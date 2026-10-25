"""Multi-agent counterfactual analysis workflow (Microsoft Agent Framework).

Graph (switch-case edges, every loop bounded by counters in the shared state):

    decision_agent --analyze--> strategy_agent --candidates--> simulation_agent --results--> verification_agent
          |                        ^   |  (retry on                 |   ^ (retry on timeout)       |
          | skip                   |   |   invalid proposals)       |   |                          |
          v                        |   +----------------------------+   |                          |
      publisher <------------------+------- revision request -----------+                          |
          ^                        +------------ revise_strategy / resimulate ---------------------+
          |                                                                                        |
          +-------- publish / unavailable --------- verification_agent <--narratives-- explanation_agent
                                                                    \\--explain-->/  (claims rejected -> retry)

The shared, typed `AnalysisWorkflowState` is owned by the analysis runtime (one object every agent
reads and writes). On every handoff a versioned snapshot of it is published into Agent Framework
workflow state (key "analysis_state", plus the "route_history" of handoffs), which copies values
between supersteps.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler, tool

from ..agents import prompts
from ..agents.policy_client import PolicyDecision, PolicyTurn
from ..agents.runner import AgentFailure, AgentRunner, ChatClientProvider
from ..agents.schemas import (
    DecisionAssessment,
    ExplanationBundle,
    Proposal,
    SimulationReport,
    StrategyProposal,
    VerificationDecision,
)
from ..config import Settings
from ..models.analysis import CounterfactualAnalysis
from ..models.common import new_id, utcnow
from ..models.decisions import CandidateAction, DecisionPoint
from ..models.match import Player
from ..models.narrative import Narrative
from ..models.simulation import SimulationConfig, SimulationRun
from ..models.state import MatchStateSnapshot
from ..models.verification import EvidenceItem
from ..models.workflow import AnalysisWorkflowState, HandoffRecord, RejectedCandidate
from ..narratives.templates import build_template_narratives
from ..services.overlays import analysis_overlays
from ..simulation import geometry as g
from ..simulation.candidates import generate_candidates, validate_candidate
from ..simulation.monte_carlo import evaluate_actions
from ..verification.checks import split_evidence_refs, verify_analysis, verify_narrative
from ..verification.evidence import action_keys

STATE_KEY = "analysis_state"
MAX_ALTERNATIVES = 3


@dataclass
class Signal:
    route: str
    reason: str = ""


@dataclass
class AnalysisContext:
    analysis: CounterfactualAnalysis
    decision: DecisionPoint
    snapshot: MatchStateSnapshot
    roster: dict[str, Player]
    settings: Settings
    rollouts: int
    horizon_s: float
    languages: list[str]
    budget_info: Callable[[], dict[str, Any]]
    cancel: threading.Event = field(default_factory=threading.Event)
    generated: dict[str, CandidateAction] = field(default_factory=dict)
    known: dict[str, CandidateAction] = field(default_factory=dict)
    evidence: list[EvidenceItem] = field(default_factory=list)
    drafts: list[Narrative] = field(default_factory=list)
    narrative_issues: dict[str, list[str]] = field(default_factory=dict)
    sim_runs: int = 0
    verification_phase: str = "analysis"
    resimulations: int = 0
    priority: str = "medium"
    overlays: list = field(default_factory=list)
    revision_requests: list[dict[str, str]] = field(default_factory=list)


class AnalysisRuntime:
    """Holds everything one analysis needs; executors call into it."""

    def __init__(self, ctx: AnalysisContext, runner: AgentRunner, publish: Callable[[str, dict], Awaitable[None] | None]):
        self.ctx = ctx
        self.runner = runner
        self.publish = publish

    @property
    def state(self) -> AnalysisWorkflowState:
        return self.ctx.analysis.workflow

    @property
    def faults(self) -> list[str]:
        return list(self.ctx.analysis.fault_injection)

    async def emit(self, kind: str, payload: dict[str, Any]) -> None:
        r = self.publish(kind, {"analysis_id": self.ctx.analysis.analysis_id, **payload})
        if asyncio.iscoroutine(r):
            await r

    async def handoff(self, src: str, dst: str, reason: str) -> None:
        self.state.handoffs.append(HandoffRecord(from_agent=src, to_agent=dst, reason=reason, at=utcnow().isoformat()))
        if self.state.steps:
            last = self.state.steps[-1]
            if last.agent == src:
                last.handoff_to = dst
                last.handoff_reason = reason
        await self.emit("handoff", {"from": src, "to": dst, "reason": reason})

    async def send(self, ctx: WorkflowContext, sig: Signal) -> None:
        """Publish the latest shared state into Agent Framework workflow state, then hand off."""
        self.state.state_version += 1
        self.state.updated_at = utcnow().isoformat()
        ctx.set_state(STATE_KEY, self.state.model_dump(mode="json"))
        ctx.set_state("route_history", [*ctx.get_state("route_history", []), f"{sig.route}:{sig.reason}"])
        await ctx.send_message(sig)

    def context_json(self, extra: dict[str, Any]) -> str:
        d = self.ctx.decision
        base = {"analysis_id": self.ctx.analysis.analysis_id, "decision_point_id": d.decision_point_id,
                "actor_id": d.actor_id, "actual_action": d.actual_action.label, "actual_type": d.actual_action.action_type}
        base.update(extra)
        return "CONTEXT_JSON: " + json.dumps(base, default=str)


def parse_context(prompt: str) -> dict[str, Any]:
    marker = "CONTEXT_JSON: "
    if marker not in prompt:
        return {}
    try:
        return json.loads(prompt.split(marker, 1)[1].strip().splitlines()[0])
    except (ValueError, IndexError):
        return {}


def _equivalent(a: CandidateAction, b: CandidateAction) -> bool:
    if a.action_type != b.action_type:
        return False
    if a.action_type == "shoot":
        return True
    if a.action_type == "pass":
        same_target = a.target_player_id == b.target_player_id
        if a.target_x is None or b.target_x is None:
            return same_target
        return same_target and g.distance((a.target_x, a.target_y), (b.target_x, b.target_y)) < 2.5
    if a.target_x is None or b.target_x is None:
        return False
    return g.distance((a.target_x, a.target_y), (b.target_x, b.target_y)) < 2.5


# =========================================================================================
# Decision Agent
# =========================================================================================


def decision_tools(rt: AnalysisRuntime) -> list:
    ctx = rt.ctx

    @tool(name="get_decision_context", description="Structured facts about the detected decision point.",
          max_invocations=2)
    def get_decision_context() -> dict:
        d = ctx.decision
        return {"decision_point_id": d.decision_point_id, "actor": d.actor_name, "team_id": d.team_id,
                "minute": d.match_clock_ms // 60000 + 1, "actual_action": d.actual_action.label,
                "observed_outcome": d.actual_outcome, "triggers": [t.value for t in d.triggers],
                "triage_score": d.candidate_score, "source": d.source,
                "features": d.features.model_dump(exclude_none=True)}

    @tool(name="get_analysis_budget", description="How many analyses already ran recently (rate limiting).",
          max_invocations=2)
    def get_analysis_budget() -> dict:
        return ctx.budget_info()

    return [get_decision_context, get_analysis_budget]


def decision_policy(turn: PolicyTurn) -> PolicyDecision:
    if "get_decision_context" not in turn.results:
        return PolicyDecision(tool_calls=[("get_decision_context", {}), ("get_analysis_budget", {})])
    c = turn.results["get_decision_context"][-1]
    b = (turn.results.get("get_analysis_budget") or [{}])[-1]
    score = float(c.get("triage_score", 0))
    within = bool(b.get("budget_remaining", 1) > 0)
    manual = c.get("source") == "manual"
    analyze = within and (manual or score >= 0.55)
    prio = "high" if score >= 0.85 else ("medium" if score >= 0.6 else "low")
    trig = ", ".join(t.lower().replace("_", " ") for t in c.get("triggers", [])) or "manual request"
    just = (f"{c.get('actor')} ({c.get('minute')}'): {trig}; triage score {score:.2f}."
            if analyze else f"Skipped: {'analysis budget exhausted' if not within else 'low viewer value'} ({trig}).")
    return PolicyDecision(final={"decision_point_id": c["decision_point_id"], "analyze": analyze, "priority": prio,
                                 "importance_justification": just})


class DecisionAgentExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="decision_agent")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Signal]) -> None:
        rt = self.rt
        rt.state.workflow_status = "running"
        rt.state.started_at = rt.state.started_at or utcnow().isoformat()
        prompt = (f"Should decision {rt.ctx.decision.decision_point_id} be analysed for viewers?\n"
                  + rt.context_json({}))
        try:
            out, step = await rt.runner.run("decision_agent", "Assess viewer value of the decision", prompts.DECISION,
                                            decision_tools(rt), prompt, DecisionAssessment, decision_policy)
        except AgentFailure as exc:
            rt.state.errors.append(f"decision_agent: {exc}")
            await rt.send(ctx, Signal("publish", "decision agent failed"))
            return
        if out.decision_point_id != rt.ctx.decision.decision_point_id:
            step.notes.append("Agent referenced a different decision id; corrected to the requested decision.")
        rt.ctx.priority = out.priority
        rt.ctx.analysis.decision_summary = {"priority": out.priority, "justification": out.importance_justification[:400],
                                            "analyze": out.analyze}
        if not out.analyze:
            rt.ctx.analysis.unavailable_reason = "Decision Agent judged the moment not worth a full analysis"
            await rt.handoff("decision_agent", "publisher", "not analysed")
            await rt.send(ctx, Signal("publish", "skip"))
            return
        await rt.handoff("decision_agent", "strategy_agent", f"analyse ({out.priority} priority)")
        await rt.send(ctx, Signal("strategy", "analyse"))


# =========================================================================================
# Strategy Agent
# =========================================================================================


def strategy_tools(rt: AnalysisRuntime) -> list:
    ctx = rt.ctx

    @tool(name="generate_candidate_actions",
          description="Deterministically enumerate feasible shots, passes and dribbles from the frozen snapshot.",
          max_invocations=2)
    def generate_candidate_actions() -> dict:
        cands = generate_candidates(ctx.snapshot, ctx.roster)
        actual = ctx.decision.actual_action
        listed = []
        for c in cands:
            if _equivalent(c, actual):
                continue
            ctx.generated[c.action_id] = c
            ctx.known[c.action_id] = c
            if len(listed) < 10:
                listed.append({"candidate_id": c.action_id, "label": c.label, "action_type": c.action_type,
                               "target_player_id": c.target_player_id,
                               "features": {k: round(v, 3) for k, v in c.features.items()}})
        return {"snapshot_id": ctx.snapshot.snapshot_id, "observed_action": actual.label, "candidates": listed}

    @tool(name="validate_candidate_action",
          description="Validate a custom action (pass target player id, or dribble target x/y in world metres).",
          max_invocations=4)
    def validate_candidate_action(action_type: str, target_player_id: str | None = None,
                                  target_x: float | None = None, target_y: float | None = None) -> dict:
        if action_type not in ("shoot", "pass", "dribble"):
            return {"ok": False, "code": "UNKNOWN_ACTION", "message": action_type}
        c = CandidateAction(action_id="probe", action_type=action_type, actor_id=ctx.decision.actor_id,
                            target_player_id=target_player_id, target_x=target_x, target_y=target_y,
                            initial_state_id=ctx.snapshot.snapshot_id)
        v = validate_candidate(ctx.snapshot, ctx.roster, c)
        return {"ok": v.ok, "code": v.code, "message": v.message}

    return [generate_candidate_actions, validate_candidate_action]


def strategy_policy(turn: PolicyTurn) -> PolicyDecision:
    if "generate_candidate_actions" not in turn.results:
        return PolicyDecision(tool_calls=[("generate_candidate_actions", {})])
    info = parse_context(turn.prompt)
    excluded = set(info.get("excluded_candidate_ids", []))
    actual_type = info.get("actual_type")
    cands = [c for c in turn.results["generate_candidate_actions"][-1]["candidates"]
             if c["candidate_id"] not in excluded]
    chosen: list[dict] = []

    def pick(pred) -> None:
        for c in cands:
            if c in chosen or not pred(c):
                continue
            chosen.append(c)
            return

    viable = lambda c: c["features"].get("completion_estimate", c["features"].get("success_estimate", 1)) >= 0.2  # noqa: E731
    # 1) best-valued safe-enough pass, 2) a different kind of option, 3) next best.
    pick(lambda c: c["action_type"] == "pass" and viable(c))
    if actual_type != "shoot":
        pick(lambda c: c["action_type"] == "shoot" and c["features"].get("modeled_shot_scoring_probability", 0) > 0.02)
    pick(lambda c: c["action_type"] == "pass" and viable(c) and c["features"].get("forward_gain_m", 0) > 3
         and all(c["target_player_id"] != x["target_player_id"] for x in chosen))
    pick(lambda c: c["action_type"] == "dribble" and viable(c))
    chosen = chosen[:2]
    proposals = []
    for c in chosen:
        f = c["features"]
        if c["action_type"] == "pass":
            why = (f"{c['label']}: completion estimate {f.get('completion_estimate', 0):.2f}, gains "
                   f"{f.get('forward_gain_m', 0):.1f} m, receiver {f.get('receiver_distance_to_goal_m', 0):.1f} m from goal.")
        elif c["action_type"] == "shoot":
            why = f"Shot option: modeled scoring probability {f.get('modeled_shot_scoring_probability', 0):.3f}."
        else:
            why = f"{c['label']}: success estimate {f.get('success_estimate', 0):.2f} into better space."
        proposals.append({"candidate_id": c["candidate_id"], "rationale": why})
    return PolicyDecision(final={"proposals": proposals, "notes": "Diverse set: best pass, alternative action type, "
                                                                   "progressive option."})


class StrategyAgentExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="strategy_agent")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Signal]) -> None:
        rt = self.rt
        st = rt.state
        if rt.ctx.cancel.is_set():
            await rt.send(ctx, Signal("publish", "cancelled"))
            return
        attempt = sum(1 for s in st.steps if s.agent == "strategy_agent") + 1
        excluded = [r.proposal.get("candidate_id") for r in st.rejected_candidates if r.proposal.get("candidate_id")]
        feedback = st.revision_feedback[-4:]
        prompt = ("Propose alternatives to the observed action.\n"
                  + (f"Feedback from earlier attempts: {feedback}\n" if feedback else "")
                  + rt.context_json({"excluded_candidate_ids": excluded, "attempt": attempt,
                                     "max_alternatives": MAX_ALTERNATIVES}))
        try:
            out, step = await rt.runner.run("strategy_agent", "Propose feasible alternative actions", prompts.STRATEGY,
                                            strategy_tools(rt), prompt, StrategyProposal, strategy_policy, attempt)
        except AgentFailure as exc:
            st.errors.append(f"strategy_agent: {exc}")
            await rt.send(ctx, Signal("publish", "strategy failed"))
            return
        proposals = list(out.proposals)[:MAX_ALTERNATIVES]
        if "invalid_candidate" in rt.faults and attempt == 1:
            actor_team = rt.ctx.roster[rt.ctx.decision.actor_id].team_id
            bench = next(pid for pid in rt.ctx.snapshot.off_pitch_player_ids
                         if rt.ctx.roster[pid].team_id == actor_team)
            proposals.append(Proposal(action_type="pass", target_player_id=bench,
                                      rationale="[controlled fault injection] pass to a player who is not on the pitch"))
            step.notes.append(f"Controlled fault injection: appended an invalid proposal (pass to {bench}).")
        accepted: list[CandidateAction] = []
        rejected_now: list[str] = []
        for p in proposals:
            cand, reason = self._materialize(p)
            if cand is None:
                st.rejected_candidates.append(RejectedCandidate(proposal=p.model_dump(), reason=reason, stage="validation"))
                rejected_now.append(reason)
                continue
            if any(_equivalent(cand, a) for a in accepted) or _equivalent(cand, rt.ctx.decision.actual_action):
                continue
            accepted.append(cand)
        step.output["validated_candidates"] = [c.action_id for c in accepted]
        step.output["rejected"] = rejected_now
        if rejected_now:
            st.revision_feedback.append("Rejected by deterministic validation: " + "; ".join(rejected_now))
            step.status = "rejected" if not accepted or "invalid_candidate" in rt.faults else step.status
        revisions_left = st.retry_count < rt.ctx.settings.max_strategy_revisions
        if rejected_now and revisions_left:
            st.retry_count += 1
            await rt.handoff("strategy_agent", "strategy_agent", "validation rejected a proposal; revising")
            await rt.send(ctx, Signal("strategy", "revise after validation"))
            return
        if not accepted:
            rt.ctx.analysis.unavailable_reason = "No valid alternative actions"
            await rt.handoff("strategy_agent", "publisher", "no valid candidates")
            await rt.send(ctx, Signal("publish", "no candidates"))
            return
        actual = rt.ctx.decision.actual_action
        rt.ctx.analysis.candidates = [actual] + accepted
        rt.ctx.analysis.actual_action_id = actual.action_id
        st.actual_action_id = actual.action_id
        st.candidate_action_ids = [c.action_id for c in rt.ctx.analysis.candidates]
        await rt.emit("candidates", {"candidates": [c.label for c in rt.ctx.analysis.candidates]})
        await rt.handoff("strategy_agent", "simulation_agent", f"{len(accepted)} alternatives + observed action")
        await rt.send(ctx, Signal("simulation", "evaluate"))

    def _materialize(self, p: Proposal) -> tuple[CandidateAction | None, str]:
        rt = self.rt
        if p.candidate_id:
            c = rt.ctx.known.get(p.candidate_id) or rt.ctx.generated.get(p.candidate_id)
            if c is None:
                return None, f"UNKNOWN_CANDIDATE: {p.candidate_id} was not produced by the generator"
            c = c.model_copy(update={"source": "agent"})
        else:
            if p.action_type is None:
                return None, "MISSING_ACTION_TYPE"
            aid = f"{rt.ctx.snapshot.snapshot_id}-agent-{p.action_type}-{p.target_player_id or 'pt'}"
            label = {"shoot": "Shoot", "dribble": "Dribble"}.get(p.action_type, "Pass")
            if p.target_player_id and p.target_player_id in rt.ctx.roster:
                label = f"Pass to {rt.ctx.roster[p.target_player_id].short_name}"
            c = CandidateAction(action_id=aid, action_type=p.action_type, actor_id=rt.ctx.decision.actor_id,
                                target_player_id=p.target_player_id, target_x=p.target_x, target_y=p.target_y,
                                initial_state_id=rt.ctx.snapshot.snapshot_id, label=label, source="agent")
            if c.action_type == "pass" and c.target_player_id and c.target_x is None:
                gen = next((x for x in rt.ctx.generated.values() if x.action_type == "pass"
                            and x.target_player_id == c.target_player_id and "-through-" not in x.action_id), None)
                if gen is not None:
                    c = c.model_copy(update={"target_x": gen.target_x, "target_y": gen.target_y})
        v = validate_candidate(rt.ctx.snapshot, rt.ctx.roster, c)
        if not v.ok:
            return None, f"{v.code}: {v.message}"
        rt.ctx.known[c.action_id] = c
        return c, "ok"


# =========================================================================================
# Simulation Agent
# =========================================================================================


def simulation_tools(rt: AnalysisRuntime) -> list:
    ctx = rt.ctx

    @tool(name="run_simulation",
          description="Run the deterministic Monte Carlo simulator for all current candidates from the frozen snapshot.",
          max_invocations=2)
    async def run_simulation(rollouts: int) -> dict:
        settings = ctx.settings
        n = int(max(20, min(int(rollouts), settings.max_rollouts)))
        budget = settings.simulation_time_budget_s
        if "simulation_timeout" in rt.faults and ctx.sim_runs == 0:
            budget = 0.25
        cfg = SimulationConfig(horizon_s=ctx.horizon_s, rollouts=n, seed=ctx.snapshot.seed, time_budget_s=budget)
        run = SimulationRun(simulation_run_id=new_id("sim"), analysis_id=ctx.analysis.analysis_id,
                            snapshot_id=ctx.snapshot.snapshot_id, config=cfg, status="running",
                            started_at=utcnow().isoformat())
        ctx.analysis.simulation = run
        await rt.emit("simulation_started", {"simulation_run_id": run.simulation_run_id, "rollouts": n})
        t0 = time.perf_counter()
        try:
            out = await asyncio.to_thread(evaluate_actions, ctx.snapshot, ctx.roster, ctx.analysis.candidates, cfg,
                                          ctx.cancel)
        except Exception as exc:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            return {"simulation_run_id": run.simulation_run_id, "status": "failed", "error": run.error}
        ctx.sim_runs += 1
        run.results = out.results
        run.comparisons = out.comparisons
        run.ranking = out.ranking
        run.overall_verdict = out.overall_verdict
        run.partial = out.partial
        run.status = "cancelled" if out.cancelled else ("timed_out" if out.timed_out else "completed")
        if out.completed_rollouts < n:
            run.config = cfg.model_copy(update={"rollouts": out.completed_rollouts})
        run.finished_at = utcnow().isoformat()
        run.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        rt.state.simulation_run_id = run.simulation_run_id
        rt.state.simulation_budget = n
        keys = action_keys(ctx.analysis)
        labels = {c.action_id: c.label for c in ctx.analysis.candidates}
        await rt.emit("simulation_completed", {"simulation_run_id": run.simulation_run_id, "status": run.status,
                                               "duration_ms": run.duration_ms})
        return {
            "simulation_run_id": run.simulation_run_id, "status": run.status, "requested_rollouts": n,
            "completed_rollouts": out.completed_rollouts, "partial": out.partial, "elapsed_s": round(out.elapsed_s, 2),
            "overall_verdict": out.overall_verdict,
            "results": [{"candidate_id": r.action_id, "key": keys[r.action_id], "label": labels[r.action_id],
                         "p_goal": r.p_goal.value, "p_goal_ci95": [r.p_goal.ci95_low, r.p_goal.ci95_high],
                         "p_shot": r.p_shot.value, "p_turnover": r.p_turnover.value,
                         "p_first_action_success": r.p_first_action_success.value} for r in out.results],
            "comparisons": [{"candidate_id": c.action_id, "diff_p_goal": c.diff_p_goal,
                             "ci95": [c.diff_ci95_low, c.diff_ci95_high], "verdict": c.verdict,
                             "secondary": c.secondary_note} for c in out.comparisons],
        }

    @tool(name="request_strategy_revision",
          description="Ask the Strategy Agent to replace one implausible alternative (bounded).", max_invocations=1)
    def request_strategy_revision(candidate_id: str, reason: str) -> dict:
        left = rt.ctx.settings.max_strategy_revisions - rt.state.retry_count
        known = {c.action_id for c in ctx.analysis.candidates if not c.is_actual}
        if candidate_id not in known:
            return {"accepted": False, "reason": "unknown candidate id"}
        if left <= 0:
            return {"accepted": False, "reason": "revision budget exhausted"}
        ctx.revision_requests.append({"candidate_id": candidate_id, "reason": reason[:300]})
        return {"accepted": True, "revisions_left": left - 1}

    return [run_simulation, request_strategy_revision]


def simulation_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_context(turn.prompt)
    runs = turn.results.get("run_simulation", [])
    if not runs:
        return PolicyDecision(tool_calls=[("run_simulation", {"rollouts": int(info.get("default_rollouts", 200))})])
    last = runs[-1]
    if last.get("status") == "failed":
        return PolicyDecision(final={"simulation_run_id": last.get("simulation_run_id"), "rollouts_used": 0,
                                     "stable": False, "summary": f"Simulation failed: {last.get('error')}"})
    if len(runs) == 1 and last.get("partial") and last.get("completed_rollouts", 0) < 50:
        return PolicyDecision(tool_calls=[("run_simulation", {"rollouts": 100})])
    comps = last.get("comparisons", [])
    best = max(comps, key=lambda c: c["diff_p_goal"]) if comps else None
    wide = best is not None and (best["ci95"][1] - best["ci95"][0]) > 0.04
    max_r = int(info.get("max_rollouts", 500))
    if (len(runs) == 1 and best is not None and best["verdict"] == "inconclusive" and wide
            and last.get("completed_rollouts", 0) < max_r and info.get("allow_escalation", True)):
        return PolicyDecision(tool_calls=[("run_simulation", {"rollouts": max_r})])
    requested = "request_strategy_revision" in turn.results
    if not requested and info.get("revisions_left", 0) > 0:
        for r in last.get("results", []):
            if r["key"] != "actual" and r["p_first_action_success"] < 0.15 and r["p_goal"] == 0:
                return PolicyDecision(tool_calls=[("request_strategy_revision", {
                    "candidate_id": r["candidate_id"],
                    "reason": f"{r['label']} almost never succeeds ({r['p_first_action_success']:.0%} first-action "
                              f"success) and never scores under the model; propose a more plausible alternative."})])
    stable = not last.get("partial", False)
    revs = []
    if requested:
        ok = turn.results["request_strategy_revision"][-1]
        if ok.get("accepted"):
            # The request itself is stored by the tool; echo it for the report.
            revs = [{"candidate_id": "see_tool_call", "reason": "requested via tool"}]
    summary = (f"{last.get('completed_rollouts')} rollouts per option, verdict {last.get('overall_verdict')}"
               + (" (partial: time budget reached)" if last.get("partial") else ""))
    return PolicyDecision(final={"simulation_run_id": last.get("simulation_run_id"),
                                 "rollouts_used": last.get("completed_rollouts", 0), "stable": stable,
                                 "revision_requests": revs, "summary": summary})


class SimulationAgentExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="simulation_agent")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Signal]) -> None:
        rt = self.rt
        st = rt.state
        if rt.ctx.cancel.is_set():
            await rt.send(ctx, Signal("publish", "cancelled"))
            return
        attempt = sum(1 for s in st.steps if s.agent == "simulation_agent") + 1
        rt.ctx.revision_requests = []
        prompt = ("Evaluate the candidates with the simulator and report.\n" + rt.context_json({
            "candidates": [{"id": c.action_id, "label": c.label} for c in rt.ctx.analysis.candidates],
            "default_rollouts": rt.ctx.rollouts, "max_rollouts": rt.ctx.settings.max_rollouts,
            "allow_escalation": rt.ctx.rollouts < rt.ctx.settings.max_rollouts,
            "revisions_left": rt.ctx.settings.max_strategy_revisions - st.retry_count, "attempt": attempt}))
        try:
            out, step = await rt.runner.run("simulation_agent", "Run and assess Monte Carlo simulations",
                                            prompts.SIMULATION, simulation_tools(rt), prompt, SimulationReport,
                                            simulation_policy, attempt)
        except AgentFailure as exc:
            st.errors.append(f"simulation_agent: {exc}")
            await rt.send(ctx, Signal("publish", "simulation agent failed"))
            return
        sim = rt.ctx.analysis.simulation
        if rt.ctx.revision_requests and st.retry_count < rt.ctx.settings.max_strategy_revisions:
            st.retry_count += 1
            for req in rt.ctx.revision_requests:
                cid = req["candidate_id"]
                st.rejected_candidates.append(RejectedCandidate(proposal={"candidate_id": cid}, reason=req["reason"],
                                                                stage="simulation"))
                st.revision_feedback.append(f"Simulation Agent: {req['reason']}")
            await rt.handoff("simulation_agent", "strategy_agent", rt.ctx.revision_requests[0]["reason"][:160])
            await rt.send(ctx, Signal("strategy", "revision requested"))
            return
        if sim is None or sim.status == "failed" or not sim.results:
            if attempt < 2:
                await rt.handoff("simulation_agent", "simulation_agent", "simulation failed; retrying once")
                await rt.send(ctx, Signal("simulation", "retry"))
                return
            rt.ctx.analysis.unavailable_reason = "Simulation failed"
            await rt.send(ctx, Signal("publish", "simulation failed"))
            return
        if sim.status == "cancelled":
            await rt.send(ctx, Signal("publish", "cancelled"))
            return
        step.output["simulation_status"] = sim.status
        await rt.handoff("simulation_agent", "verification_agent", f"{sim.config.rollouts} rollouts/option ready")
        await rt.send(ctx, Signal("verification", "verify analysis"))


# =========================================================================================
# Verification Agent
# =========================================================================================

REVISE_CHECKS = {"candidates_valid", "actual_included", "candidate_count", "unique_candidates"}
RESIM_CHECKS = {"probabilities_consistent", "comparisons_consistent", "equal_budget", "results_cover_candidates",
                "simulation_completed", "reproducible", "simulator_version"}


def verification_tools(rt: AnalysisRuntime) -> list:
    ctx = rt.ctx

    @tool(name="run_verification_checks",
          description="Run the deterministic verification layer on the current analysis.", max_invocations=2)
    async def run_verification_checks() -> dict:
        rec = await asyncio.to_thread(verify_analysis, ctx.analysis, ctx.decision, ctx.snapshot, ctx.roster)
        ctx.analysis.verification = rec
        ctx.evidence = rec.accepted_evidence
        return {"phase": "analysis", "status": rec.status,
                "failed_errors": [c.check_id for c in rec.checks if not c.passed and c.severity == "error"],
                "failed_warnings": [c.check_id for c in rec.checks if not c.passed and c.severity == "warning"],
                "passed": sum(1 for c in rec.checks if c.passed), "total": len(rec.checks),
                "details": {c.check_id: c.details for c in rec.checks if not c.passed}}

    @tool(name="verify_narratives",
          description="Check every drafted narrative claim against the evidence table.", max_invocations=2)
    def verify_narratives() -> dict:
        allowed = _allowed_players(ctx)
        issues: dict[str, list[str]] = {}
        for n in ctx.drafts:
            iss = verify_narrative(n, ctx.evidence, ctx.roster, allowed)
            n.verification_status = "rejected" if iss else "verified"
            n.verification_notes = iss
            if iss:
                issues[f"{n.audience}/{n.language}"] = iss
        ctx.narrative_issues = issues
        return {"phase": "narratives", "drafts": len(ctx.drafts), "rejected": issues}

    return [run_verification_checks, verify_narratives]


def _allowed_players(ctx: AnalysisContext) -> set[str]:
    return allowed_players(ctx.decision, ctx.analysis, ctx.snapshot)


def allowed_players(decision: DecisionPoint, analysis: CounterfactualAnalysis, snapshot: MatchStateSnapshot) -> set[str]:
    """Players a narrative may mention: the actor, the option targets and everyone within 12 m of the actor."""
    allowed = {decision.actor_id}
    allowed |= {c.target_player_id for c in analysis.candidates if c.target_player_id}
    actor = snapshot.player(decision.actor_id)
    if actor is not None:
        for p in snapshot.players:
            if g.distance((p.x, p.y), (actor.x, actor.y)) < 12:
                allowed.add(p.player_id)
    return allowed


def verification_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_context(turn.prompt)
    phase = info.get("phase", "analysis")
    tool_name = "run_verification_checks" if phase == "analysis" else "verify_narratives"
    if tool_name not in turn.results:
        return PolicyDecision(tool_calls=[(tool_name, {})])
    r = turn.results[tool_name][-1]
    if phase == "narratives":
        rejected = r.get("rejected", {})
        if rejected:
            issues = [f"{k}: {v[0]}" for k, v in rejected.items()]
            return PolicyDecision(final={"status": "rejected", "route": "explain", "issues": issues,
                                         "assessment": f"{len(rejected)} narrative(s) contain unsupported claims."})
        return PolicyDecision(final={"status": "verified", "route": "publish", "issues": [],
                                     "assessment": f"All {r.get('drafts')} narratives are grounded in the evidence."})
    errors = set(r.get("failed_errors", []))
    warns = r.get("failed_warnings", [])
    if not errors:
        return PolicyDecision(final={"status": "verified", "route": "explain", "issues": warns,
                                     "assessment": f"{r['passed']}/{r['total']} checks passed"
                                                   + (f"; warnings: {', '.join(warns)}" if warns else "")})
    route = "revise_strategy" if errors & REVISE_CHECKS else ("resimulate" if errors & RESIM_CHECKS else "unavailable")
    return PolicyDecision(final={"status": "rejected", "route": route,
                                 "issues": [f"{e}: {r['details'].get(e, '')}" for e in sorted(errors)],
                                 "assessment": f"Deterministic checks failed: {', '.join(sorted(errors))}"})


class VerificationAgentExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="verification_agent")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Signal]) -> None:
        rt = self.rt
        st = rt.state
        phase = "narratives" if sig.route == "verify_narratives" else "analysis"
        rt.ctx.verification_phase = phase
        attempt = sum(1 for s in st.steps if s.agent == "verification_agent") + 1
        prompt = (("Verify the analysis before it is explained." if phase == "analysis"
                   else "Verify the drafted narratives against the evidence.") + "\n"
                  + rt.context_json({"phase": phase}))
        try:
            out, step = await rt.runner.run("verification_agent", f"Verify {phase}", prompts.VERIFICATION,
                                            verification_tools(rt), prompt, VerificationDecision, verification_policy,
                                            attempt)
        except AgentFailure as exc:
            st.errors.append(f"verification_agent: {exc}")
            rt.ctx.analysis.unavailable_reason = "Verification could not run"
            await rt.send(ctx, Signal("publish", "verification failed"))
            return
        if phase == "analysis":
            rec = rt.ctx.analysis.verification
            if rec is None:  # the agent did not call the tool: run it deterministically
                rec = await asyncio.to_thread(verify_analysis, rt.ctx.analysis, rt.ctx.decision, rt.ctx.snapshot,
                                              rt.ctx.roster)
                rt.ctx.analysis.verification = rec
                rt.ctx.evidence = rec.accepted_evidence
                step.notes.append("Deterministic checks executed by the orchestrator (agent skipped the tool).")
            rec.agent_assessment = out.assessment[:600]
            st.verification_status = rec.status
            st.verification_issues = rec.failures + [i for i in out.issues if i not in rec.failures][:6]
            deterministic_failed = rec.status == "rejected"
            route = out.route
            if deterministic_failed and out.status == "verified":
                step.notes.append("Agent tried to accept an analysis with failing deterministic checks; overridden.")
                route = "unavailable"
            if not deterministic_failed and out.status == "rejected" and route == "explain":
                route = "resimulate"
            if not deterministic_failed and route == "explain":
                await rt.handoff("verification_agent", "explanation_agent", "analysis verified")
                await rt.send(ctx, Signal("explanation", "explain"))
                return
            if route == "revise_strategy" and st.retry_count < rt.ctx.settings.max_strategy_revisions:
                st.retry_count += 1
                st.revision_feedback.append("Verification: " + "; ".join(rec.failures)[:300])
                await rt.handoff("verification_agent", "strategy_agent", "invalid candidates")
                await rt.send(ctx, Signal("strategy", "revise"))
                return
            if route == "resimulate" and rt.ctx.resimulations < 1:
                rt.ctx.resimulations += 1
                await rt.handoff("verification_agent", "simulation_agent", "inconsistent simulation results")
                await rt.send(ctx, Signal("simulation", "resimulate"))
                return
            rt.ctx.analysis.unavailable_reason = "Verification rejected the analysis: " + "; ".join(rec.failures)[:300]
            await rt.handoff("verification_agent", "publisher", "analysis unavailable")
            await rt.send(ctx, Signal("publish", "rejected"))
            return
        # narratives phase. Rejected claims are always recorded, whichever route the agent picks: a rewrite
        # by the Explanation Agent, or (publisher) replacement by a verified template.
        if rt.ctx.narrative_issues:
            st.verification_issues = [f"{k}: {'; '.join(v)}" for k, v in rt.ctx.narrative_issues.items()]
        if out.route == "explain" and rt.ctx.narrative_issues and \
                st.explanation_retries < rt.ctx.settings.max_explanation_retries:
            st.explanation_retries += 1
            st.verification_issues = [f"{k}: {'; '.join(v)}" for k, v in rt.ctx.narrative_issues.items()]
            await rt.handoff("verification_agent", "explanation_agent", "unsupported claims; regenerate")
            await rt.send(ctx, Signal("explanation", "regenerate"))
            return
        await rt.handoff("verification_agent", "publisher", "narratives checked")
        await rt.send(ctx, Signal("publish", "narratives checked"))


# =========================================================================================
# Explanation Agent
# =========================================================================================


def explanation_tools(rt: AnalysisRuntime) -> list:
    ctx = rt.ctx

    @tool(name="get_verified_evidence",
          description="Evidence table (refs, labels, display values), allowed players and requested outputs.",
          max_invocations=2)
    def get_verified_evidence() -> dict:
        return {"evidence": [{"ref": e.ref, "label": e.label, "display": e.display} for e in ctx.evidence],
                "allowed_players": sorted(ctx.roster[p].name for p in _allowed_players(ctx)),
                "requested": [{"audience": a, "language": lang} for lang in ctx.languages
                              for a in ("casual", "analyst", "broadcaster")],
                "previous_issues": rt.state.verification_issues[-6:]}

    @tool(name="check_narrative", description="Self-check a draft narrative for unsupported numbers or claims.",
          max_invocations=6)
    def check_narrative(audience: str, language: str, headline: str, body: str, caption: str | None = None) -> dict:
        n = Narrative(narrative_id="draft", analysis_id=ctx.analysis.analysis_id,
                      audience=audience if audience in ("casual", "analyst", "broadcaster") else "casual",
                      language=language if language in ("en", "nl", "es", "fr", "de") else "en", headline=headline, body=body,
                      caption=caption, generated_by="draft", is_live_model_output=False, created_at="")
        return {"issues": verify_narrative(n, ctx.evidence, ctx.roster, _allowed_players(ctx))}

    return [get_verified_evidence, check_narrative]


def make_explanation_policy(rt: AnalysisRuntime):
    def policy(turn: PolicyTurn) -> PolicyDecision:
        if "get_verified_evidence" not in turn.results:
            return PolicyDecision(tool_calls=[("get_verified_evidence", {})])
        ctx = rt.ctx
        tpl = build_template_narratives(ctx.analysis, ctx.decision, ctx.roster, ctx.evidence, ctx.languages)
        return PolicyDecision(final={"narratives": [
            {"audience": n.audience, "language": n.language, "headline": n.headline, "body": n.body,
             "bullets": n.bullets, "caption": n.caption, "evidence_refs": n.evidence_refs} for n in tpl]})
    return policy


class ExplanationAgentExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="explanation_agent")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Signal]) -> None:
        rt = self.rt
        st = rt.state
        attempt = sum(1 for s in st.steps if s.agent == "explanation_agent") + 1
        feedback = st.verification_issues[-6:] if attempt > 1 else []
        prompt = ("Write viewer narratives for the verified analysis.\n"
                  + (f"The Verification Agent rejected these claims, fix them: {feedback}\n" if feedback else "")
                  + rt.context_json({"languages": rt.ctx.languages, "attempt": attempt}))
        try:
            out, step = await rt.runner.run("explanation_agent", "Explain the verified analysis", prompts.EXPLANATION,
                                            explanation_tools(rt), prompt, ExplanationBundle,
                                            make_explanation_policy(rt), attempt)
        except AgentFailure as exc:
            st.errors.append(f"explanation_agent: {exc}")
            out, step = ExplanationBundle(narratives=[]), None
        live = bool(step and step.live_model)
        label = step.model if step else "none"
        drafts: list[Narrative] = []
        dropped: set[str] = set()
        for d in out.narratives[:6]:
            refs, unknown = split_evidence_refs(d.evidence_refs[:20], rt.ctx.evidence)
            dropped.update(unknown)
            drafts.append(Narrative(
                narrative_id=new_id("nar"), analysis_id=rt.ctx.analysis.analysis_id, audience=d.audience,
                language=d.language, headline=d.headline[:140], body=d.body[:900], bullets=[b[:240] for b in d.bullets[:10]],
                caption=(d.caption or None) and d.caption[:140], evidence_refs=refs,
                generated_by=label if live else "policy-template", is_live_model_output=live,
                created_at=utcnow().isoformat()))
        if dropped and step:
            step.notes.append(f"Dropped citations of evidence fields that do not exist: {sorted(dropped)[:4]}")
        if "contradictory_claim" in rt.faults and attempt == 1 and drafts:
            sim = rt.ctx.analysis.simulation
            best = max(sim.results, key=lambda r: r.p_goal.value)
            wrong = min(0.95, best.p_goal.value + 0.173)
            d0 = drafts[0]
            injected = (f" [Injected] In fact the model gives this option a {wrong * 100:.1f}% chance."
                        if d0.language == "en" else f" [Injected] Het model geeft deze optie {wrong * 100:.1f}% kans.")
            drafts[0] = d0.model_copy(update={"body": d0.body + injected})
            if step:
                step.notes.append("Controlled fault injection: a probability inconsistent with the simulation was "
                                  "inserted into the first narrative.")
        rt.ctx.drafts = drafts
        st.narrative_ids = [n.narrative_id for n in drafts]
        await rt.handoff("explanation_agent", "verification_agent", f"{len(drafts)} narratives drafted")
        await rt.send(ctx, Signal("verify_narratives", "check claims"))


# =========================================================================================
# Publisher
# =========================================================================================


class PublisherExecutor(Executor):
    def __init__(self, rt: AnalysisRuntime):
        super().__init__(id="publisher")
        self.rt = rt

    @handler
    async def run(self, sig: Signal, ctx: WorkflowContext[Never, CounterfactualAnalysis]) -> None:
        rt = self.rt
        a = rt.ctx.analysis
        st = rt.state
        now = utcnow().isoformat()
        if rt.ctx.cancel.is_set() or sig.reason == "cancelled":
            a.status = "cancelled"
            st.workflow_status = "cancelled"
        elif a.verification is not None and a.verification.status != "rejected" and a.simulation is not None \
                and rt.ctx.drafts:
            final: list[Narrative] = []
            fallback_needed = [n for n in rt.ctx.drafts if n.verification_status != "verified"]
            final.extend(n for n in rt.ctx.drafts if n.verification_status == "verified")
            if fallback_needed:
                tpl = build_template_narratives(a, rt.ctx.decision, rt.ctx.roster, rt.ctx.evidence, rt.ctx.languages,
                                                generated_by="policy-template (fallback after rejected narrative)")
                allowed = _allowed_players(rt.ctx)
                have = {(n.audience, n.language) for n in final}
                for n in tpl:
                    if (n.audience, n.language) in have:
                        continue
                    iss = verify_narrative(n, rt.ctx.evidence, rt.ctx.roster, allowed)
                    n.verification_status = "rejected" if iss else "verified"
                    n.verification_notes = iss
                    if not iss:
                        final.append(n)
                st.errors.append(f"{len(fallback_needed)} narrative(s) replaced by verified templates")
            order = {"casual": 0, "analyst": 1, "broadcaster": 2}
            final.sort(key=lambda n: (n.language, order[n.audience]))
            a.narratives = final
            st.narrative_ids = [n.narrative_id for n in final]
            a.status = "verified"
            st.workflow_status = "completed"
        elif a.decision_summary.get("analyze") is False:
            a.status = "unavailable"
            st.workflow_status = "completed"
        else:
            a.status = "unavailable"
            st.workflow_status = "unavailable"
            a.unavailable_reason = a.unavailable_reason or sig.reason
        a.completed_at = now
        st.finished_at = now
        st.updated_at = now
        a.model.live_model_calls = rt.runner.live_calls
        a.model.policy_fallbacks = rt.runner.policy_fallbacks
        a.model.degraded = st.degraded
        rt.ctx.overlays = analysis_overlays(a, rt.ctx.decision, rt.ctx.priority)
        await rt.emit("analysis_completed", {"status": a.status})
        await ctx.yield_output(a)


def build_workflow(rt: AnalysisRuntime):
    decision = DecisionAgentExecutor(rt)
    strategy = StrategyAgentExecutor(rt)
    simulation = SimulationAgentExecutor(rt)
    verification = VerificationAgentExecutor(rt)
    explanation = ExplanationAgentExecutor(rt)
    publisher = PublisherExecutor(rt)

    def route(name: str):
        return lambda s: isinstance(s, Signal) and s.route == name

    return (
        WorkflowBuilder(start_executor=decision, max_iterations=40, name="offscript-counterfactual-analysis",
                        description="Decision -> Strategy -> Simulation -> Verification -> Explanation -> Publish")
        .add_switch_case_edge_group(decision, [Case(condition=route("strategy"), target=strategy),
                                               Default(target=publisher)])
        .add_switch_case_edge_group(strategy, [Case(condition=route("simulation"), target=simulation),
                                               Case(condition=route("strategy"), target=strategy),
                                               Default(target=publisher)])
        .add_switch_case_edge_group(simulation, [Case(condition=route("verification"), target=verification),
                                                 Case(condition=route("strategy"), target=strategy),
                                                 Case(condition=route("simulation"), target=simulation),
                                                 Default(target=publisher)])
        .add_switch_case_edge_group(verification, [Case(condition=route("explanation"), target=explanation),
                                                   Case(condition=route("strategy"), target=strategy),
                                                   Case(condition=route("simulation"), target=simulation),
                                                   Default(target=publisher)])
        .add_edge(explanation, verification)
        .build()
    )


async def run_workflow(rt: AnalysisRuntime, timeout_s: float = 180.0) -> CounterfactualAnalysis:
    wf = build_workflow(rt)
    try:
        result = await asyncio.wait_for(wf.run(Signal("start", "decision detected")), timeout_s)
        outputs = result.get_outputs()
    except TimeoutError:
        rt.ctx.cancel.set()
        rt.state.workflow_status = "timed_out"
        rt.ctx.analysis.status = "failed"
        rt.ctx.analysis.unavailable_reason = f"Analysis exceeded {timeout_s:.0f} s"
        rt.state.errors.append("workflow timeout")
        return rt.ctx.analysis
    if not outputs:
        rt.ctx.analysis.status = "failed"
        rt.state.workflow_status = "failed"
        rt.state.errors.append("workflow produced no output")
        return rt.ctx.analysis
    return outputs[-1]


__all__ = ["AnalysisContext", "AnalysisRuntime", "ChatClientProvider", "build_workflow", "run_workflow", "Signal"]

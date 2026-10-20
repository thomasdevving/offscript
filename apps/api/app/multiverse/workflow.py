"""Adversarial planning workflow (Microsoft Agent Framework) for one Multiverse decision node.

    attacking_agent -> defending_agent -> simulation_agent --(new strategies, round < max)--> attacking_agent
                                                         \\--(converged / budget)--> verification_agent
    verification_agent --(verified)--> explanation_agent -> verification_agent (narratives) -> publisher
                       \\--(rejected)--> publisher (failed node, parent untouched)

The attacking agent maximises and the defending agent minimises the same simulator-computed value
V(state, A, D) = modelled expected goals within the horizon. Rounds are bounded (default 3). The
simulation agent's tool fills the response matrix; agents only choose and revise strategies.
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

from ..agents import multiverse_prompts as mp
from ..agents import prompts
from ..agents.policy_client import PolicyDecision, PolicyTurn
from ..agents.runner import AgentFailure, AgentRunner
from ..agents.schemas import AttackPlan, DefensePlan, ExplanationBundle, MatrixReport, VerificationDecision
from ..config import Settings
from ..models.common import new_id, utcnow
from ..models.decisions import CandidateAction
from ..models.match import Player
from ..models.multiverse import (
    AttackProposal,
    BranchNode,
    DefenseProposal,
    DefensiveAssignment,
    DefensiveStrategy,
    MultiversePlanning,
    PlanningRound,
    SampleKind,
    StrategySummary,
)
from ..models.narrative import Narrative
from ..models.state import MatchStateSnapshot
from ..models.workflow import HandoffRecord
from ..simulation import geometry as g
from ..simulation.candidates import generate_candidates, validate_candidate
from ..simulation.defense import BASELINE, generate_defensive_options, validate_strategy
from .core import (
    CellEvaluator,
    CellResult,
    StepOutcome,
    action_fingerprint,
    realize_transition,
    snapshot_digest,
)
from .narratives import build_multiverse_evidence, build_multiverse_narratives
from .verify import verify_planning

MAX_ATTACK = 3
MAX_DEFENSE = 3


@dataclass
class MvSignal:
    route: str
    reason: str = ""


@dataclass
class MvContext:
    node: BranchNode
    snapshot: MatchStateSnapshot
    roster: dict[str, Player]
    settings: Settings
    planning: MultiversePlanning
    evaluator: CellEvaluator
    user_action: CandidateAction | None
    actual_action: CandidateAction | None
    sample_kind: SampleKind
    child_snapshot_id: str
    rollouts_per_cell: int
    horizon_s: float
    languages: list[str]
    cancel: threading.Event = field(default_factory=threading.Event)
    generated: dict[str, CandidateAction] = field(default_factory=dict)
    strategies: dict[str, DefensiveStrategy] = field(default_factory=dict)
    attack_set: list[str] = field(default_factory=list)
    defense_set: list[str] = field(default_factory=list)
    cells: dict[tuple[str, str], CellResult] = field(default_factory=dict)
    new_attack: bool = False
    new_defense: bool = False
    round: int = 0
    parent_digest: str = ""
    outcome: StepOutcome | None = None
    evidence: list = field(default_factory=list)
    drafts: list[Narrative] = field(default_factory=list)
    narrative_issues: dict[str, list[str]] = field(default_factory=dict)
    explanation_retries: int = 0
    custom_counter: int = 0

    def action(self, aid: str) -> CandidateAction:
        if self.user_action is not None and aid == self.user_action.action_id:
            return self.user_action
        return self.generated[aid]

    def all_strategy_ids(self) -> list[str]:
        return [BASELINE.strategy_id] + [s for s in self.defense_set if s != BASELINE.strategy_id]


class MvRuntime:
    def __init__(self, ctx: MvContext, runner: AgentRunner, publish: Callable[[str, dict], Awaitable[None] | None]):
        self.ctx = ctx
        self.runner = runner
        self.publish = publish

    @property
    def planning(self) -> MultiversePlanning:
        return self.ctx.planning

    async def emit(self, kind: str, payload: dict[str, Any]) -> None:
        r = self.publish(kind, {"planning_id": self.planning.planning_id, **payload})
        if asyncio.iscoroutine(r):
            await r

    async def send(self, wctx: WorkflowContext, sig: MvSignal, src: str, dst: str) -> None:
        p = self.planning
        p.handoffs.append(HandoffRecord(from_agent=src, to_agent=dst, reason=sig.reason, at=utcnow().isoformat()))
        if p.steps and p.steps[-1].agent == src:
            p.steps[-1].handoff_to, p.steps[-1].handoff_reason = dst, sig.reason
        p.state_version += 1
        p.updated_at = utcnow().isoformat()
        wctx.set_state("multiverse_state", {"round": self.ctx.round, "attack": self.ctx.attack_set,
                                            "defense": self.ctx.defense_set, "version": p.state_version})
        await self.emit("handoff", {"from": src, "to": dst, "reason": sig.reason})
        await wctx.send_message(sig)

    def context_json(self, extra: dict[str, Any]) -> str:
        c = self.ctx
        base = {"node_id": c.node.node_id, "snapshot_id": c.snapshot.snapshot_id, "round": c.round,
                "user_action_id": c.user_action.action_id if c.user_action else None, "mode": c.planning.mode}
        base.update(extra)
        return "CONTEXT_JSON: " + json.dumps(base, default=str)


def parse_ctx(prompt: str) -> dict[str, Any]:
    marker = "CONTEXT_JSON: "
    if marker not in prompt:
        return {}
    try:
        return json.loads(prompt.split(marker, 1)[1].strip().splitlines()[0])
    except (ValueError, IndexError):
        return {}


def _values(ctx: MvContext) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for (aid, sid), cell in ctx.cells.items():
        out.setdefault(aid, {})[sid] = cell.cell.xg
    return out


def _feedback(ctx: MvContext) -> dict:
    vals = _values(ctx)
    rows = []
    for aid in ctx.attack_set:
        v = vals.get(aid, {})
        if not v:
            continue
        counter = min(v, key=lambda s: (v[s], s))
        rows.append({"candidate_id": aid, "label": ctx.action(aid).label,
                     "worst_case_xg": round(min(v.values()), 4), "best_case_xg": round(max(v.values()), 4),
                     "mean_xg": round(sum(v.values()) / len(v), 4), "strongest_counter": counter,
                     "strongest_counter_label": ctx.strategies[counter].label if counter in ctx.strategies else counter})
    return {"round": ctx.round, "actions": rows,
            "defensive_strategies": [{"strategy_id": s, "label": ctx.strategies[s].label} for s in ctx.all_strategy_ids()]}


# =========================================================================================
# Attacking agent
# =========================================================================================

def attacking_tools(rt: MvRuntime) -> list:
    ctx = rt.ctx

    @tool(name="get_match_state", description="Ball carrier, score, clock and all player positions (world metres).",
          max_invocations=2)
    def get_match_state() -> dict:
        s = ctx.snapshot
        return {"snapshot_id": s.snapshot_id, "carrier": s.ball.possessor_id, "possession": s.possession_team_id,
                "score": s.score, "clock_ms": s.match_clock_ms, "ball": [s.ball.x, s.ball.y],
                "players": [{"id": p.player_id, "team": p.team_id, "x": round(p.x, 1), "y": round(p.y, 1)}
                            for p in s.players]}

    @tool(name="get_available_actions", description="Deterministically generated feasible actions with model features.",
          max_invocations=2)
    def get_available_actions() -> dict:
        if not ctx.generated:
            for c in generate_candidates(ctx.snapshot, ctx.roster):
                ctx.generated[c.action_id] = c
        listed = [{"candidate_id": c.action_id, "label": c.label, "type": c.action_type,
                   "target": c.target_player_id,
                   "features": {k: round(v, 3) for k, v in c.features.items() if k != "through_ball"}}
                  for c in list(ctx.generated.values())[:12]]
        return {"user_selected": ctx.user_action.action_id if ctx.user_action else None,
                "user_selected_label": ctx.user_action.label if ctx.user_action else None,
                "already_proposed": list(ctx.attack_set),
                "tried": list(dict.fromkeys(p.action.action_id for p in ctx.planning.attack_proposals)),
                "candidates": listed}

    @tool(name="get_planning_feedback", description="Response matrix so far: value of each attacking option vs each defence.",
          max_invocations=2)
    def get_planning_feedback() -> dict:
        return _feedback(ctx)

    return [get_match_state, get_available_actions, get_planning_feedback]


def attacking_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_ctx(turn.prompt)
    if "get_available_actions" not in turn.results:
        calls = [("get_available_actions", {})]
        if info.get("round", 1) > 1:
            calls.append(("get_planning_feedback", {}))
        return PolicyDecision(tool_calls=calls)
    av = turn.results["get_available_actions"][-1]
    cands = av["candidates"]
    user = av.get("user_selected")
    proposed = av.get("already_proposed", [])
    tried = set(av.get("tried", [])) | set(proposed)
    if info.get("round", 1) <= 1:
        chosen: list[dict] = []
        if user:
            chosen.append({"candidate_id": user, "rationale": "User-selected action: evaluated as chosen.",
                           "follow_up": ""})
        viable = [c for c in cands if c["features"].get("completion_estimate", c["features"].get("success_estimate", 1)) >= 0.25]
        best_pass = next((c for c in viable if c["type"] == "pass" and c["candidate_id"] != user), None)
        if best_pass:
            f = best_pass["features"]
            chosen.append({"candidate_id": best_pass["candidate_id"],
                           "rationale": f"{best_pass['label']}: completion estimate {f.get('completion_estimate', 0):.2f}, "
                                        f"gains {f.get('forward_gain_m', 0):.1f} m.",
                           "follow_up": "Receiver attacks the box or shoots if space opens."})
        other = next((c for c in viable if c["type"] != "pass" and c["candidate_id"] != user
                      and (c["type"] != "shoot" or c["features"].get("modeled_shot_scoring_probability", 0) > 0.02)), None)
        if other is None:
            other = next((c for c in viable if c["candidate_id"] not in {x["candidate_id"] for x in chosen}), None)
        if other:
            chosen.append({"candidate_id": other["candidate_id"], "rationale": f"{other['label']}: a different kind of threat "
                           "to stretch the defence.", "follow_up": ""})
        return PolicyDecision(final={"proposals": chosen[:MAX_ATTACK], "revised": False, "revision_reason": ""})
    fb = turn.results.get("get_planning_feedback", [{}])[-1]
    rows = {r["candidate_id"]: r for r in fb.get("actions", [])}
    keep = [cid for cid in proposed if cid in rows]
    removable = [cid for cid in keep if cid != user]
    # Tabu: options dropped in earlier rounds are not proposed again (prevents oscillation).
    untried = [c for c in cands if c["candidate_id"] not in tried and c["candidate_id"] != user]
    if not removable or not untried:
        return PolicyDecision(final={"proposals": [{"candidate_id": cid, "rationale": "Kept."} for cid in keep],
                                     "revised": False, "revision_reason": "No better untried option."})
    weakest = min(removable, key=lambda cid: (rows[cid]["worst_case_xg"], rows[cid]["mean_xg"]))
    best_worst = max(rows[cid]["worst_case_xg"] for cid in keep)
    if rows[weakest]["worst_case_xg"] >= best_worst - 0.002:
        # No option is clearly dominated: replanning would not be expected to improve the robust value.
        return PolicyDecision(final={"proposals": [{"candidate_id": cid, "rationale": "Kept."} for cid in keep],
                                     "revised": False, "revision_reason": "No dominated option to replace."})
    counter_labels = {rows[cid]["strongest_counter_label"] for cid in keep}
    covered_targets = {lbl.split(" to ")[-1] for lbl in counter_labels if " to " in lbl} | \
                      {lbl.replace("Track ", "") for lbl in counter_labels if lbl.startswith("Track ")}
    pick = next((c for c in untried if not any(t and t in c["label"] for t in covered_targets)), untried[0])
    new = [cid for cid in keep if cid != weakest] + [pick["candidate_id"]]
    reason = (f"{rows[weakest]['label']} is neutralised by '{rows[weakest]['strongest_counter_label']}' "
              f"(worst case {100 * rows[weakest]['worst_case_xg']:.1f}%); switching to {pick['label']}, which that counter "
              "does not target.")
    return PolicyDecision(final={"proposals": [{"candidate_id": cid, "rationale": "Kept." if cid != pick["candidate_id"]
                                                else reason} for cid in new], "revised": True, "revision_reason": reason})


class AttackingAgentExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="attacking_agent")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[MvSignal]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        if ctx.cancel.is_set():
            await rt.send(wctx, MvSignal("publish", "cancelled"), "attacking_agent", "publisher")
            return
        ctx.round += 1
        ctx.planning.status = "running"
        prompt = ("Propose attacking actions for this decision." +
                  (f" The user selected {ctx.user_action.label}; keep it." if ctx.user_action else "") + "\n" +
                  rt.context_json({}))
        try:
            out, step = await rt.runner.run("attacking_agent", f"Round {ctx.round}: attacking proposals",
                                            mp.ATTACKING, attacking_tools(rt), prompt, AttackPlan, attacking_policy,
                                            ctx.round)
        except AgentFailure as exc:
            ctx.planning.errors.append(f"attacking_agent: {exc}")
            await rt.send(wctx, MvSignal("publish", "attacking agent failed"), "attacking_agent", "publisher")
            return
        if not ctx.generated:
            for c in generate_candidates(ctx.snapshot, ctx.roster):
                ctx.generated[c.action_id] = c
        accepted: list[str] = []
        rejected: list[str] = []
        if ctx.user_action is not None:
            accepted.append(ctx.user_action.action_id)
        for item in out.proposals[: MAX_ATTACK + 1]:
            cid = item.candidate_id
            if cid in accepted:
                continue
            cand = ctx.generated.get(cid)
            if cand is None:
                rejected.append(f"{cid}: not produced by the generator")
                continue
            v = validate_candidate(ctx.snapshot, ctx.roster, cand)
            if not v.ok:
                rejected.append(f"{cid}: {v.code}")
                continue
            if any(action_fingerprint(cand) == action_fingerprint(ctx.action(a)) for a in accepted):
                continue
            accepted.append(cid)
            if not any(p.action.action_id == cid for p in ctx.planning.attack_proposals):
                ctx.planning.attack_proposals.append(AttackProposal(
                    proposal_id=new_id("atk"), round=ctx.round, action=cand, source="attacking_agent",
                    rationale=item.rationale[:300], follow_up=item.follow_up[:200]))
        accepted = accepted[:MAX_ATTACK]
        if ctx.user_action is not None and not any(p.source == "user" for p in ctx.planning.attack_proposals):
            ctx.planning.attack_proposals.insert(0, AttackProposal(
                proposal_id=new_id("atk"), round=ctx.round, action=ctx.user_action, source="user",
                rationale="Selected by the user; never replaced by an agent."))
        ctx.new_attack = set(accepted) != set(ctx.attack_set)
        ctx.attack_set = accepted
        step.output["accepted"] = accepted
        step.output["rejected"] = rejected
        if out.revised and ctx.round > 1:
            step.notes.append(f"Revision: {out.revision_reason[:300]}")
        if not accepted:
            ctx.planning.errors.append("No valid attacking proposal")
            await rt.send(wctx, MvSignal("publish", "no valid attacking proposals"), "attacking_agent", "publisher")
            return
        await rt.emit("attack_proposals", {"round": ctx.round, "actions": [ctx.action(a).label for a in accepted],
                                           "revised": out.revised})
        await rt.send(wctx, MvSignal("defend", f"{len(accepted)} attacking options"), "attacking_agent", "defending_agent")


# =========================================================================================
# Defending agent
# =========================================================================================

def defending_tools(rt: MvRuntime) -> list:
    ctx = rt.ctx

    @tool(name="get_threat_assessment", description="Current attacking proposals with model features (most dangerous first).",
          max_invocations=2)
    def get_threat_assessment() -> dict:
        rows = []
        for aid in ctx.attack_set:
            a = ctx.action(aid)
            rows.append({"candidate_id": aid, "label": a.label, "type": a.action_type, "target": a.target_player_id,
                         "danger": round(a.features.get("heuristic_value", 0.0), 4)})
        rows.sort(key=lambda r: -r["danger"])
        return {"threats": rows}

    @tool(name="get_defensive_options", description="Feasible defensive strategies against the current attacking threats.",
          max_invocations=2)
    def get_defensive_options() -> dict:
        threats = []
        for aid in ctx.attack_set:
            a = ctx.action(aid)
            if a.action_type == "pass" and a.target_player_id:
                threats.append((a.target_player_id, a.target_x or 0.0, a.target_y or 0.0))
        for s in generate_defensive_options(ctx.snapshot, ctx.roster, threats):
            ctx.strategies.setdefault(s.strategy_id, s)
        return {"strategies": [{"strategy_id": s.strategy_id, "label": s.label, "style": s.style,
                                "assignments": [a.model_dump(exclude_none=True) for a in s.assignments]}
                               for s in ctx.strategies.values()]}

    @tool(name="validate_defensive_strategy",
          description="Validate a custom single-defender strategy (role: press, cover_lane or track_runner).",
          max_invocations=3)
    def validate_defensive_strategy(defender_id: str, role: str, target_player_id: str | None = None) -> dict:
        if role not in ("press", "cover_lane", "track_runner"):
            return {"ok": False, "code": "UNKNOWN_ROLE", "message": role}
        ctx.custom_counter += 1
        sid = f"def-custom-{ctx.custom_counter}"
        strat = DefensiveStrategy(strategy_id=sid, style=role, label=f"Custom {role.replace('_', ' ')}",
                                  assignments=[DefensiveAssignment(defender_id=defender_id, role=role,
                                                                   target_player_id=target_player_id)])
        ok, code, msg = validate_strategy(strat, ctx.snapshot, ctx.roster)
        if ok:
            ctx.strategies[sid] = strat
        return {"ok": ok, "code": code, "message": msg, "strategy_id": sid if ok else None}

    @tool(name="get_planning_feedback", description="Response matrix so far.", max_invocations=2)
    def get_planning_feedback() -> dict:
        return _feedback(ctx)

    return [get_threat_assessment, get_defensive_options, validate_defensive_strategy, get_planning_feedback]


def defending_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_ctx(turn.prompt)
    if "get_defensive_options" not in turn.results:
        calls = [("get_threat_assessment", {}), ("get_defensive_options", {})]
        if info.get("round", 1) > 1:
            calls.append(("get_planning_feedback", {}))
        return PolicyDecision(tool_calls=calls)
    threats = turn.results["get_threat_assessment"][-1]["threats"]
    options = {o["strategy_id"]: o for o in turn.results["get_defensive_options"][-1]["strategies"]}
    current = info.get("current_defense", [])
    chosen: list[dict] = []

    def counter_for(t: dict) -> str | None:
        if t["type"] == "pass" and t["target"]:
            for sid in (f"def-cover-{t['target']}", f"def-track-{t['target']}"):
                if sid in options and sid not in [c["strategy_id"] for c in chosen]:
                    return sid
        if t["type"] == "dribble" and "def-press" in options:
            return "def-press"
        if t["type"] == "shoot":
            return "def-press" if "def-press" in options else "def-central"
        return None

    for t in threats:
        sid = counter_for(t)
        if sid and sid not in [c["strategy_id"] for c in chosen]:
            chosen.append({"strategy_id": sid, "targets_candidate_id": t["candidate_id"],
                           "rationale": f"{options[sid]['label']} against {t['label']} (danger {t['danger']:.3f})."})
    if len(chosen) < MAX_DEFENSE and "def-central" in options and "def-central" not in [c["strategy_id"] for c in chosen]:
        chosen.append({"strategy_id": "def-central", "rationale": "Protect the central corridor in front of goal."})
    revised = info.get("round", 1) > 1 and set(c["strategy_id"] for c in chosen[:MAX_DEFENSE]) != set(current)
    return PolicyDecision(final={"strategies": chosen[:MAX_DEFENSE], "revised": revised,
                                 "revision_reason": "New attacking option needs a counter." if revised else ""})


class DefendingAgentExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="defending_agent")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[MvSignal]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        prompt = "Respond to the attacking proposals with defensive strategies.\n" + rt.context_json(
            {"current_defense": ctx.defense_set})
        try:
            out, step = await rt.runner.run("defending_agent", f"Round {ctx.round}: defensive responses",
                                            mp.DEFENDING, defending_tools(rt), prompt, DefensePlan, defending_policy,
                                            ctx.round)
        except AgentFailure as exc:
            ctx.planning.errors.append(f"defending_agent: {exc}")
            await rt.send(wctx, MvSignal("simulate", "defending agent failed: baseline only"), "defending_agent",
                          "simulation_agent")
            return
        if not ctx.strategies:
            for s in generate_defensive_options(ctx.snapshot, ctx.roster, []):
                ctx.strategies.setdefault(s.strategy_id, s)
        accepted, rejected = [], []
        for item in out.strategies[: MAX_DEFENSE + 1]:
            strat = ctx.strategies.get(item.strategy_id)
            if strat is None:
                rejected.append(f"{item.strategy_id}: unknown strategy")
                continue
            ok, code, _ = validate_strategy(strat, ctx.snapshot, ctx.roster)
            if not ok:
                rejected.append(f"{item.strategy_id}: {code}")
                continue
            if item.strategy_id not in accepted and item.strategy_id != BASELINE.strategy_id:
                accepted.append(item.strategy_id)
                if not any(p.strategy.strategy_id == item.strategy_id for p in ctx.planning.defense_proposals):
                    ctx.planning.defense_proposals.append(DefenseProposal(
                        proposal_id=new_id("def"), round=ctx.round, strategy=strat, source="defending_agent",
                        rationale=item.rationale[:300], targets_action_id=item.targets_candidate_id))
        accepted = accepted[:MAX_DEFENSE]
        merged = list(dict.fromkeys(ctx.defense_set + accepted))
        ctx.new_defense = set(merged) != set(ctx.defense_set)
        ctx.defense_set = merged
        step.output["accepted"] = accepted
        step.output["rejected"] = rejected
        await rt.emit("defense_proposals", {"round": ctx.round, "strategies": [ctx.strategies[s].label for s in accepted]})
        await rt.send(wctx, MvSignal("simulate", f"{len(accepted)} defensive responses"), "defending_agent",
                      "simulation_agent")


# =========================================================================================
# Simulation agent (response matrix)
# =========================================================================================

def simulation_tools(rt: MvRuntime) -> list:
    ctx = rt.ctx

    @tool(name="evaluate_response_matrix",
          description="Simulate every attacking option against every defensive response (same snapshot, CRN).",
          max_invocations=2)
    async def evaluate_response_matrix(rollouts_per_cell: int) -> dict:
        n = int(max(30, min(int(rollouts_per_cell), ctx.settings.multiverse_max_cell_rollouts)))
        n = ctx.rollouts_per_cell or n
        ctx.rollouts_per_cell = n
        ctx.planning.rollouts_per_cell = n
        new = 0
        t0 = time.perf_counter()
        for aid in ctx.attack_set:
            for sid in ctx.all_strategy_ids():
                if (aid, sid) in ctx.cells:
                    continue
                if ctx.cancel.is_set():
                    break
                strat = ctx.strategies.get(sid, BASELINE)
                res = await asyncio.to_thread(ctx.evaluator.evaluate, ctx.snapshot, ctx.roster, ctx.action(aid),
                                              None if sid == BASELINE.strategy_id else strat, n, ctx.snapshot.seed,
                                              ctx.horizon_s, ctx.round, ctx.cancel)
                ctx.cells[(aid, sid)] = res
                new += 1
                if res.cell.cached:
                    ctx.planning.cache_hits += 1
                else:
                    ctx.planning.cells_computed += 1
                await rt.emit("cell", {"action": ctx.action(aid).label, "strategy": strat.label,
                                       "xg": res.cell.xg, "cached": res.cell.cached})
        ctx.planning.matrix = [c.cell for c in ctx.cells.values()]
        fb = _feedback(ctx)
        return {"new_cells": new, "rollouts_per_cell": n, "seconds": round(time.perf_counter() - t0, 2),
                "round": ctx.round, "new_attack": ctx.new_attack, "new_defense": ctx.new_defense,
                "max_rounds": ctx.planning.max_rounds, **fb}

    return [evaluate_response_matrix]


def simulation_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_ctx(turn.prompt)
    if "evaluate_response_matrix" not in turn.results:
        return PolicyDecision(tool_calls=[("evaluate_response_matrix", {"rollouts_per_cell": info.get("rollouts", 80)})])
    r = turn.results["evaluate_response_matrix"][-1]
    more = r["round"] < r["max_rounds"] and (r["new_attack"] or r["new_defense"])
    reason = ("New strategies appeared this round; another planning round may change the best response."
              if more else ("Planning converged: no new strategies." if r["round"] < r["max_rounds"]
                            else "Maximum planning rounds reached."))
    return PolicyDecision(final={"cells_evaluated": r["new_cells"], "continue_planning": more, "reason": reason})


def compute_summary(ctx: MvContext, selected_id: str) -> StrategySummary:
    vals = _values(ctx)
    per = {}
    for aid in ctx.attack_set:
        v = vals[aid]
        per[aid] = {"worst": min(v.values()), "best": max(v.values()), "mean": sum(v.values()) / len(v)}
    best_expected = max(per, key=lambda a: (per[a]["mean"], a))
    robust = max(per, key=lambda a: (per[a]["worst"], per[a]["mean"], a))
    upside = max(per, key=lambda a: (per[a]["best"], a))
    sv = vals[selected_id]
    counter = min(sv, key=lambda s: (sv[s], s != BASELINE.strategy_id, s))
    base_v = sv[BASELINE.strategy_id]
    return StrategySummary(best_expected_action_id=best_expected, most_robust_action_id=robust,
                           highest_upside_action_id=upside, selected_action_id=selected_id,
                           defensive_counter_id=counter, selected_value_vs_counter=round(sv[counter], 6),
                           selected_value_vs_baseline=round(base_v, 6),
                           counter_effect_pp=round((sv[counter] - base_v) * 100, 3),
                           per_action={k: {kk: round(vv, 6) for kk, vv in v.items()} for k, v in per.items()})


class SimulationAgentExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="simulation_agent")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[MvSignal]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        prompt = "Evaluate the response matrix and decide whether to plan another round.\n" + rt.context_json(
            {"rollouts": ctx.settings.multiverse_cell_rollouts})
        try:
            out, step = await rt.runner.run("simulation_agent", f"Round {ctx.round}: response matrix",
                                            mp.SIMULATION, simulation_tools(rt), prompt, MatrixReport,
                                            simulation_policy, ctx.round)
        except AgentFailure as exc:
            ctx.planning.errors.append(f"simulation_agent: {exc}")
            await rt.send(wctx, MvSignal("publish", "simulation failed"), "simulation_agent", "publisher")
            return
        missing = [(a, s) for a in ctx.attack_set for s in ctx.all_strategy_ids() if (a, s) not in ctx.cells]
        if missing or ctx.cancel.is_set():
            ctx.planning.errors.append(f"matrix incomplete ({len(missing)} cells)")
            await rt.send(wctx, MvSignal("publish", "matrix incomplete"), "simulation_agent", "publisher")
            return
        summary_now = compute_summary(ctx, ctx.attack_set[0])
        ctx.planning.rounds.append(PlanningRound(
            round=ctx.round, attack_proposal_ids=list(ctx.attack_set), defense_proposal_ids=list(ctx.defense_set),
            new_cells=out.cells_evaluated, best_robust_action_id=summary_now.most_robust_action_id,
            best_robust_value=summary_now.per_action[summary_now.most_robust_action_id]["worst"], note=out.reason[:300]))
        within_budget = ctx.round < ctx.planning.max_rounds
        progressed = ctx.new_attack or ctx.new_defense
        if out.continue_planning and within_budget and progressed:
            await rt.send(wctx, MvSignal("revise", out.reason[:160]), "simulation_agent", "attacking_agent")
            return
        ctx.planning.termination_reason = (out.reason if (within_budget or not out.continue_planning)
                                           else "Maximum planning rounds reached.")
        # Choose the action to realise and its defensive counter, then replay one continuation.
        mode = ctx.planning.mode
        selected = ctx.user_action.action_id if (mode == "manual" and ctx.user_action) else summary_now.most_robust_action_id
        if ctx.user_action is not None and mode != "autonomous":
            selected = ctx.user_action.action_id
        summary = compute_summary(ctx, selected)
        ctx.planning.summary = summary
        if mode != "assisted" or ctx.user_action is not None:
            counter = ctx.strategies.get(summary.defensive_counter_id)
            strat = None if summary.defensive_counter_id == BASELINE.strategy_id else counter
            cell = ctx.cells[(selected, summary.defensive_counter_id)]
            ctx.outcome = await asyncio.to_thread(realize_transition, ctx.snapshot, ctx.roster, ctx.action(selected),
                                                  strat, cell, ctx.sample_kind, ctx.child_snapshot_id,
                                                  ctx.snapshot.seed + len(ctx.node.children) + 1)
        step.output["selected"] = selected
        await rt.send(wctx, MvSignal("verify", ctx.planning.termination_reason[:160]), "simulation_agent",
                      "verification_agent")


# =========================================================================================
# Verification + explanation
# =========================================================================================

def verification_tools(rt: MvRuntime) -> list:
    ctx = rt.ctx

    @tool(name="run_multiverse_checks", description="Deterministic checks on the planning result and transition.",
          max_invocations=2)
    async def run_multiverse_checks() -> dict:
        checks = await asyncio.to_thread(verify_planning, ctx)
        ctx.planning.verification_checks = checks
        failed = [c for c in checks if not c["passed"] and c["severity"] == "error"]
        ctx.planning.verification_status = "rejected" if failed else "verified"
        if not failed:
            ctx.evidence = build_multiverse_evidence(ctx)
        return {"phase": "analysis", "status": ctx.planning.verification_status,
                "failed_errors": [c["check_id"] for c in failed], "passed": sum(c["passed"] for c in checks),
                "total": len(checks), "details": {c["check_id"]: c["details"] for c in failed}}

    @tool(name="verify_narratives", description="Check drafted narratives against the evidence table.",
          max_invocations=2)
    def verify_narratives() -> dict:
        from ..verification.checks import verify_narrative

        allowed = _allowed_players(ctx)
        issues = {}
        for n in ctx.drafts:
            iss = verify_narrative(n, ctx.evidence, ctx.roster, allowed)
            n.verification_status = "rejected" if iss else "verified"
            n.verification_notes = iss
            if iss:
                issues[f"{n.audience}/{n.language}"] = iss
        ctx.narrative_issues = issues
        return {"phase": "narratives", "drafts": len(ctx.drafts), "rejected": issues}

    return [run_multiverse_checks, verify_narratives]


def _allowed_players(ctx: MvContext) -> set[str]:
    out = {ctx.snapshot.ball.possessor_id} if ctx.snapshot.ball.possessor_id else set()
    for aid in ctx.attack_set:
        a = ctx.action(aid)
        if a.target_player_id:
            out.add(a.target_player_id)
    for sid in ctx.defense_set:
        s = ctx.strategies.get(sid)
        if s:
            out |= {x.defender_id for x in s.assignments} | {x.target_player_id for x in s.assignments if x.target_player_id}
    return out


def mv_verification_policy(turn: PolicyTurn) -> PolicyDecision:
    info = parse_ctx(turn.prompt)
    tool_name = "run_multiverse_checks" if info.get("phase") == "analysis" else "verify_narratives"
    if tool_name not in turn.results:
        return PolicyDecision(tool_calls=[(tool_name, {})])
    r = turn.results[tool_name][-1]
    if info.get("phase") == "analysis":
        bad = r.get("failed_errors", [])
        return PolicyDecision(final={"status": "rejected" if bad else "verified",
                                     "route": "unavailable" if bad else "explain",
                                     "issues": [f"{b}: {r['details'].get(b, '')}" for b in bad],
                                     "assessment": f"{r['passed']}/{r['total']} multiverse checks passed"})
    rej = r.get("rejected", {})
    return PolicyDecision(final={"status": "rejected" if rej else "verified", "route": "explain" if rej else "publish",
                                 "issues": [f"{k}: {v[0]}" for k, v in rej.items()],
                                 "assessment": "Narratives grounded" if not rej else "Unsupported claims found"})


class MvVerificationExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="verification_agent")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[MvSignal]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        phase = "narratives" if sig.route == "verify_narratives" else "analysis"
        attempt = sum(1 for s in ctx.planning.steps if s.agent == "verification_agent") + 1
        prompt = f"Verify the multiverse {phase}.\n" + rt.context_json({"phase": phase})
        try:
            out, step = await rt.runner.run("verification_agent", f"Verify {phase}", prompts.VERIFICATION,
                                            verification_tools(rt), prompt, VerificationDecision,
                                            mv_verification_policy, attempt)
        except AgentFailure as exc:
            ctx.planning.errors.append(f"verification_agent: {exc}")
            await rt.send(wctx, MvSignal("publish", "verification failed"), "verification_agent", "publisher")
            return
        if phase == "analysis":
            if not ctx.planning.verification_checks:
                ctx.planning.verification_checks = await asyncio.to_thread(verify_planning, ctx)
            failed = [c for c in ctx.planning.verification_checks if not c["passed"] and c["severity"] == "error"]
            ctx.planning.verification_status = "rejected" if failed else "verified"
            if failed:
                if out.status == "verified":
                    step.notes.append("Agent tried to accept a planning result with failing checks; overridden.")
                ctx.planning.errors.append("verification rejected: " + ", ".join(c["check_id"] for c in failed))
                await rt.send(wctx, MvSignal("publish", "rejected"), "verification_agent", "publisher")
                return
            if not ctx.evidence:
                ctx.evidence = build_multiverse_evidence(ctx)
            await rt.send(wctx, MvSignal("explain", "planning verified"), "verification_agent", "explanation_agent")
            return
        if ctx.narrative_issues and ctx.explanation_retries < 1:
            ctx.explanation_retries += 1
            await rt.send(wctx, MvSignal("explain", "unsupported claims; regenerate"), "verification_agent",
                          "explanation_agent")
            return
        await rt.send(wctx, MvSignal("publish", "narratives checked"), "verification_agent", "publisher")


def explanation_tools(rt: MvRuntime) -> list:
    ctx = rt.ctx

    @tool(name="get_planning_evidence", description="Evidence table for the planning result and transition.",
          max_invocations=2)
    def get_planning_evidence() -> dict:
        return {"evidence": [{"ref": e.ref, "label": e.label, "display": e.display} for e in ctx.evidence],
                "allowed_players": sorted(ctx.roster[p].name for p in _allowed_players(ctx)),
                "requested": [{"audience": a, "language": lang} for lang in ctx.languages
                              for a in ("casual", "analyst", "broadcaster")]}

    return [get_planning_evidence]


def make_mv_explanation_policy(rt: MvRuntime):
    def policy(turn: PolicyTurn) -> PolicyDecision:
        if "get_planning_evidence" not in turn.results:
            return PolicyDecision(tool_calls=[("get_planning_evidence", {})])
        tpl = build_multiverse_narratives(rt.ctx)
        return PolicyDecision(final={"narratives": [
            {"audience": n.audience, "language": n.language, "headline": n.headline, "body": n.body,
             "bullets": n.bullets, "caption": n.caption, "evidence_refs": n.evidence_refs} for n in tpl]})
    return policy


class MvExplanationExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="explanation_agent")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[MvSignal]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        attempt = sum(1 for s in ctx.planning.steps if s.agent == "explanation_agent") + 1
        prompt = ("Explain the decision, the defensive response, any strategy revision and the uncertainty.\n"
                  + rt.context_json({"attempt": attempt}))
        try:
            out, step = await rt.runner.run("explanation_agent", "Explain the tactical trade-off", prompts.EXPLANATION,
                                            explanation_tools(rt), prompt, ExplanationBundle,
                                            make_mv_explanation_policy(rt), attempt)
            live = step.live_model
            label = step.model
        except AgentFailure as exc:
            ctx.planning.errors.append(f"explanation_agent: {exc}")
            out, live, label = ExplanationBundle(narratives=[]), False, "none"
        ctx.drafts = [Narrative(
            narrative_id=new_id("nar"), analysis_id=ctx.planning.planning_id, audience=d.audience, language=d.language,
            headline=d.headline[:140], body=d.body[:1100], bullets=[b[:260] for b in d.bullets[:10]],
            caption=(d.caption or None) and d.caption[:140], evidence_refs=d.evidence_refs[:24],
            generated_by=label if live else "policy-template", is_live_model_output=live,
            created_at=utcnow().isoformat()) for d in out.narratives[:6]]
        await rt.send(wctx, MvSignal("verify_narratives", f"{len(ctx.drafts)} narratives"), "explanation_agent",
                      "verification_agent")


class MvPublisherExecutor(Executor):
    def __init__(self, rt: MvRuntime):
        super().__init__(id="publisher")
        self.rt = rt

    @handler
    async def run(self, sig: MvSignal, wctx: WorkflowContext[Never, MultiversePlanning]) -> None:
        rt, ctx = self.rt, self.rt.ctx
        p = ctx.planning
        verified = p.verification_status == "verified" and p.summary is not None
        if verified:
            good = [n for n in ctx.drafts if n.verification_status == "verified"]
            if len(good) < len(ctx.drafts) or not ctx.drafts:
                have = {(n.audience, n.language) for n in good}
                from ..verification.checks import verify_narrative

                for n in build_multiverse_narratives(ctx):
                    if (n.audience, n.language) in have:
                        continue
                    if not verify_narrative(n, ctx.evidence, ctx.roster, _allowed_players(ctx)):
                        n.verification_status = "verified"
                        good.append(n)
            p.narratives = good
            p.status = "completed"
        else:
            p.status = "cancelled" if ctx.cancel.is_set() else "failed"
            ctx.outcome = None
        p.live_model_calls = rt.runner.live_calls
        p.degraded = p.degraded or rt.runner.policy_fallbacks > 0
        await rt.emit("planning_completed", {"status": p.status})
        await wctx.yield_output(p)


def build_mv_workflow(rt: MvRuntime):
    atk, dfn, sim = AttackingAgentExecutor(rt), DefendingAgentExecutor(rt), SimulationAgentExecutor(rt)
    ver, exp, pub = MvVerificationExecutor(rt), MvExplanationExecutor(rt), MvPublisherExecutor(rt)

    def route(name: str):
        return lambda s: isinstance(s, MvSignal) and s.route == name

    return (
        WorkflowBuilder(start_executor=atk, max_iterations=40, name="parallel-multiverse-adversarial-planning")
        .add_switch_case_edge_group(atk, [Case(condition=route("defend"), target=dfn), Default(target=pub)])
        .add_switch_case_edge_group(dfn, [Case(condition=route("simulate"), target=sim), Default(target=pub)])
        .add_switch_case_edge_group(sim, [Case(condition=route("revise"), target=atk),
                                          Case(condition=route("verify"), target=ver), Default(target=pub)])
        .add_switch_case_edge_group(ver, [Case(condition=route("explain"), target=exp), Default(target=pub)])
        .add_edge(exp, ver)
        .build()
    )


async def run_planning(rt: MvRuntime, timeout_s: float) -> MultiversePlanning:
    rt.ctx.parent_digest = snapshot_digest(rt.ctx.snapshot)
    wf = build_mv_workflow(rt)
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(wf.run(MvSignal("start", "decision")), timeout_s)
        outs = result.get_outputs()
    except TimeoutError:
        rt.ctx.cancel.set()
        rt.planning.status = "timed_out"
        rt.planning.errors.append(f"planning exceeded {timeout_s:.0f} s")
        rt.ctx.outcome = None
        outs = []
    rt.planning.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    return outs[-1] if outs else rt.planning


__all__ = ["MvContext", "MvRuntime", "run_planning", "compute_summary", "g"]

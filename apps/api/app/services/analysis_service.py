"""Analysis jobs: runs the multi-agent workflow in the background, caches verified results.

* Non-blocking: POST returns immediately with a pending analysis; progress is pushed to
  WebSocket subscribers of the match and can be polled.
* Bounded: a semaphore limits concurrent analyses; rollouts and time budgets are capped.
* Cached: verified analyses are cached by (snapshot, rollouts, horizon, simulator version,
  agent mode/deployment). Cached results are clearly labelled `cached=True` on replay.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from ..agents.runner import AgentRunner, ChatClientProvider
from ..config import Settings
from ..models.analysis import AnalyzeRequest, CounterfactualAnalysis, ModelInfo, SimulateRequest
from ..models.common import SIMULATOR_VERSION, Language, new_id, utcnow
from ..models.decisions import DecisionPoint
from ..models.overlay import Overlay
from ..models.simulation import SimulationConfig, SimulationRun, Trajectory
from ..models.workflow import AnalysisWorkflowState
from ..narratives.templates import build_template_narratives
from ..orchestration.workflow import AnalysisContext, AnalysisRuntime, allowed_players, run_workflow
from ..simulation.monte_carlo import REPRESENTATIVE_RULE, evaluate_actions, replay_rollout
from ..verification.checks import verify_narrative
from . import metrics
from .hub import EventHub
from .overlays import analysis_overlays
from .store import Store

log = logging.getLogger("offscript.analysis")


class AnalysisService:
    def __init__(self, settings: Settings, store: Store, hub: EventHub, provider: ChatClientProvider | None = None):
        self.settings = settings
        self.store = store
        self.hub = hub
        self.provider = provider or ChatClientProvider(settings)
        self.sem = asyncio.Semaphore(settings.max_concurrent_analyses)
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancels: dict[str, threading.Event] = {}
        self.trajectory_cache: dict[tuple[str, str, int], Trajectory] = {}
        self.sim_jobs: dict[str, SimulationRun] = {}
        self.recent_starts: list[tuple[float, str, str]] = []

    # ------------------------------------------------------------------ helpers
    def model_info(self) -> ModelInfo:
        mode = self.provider.mode
        return ModelInfo(agent_mode=mode, provider="microsoft-foundry" if mode == "foundry" else "deterministic-policy",
                         deployment=self.settings.foundry_model if mode == "foundry" else None)

    def cache_key(self, decision: DecisionPoint, rollouts: int, horizon: float, languages: list[str]) -> str:
        mi = self.model_info()
        return "|".join([decision.snapshot_id, str(rollouts), f"{horizon:g}", SIMULATOR_VERSION, mi.agent_mode,
                         mi.deployment or "-", ",".join(sorted(languages)), "v3"])

    def budget_info(self, decision: DecisionPoint) -> dict[str, Any]:
        now = time.time()
        recent = [r for r in self.recent_starts if now - r[0] < 300 and r[1] == decision.match_id]
        same_actor = any(r[2] == decision.actor_id for r in recent if now - r[0] < 30)
        limit = 30
        return {"analyses_last_5_min": len(recent), "budget_remaining": max(0, limit - len(recent)),
                "same_actor_analysed_last_30s": same_actor, "max_concurrent": self.settings.max_concurrent_analyses}

    # ------------------------------------------------------------------ API
    def get(self, analysis_id: str) -> CounterfactualAnalysis | None:
        return self.store.analyses.get(analysis_id)

    def overlays(self, analysis_id: str) -> list[Overlay]:
        return self.store.analysis_overlays.get(analysis_id, [])

    async def start(self, decision_id: str, req: AnalyzeRequest) -> CounterfactualAnalysis:
        decision = self.store.decisions.get(decision_id)
        if decision is None:
            raise KeyError(decision_id)
        md = self.store.matches[decision.match_id]
        rollouts = min(req.rollouts or self.settings.default_rollouts, self.settings.max_rollouts)
        horizon = req.horizon_s or self.settings.simulation_horizon_s
        key = self.cache_key(decision, rollouts, horizon, req.languages)
        if not req.fault_injection and not req.force_refresh and self.settings.use_analysis_cache:
            existing_id = self.store.analysis_by_cache_key.get(key)
            if existing_id and existing_id in self.store.analyses:
                a = self.store.analyses[existing_id]
                if a.status in ("pending", "running", "verified"):
                    return a
            cached = self.store.load_cached(key)
            if cached is not None and cached.status == "verified":
                cached = cached.model_copy(update={"cached": True})
                self._register(cached, decision, key)
                self.store.analysis_overlays[cached.analysis_id] = analysis_overlays(
                    cached, decision, str(cached.decision_summary.get("priority", "medium")))
                self.hub.publish(decision.match_id, {"type": "analysis_completed", "analysis_id": cached.analysis_id,
                                                     "decision_point_id": decision_id, "status": cached.status,
                                                     "cached": True})
                return cached
        analysis_id = new_id("analysis")
        corr = new_id("corr")
        state = AnalysisWorkflowState(analysis_id=analysis_id, match_id=decision.match_id,
                                      snapshot_id=decision.snapshot_id, decision_point_id=decision_id,
                                      correlation_id=corr, fault_injection=list(req.fault_injection))
        analysis = CounterfactualAnalysis(analysis_id=analysis_id, match_id=decision.match_id,
                                          decision_point_id=decision_id, snapshot_id=decision.snapshot_id,
                                          correlation_id=corr, status="pending", created_at=utcnow().isoformat(),
                                          workflow=state, model=self.model_info(), cache_key=key,
                                          fault_injection=list(req.fault_injection))
        self._register(analysis, decision, None if req.fault_injection else key)
        cancel = threading.Event()
        self.cancels[analysis_id] = cancel
        self.recent_starts.append((time.time(), decision.match_id, decision.actor_id))
        ctx = AnalysisContext(analysis=analysis, decision=decision, snapshot=md.snapshots[decision.snapshot_id],
                              roster=md.roster, settings=self.settings, rollouts=rollouts, horizon_s=horizon,
                              languages=list(req.languages), budget_info=lambda: self.budget_info(decision),
                              cancel=cancel)
        self.tasks[analysis_id] = asyncio.create_task(self._run(ctx, key, decision))
        self.hub.publish(decision.match_id, {"type": "analysis_started", "analysis_id": analysis_id,
                                             "decision_point_id": decision_id, "correlation_id": corr})
        return analysis

    async def analyse_match(self, match_id: str) -> list[CounterfactualAnalysis]:
        """Start (or reuse from cache) an analysis for every detected decision without a usable one."""
        md = self.store.matches[match_id]
        live = {a.decision_point_id for a in self.store.analyses.values()
                if a.match_id == match_id and not a.fault_injection and a.status in ("pending", "running", "verified")}
        return [await self.start(dp.decision_point_id, AnalyzeRequest())
                for dp in md.decisions if dp.decision_point_id not in live]

    def add_language(self, analysis_id: str, language: Language) -> CounterfactualAnalysis:
        """Adds verified narratives in another language to a finished analysis, without re-running it.

        The narratives come from the deterministic templates, so every number is the same evidence the
        original analysis verified; each one is checked again by the narrative verifier before it is kept.
        """
        a = self.store.analyses[analysis_id]
        if a.status != "verified" or a.simulation is None or a.verification is None:
            return a
        if any(n.language == language for n in a.narratives):
            return a
        decision = self.store.decisions[a.decision_point_id]
        md = self.store.matches[decision.match_id]
        evidence = a.verification.accepted_evidence
        allowed = allowed_players(decision, a, md.snapshots[decision.snapshot_id])
        added = []
        for n in build_template_narratives(a, decision, md.roster, evidence, [language],
                                           generated_by="policy-template (language added on request)"):
            issues = verify_narrative(n, evidence, md.roster, allowed)
            n.verification_status = "rejected" if issues else "verified"
            n.verification_notes = issues
            if not issues:
                added.append(n)
            else:
                log.warning("narrative %s/%s for %s failed verification: %s", n.audience, language, analysis_id, issues)
        with self.store.lock:
            a.narratives = [*a.narratives, *added]
        return a

    def _register(self, a: CounterfactualAnalysis, decision: DecisionPoint, key: str | None) -> None:
        with self.store.lock:
            self.store.analyses[a.analysis_id] = a
            if key:
                self.store.analysis_by_cache_key[key] = a.analysis_id
            if a.analysis_id not in decision.analysis_ids:
                decision.analysis_ids.append(a.analysis_id)

    async def _run(self, ctx: AnalysisContext, key: str, decision: DecisionPoint) -> None:
        a = ctx.analysis
        match_id = decision.match_id

        def publish(kind: str, payload: dict) -> None:
            self.hub.publish(match_id, {"type": "analysis_progress", "event": kind, "decision_point_id":
                                        decision.decision_point_id, **payload})

        t0 = time.perf_counter()
        async with self.sem:
            a.status = "running"
            runner = AgentRunner(self.settings, self.provider, a.workflow, publish,
                                 simulate_outage="model_unavailable" in a.fault_injection)
            rt = AnalysisRuntime(ctx, runner, publish)
            log.info("analysis start", extra={"correlation_id": a.correlation_id, "analysis_id": a.analysis_id,
                                              "match_id": match_id})
            try:
                await run_workflow(rt)
            except Exception as exc:  # never leave a job hanging
                log.exception("analysis crashed")
                a.status = "failed"
                a.workflow.workflow_status = "failed"
                a.workflow.errors.append(f"{type(exc).__name__}: {exc}")
                a.unavailable_reason = "Internal error"
        elapsed = (time.perf_counter() - t0) * 1000
        metrics.record("analysis.end_to_end", elapsed)
        for st in a.workflow.steps:
            if st.duration_ms is not None:
                metrics.record(f"agent.{st.agent}", st.duration_ms)
            for tc in st.tool_calls:
                metrics.record(f"tool.{tc.tool_name}", tc.duration_ms)
        if a.simulation and a.simulation.duration_ms:
            metrics.record("simulation.run", a.simulation.duration_ms)
        self.store.analysis_overlays[a.analysis_id] = rt.ctx.overlays
        if a.status == "verified" and not a.fault_injection:
            try:
                self.store.save_cached(key, a)
            except OSError as exc:
                log.warning("could not write cache: %s", exc)
        self.hub.publish(match_id, {"type": "analysis_completed", "analysis_id": a.analysis_id,
                                    "decision_point_id": decision.decision_point_id, "status": a.status,
                                    "cached": False, "duration_ms": round(elapsed, 1)})
        self.tasks.pop(a.analysis_id, None)

    async def wait(self, analysis_id: str, timeout: float = 300) -> CounterfactualAnalysis | None:
        task = self.tasks.get(analysis_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        return self.get(analysis_id)

    def cancel(self, analysis_id: str) -> bool:
        ev = self.cancels.get(analysis_id)
        if ev is None:
            return False
        ev.set()
        return True

    # ------------------------------------------------------------------ trajectories
    async def trajectory(self, analysis_id: str, action_id: str, rollout_index: int | None = None
                         ) -> Trajectory:
        a = self.get(analysis_id)
        if a is None or a.simulation is None:
            raise KeyError(analysis_id)
        res = next((r for r in a.simulation.results if r.action_id == action_id), None)
        cand = next((c for c in a.candidates if c.action_id == action_id), None)
        if res is None or cand is None:
            raise KeyError(action_id)
        idx = res.representative_rollout if rollout_index is None else int(rollout_index)
        if not 0 <= idx < max(1, res.n_rollouts):
            raise ValueError("rollout index out of range")
        ck = (a.simulation.simulation_run_id, action_id, idx)
        if ck in self.trajectory_cache:
            return self.trajectory_cache[ck]
        md = self.store.matches[a.match_id]
        snap = md.snapshots[a.snapshot_id]
        rule = REPRESENTATIVE_RULE if rollout_index is None else f"Rollout {idx} selected by the viewer"
        traj = await asyncio.to_thread(replay_rollout, snap, md.roster, cand, a.simulation.config, idx,
                                       a.simulation.simulation_run_id, rule)
        self.trajectory_cache[ck] = traj
        return traj

    # ------------------------------------------------------------------ exploratory simulation jobs
    async def simulate(self, analysis_id: str, req: SimulateRequest) -> SimulationRun:
        a = self.get(analysis_id)
        if a is None or not a.candidates:
            raise KeyError(analysis_id)
        md = self.store.matches[a.match_id]
        actions = [c for c in a.candidates if not req.action_ids or c.action_id in req.action_ids or c.is_actual]
        cfg = SimulationConfig(horizon_s=req.horizon_s or self.settings.simulation_horizon_s,
                               rollouts=min(req.rollouts, self.settings.max_rollouts),
                               seed=md.snapshots[a.snapshot_id].seed, time_budget_s=self.settings.simulation_time_budget_s)
        run = SimulationRun(simulation_run_id=new_id("simjob"), analysis_id=analysis_id, snapshot_id=a.snapshot_id,
                            config=cfg, status="pending")
        self.sim_jobs[run.simulation_run_id] = run

        async def _go() -> None:
            run.status = "running"
            run.started_at = utcnow().isoformat()
            t0 = time.perf_counter()
            try:
                async with self.sem:
                    out = await asyncio.to_thread(evaluate_actions, md.snapshots[a.snapshot_id], md.roster, actions, cfg)
                run.results, run.comparisons, run.ranking = out.results, out.comparisons, out.ranking
                run.overall_verdict, run.partial = out.overall_verdict, out.partial
                run.status = "timed_out" if out.timed_out else "completed"
            except Exception as exc:
                run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            run.finished_at = utcnow().isoformat()
            run.duration_ms = round((time.perf_counter() - t0) * 1000, 1)

        asyncio.create_task(_go())
        return run

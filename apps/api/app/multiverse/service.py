"""Football Multiverse sessions: branching trees of simulated futures from one decision.

* Copy-on-write: every child node owns a new immutable snapshot; parents and siblings are never touched.
* Deterministic: a node is fully determined by (parent snapshot, action, defensive counter, seed,
  rollout index); completed nodes store frames/events/proposals so replay needs no model calls.
* Persistent: each session is a JSON document under DATA_DIR/multiverse (survives refresh/restart).
* Bounded: depth, children per node, nodes per session, rounds, rollouts and concurrency are capped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path

import numpy as np

from ..agents.runner import AgentRunner, ChatClientProvider
from ..config import Settings
from ..models.common import new_id, utcnow
from ..models.decisions import CandidateAction
from ..models.events import TrackingFrame
from ..models.multiverse import (
    ActionSpec,
    ActionValidation,
    BranchActionRequest,
    BranchComparison,
    BranchNode,
    MultiverseJob,
    MultiversePlanning,
    MultiverseSession,
    PathStep,
    SessionCreate,
)
from ..models.simulation import SimEvent
from ..services import metrics
from ..services.hub import EventHub
from ..services.store import Store
from ..simulation import geometry as g
from ..simulation.candidates import validate_candidate
from ..simulation.engine import Engine
from ..simulation.rollout import state_from_snapshot
from ..verification.evidence import pct
from .core import CellEvaluator, action_fingerprint
from .workflow import MvContext, MvRuntime, run_planning

log = logging.getLogger("parallel.multiverse")


class MultiverseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class MultiverseService:
    def __init__(self, settings: Settings, store: Store, hub: EventHub, provider: ChatClientProvider):
        self.settings = settings
        self.store = store
        self.hub = hub
        self.provider = provider
        self.sessions: dict[str, MultiverseSession] = {}
        self.jobs: dict[str, MultiverseJob] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancels: dict[str, threading.Event] = {}
        self.evaluator = CellEvaluator()
        self.sem = asyncio.Semaphore(max(1, settings.max_concurrent_analyses))
        self.locks: dict[str, asyncio.Lock] = {}
        self.dir = Path(settings.data_dir) / "multiverse"

    # ------------------------------------------------------------------ persistence
    def _path(self, sid: str) -> Path:
        safe = "".join(ch for ch in sid if ch.isalnum() or ch in "-_")
        return self.dir / f"{safe}.json"

    def persist(self, s: MultiverseSession) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path(s.session_id).with_suffix(".tmp")
            tmp.write_text(s.model_dump_json(), encoding="utf-8")
            tmp.replace(self._path(s.session_id))
        except OSError as exc:  # persistence is best-effort; the in-memory session stays authoritative
            log.warning("could not persist multiverse session: %s", exc)

    def get(self, sid: str) -> MultiverseSession:
        s = self.sessions.get(sid)
        if s is None:
            p = self._path(sid)
            if p.exists():
                try:
                    s = MultiverseSession.model_validate_json(p.read_text(encoding="utf-8"))
                    self.sessions[sid] = s
                except Exception as exc:
                    raise MultiverseError(410, "SESSION_CORRUPT", f"Session could not be restored: {exc}") from exc
        if s is None:
            raise MultiverseError(404, "UNKNOWN_SESSION", f"Unknown multiverse session {sid}")
        return s

    def node(self, sid: str, node_id: str) -> tuple[MultiverseSession, BranchNode]:
        s = self.get(sid)
        n = s.nodes.get(node_id)
        if n is None:
            raise MultiverseError(404, "UNKNOWN_NODE", f"Unknown branch node {node_id}")
        return s, n

    def find_node(self, node_id: str) -> tuple[MultiverseSession, BranchNode]:
        sid = node_id.split("~")[0]
        return self.node(sid, node_id)

    def _lock(self, sid: str) -> asyncio.Lock:
        return self.locks.setdefault(sid, asyncio.Lock())

    # ------------------------------------------------------------------ sessions
    def create_session(self, req: SessionCreate) -> MultiverseSession:
        if len(self.sessions) >= self.settings.multiverse_max_sessions:
            oldest = min(self.sessions.values(), key=lambda x: x.created_at)
            self.sessions.pop(oldest.session_id, None)
        dp = self.store.decisions.get(req.decision_point_id)
        if dp is None:
            raise MultiverseError(404, "UNKNOWN_DECISION", f"Unknown decision {req.decision_point_id}")
        if req.match_id and req.match_id != dp.match_id:
            raise MultiverseError(422, "MATCH_MISMATCH", "Decision does not belong to that match")
        md = self.store.matches[dp.match_id]
        snap = md.snapshots[dp.snapshot_id]
        sid = new_id("mv")
        root_id = f"{sid}~root"
        now = utcnow().isoformat()
        root = BranchNode(node_id=root_id, session_id=sid, parent_node_id=None, depth=0, status="decision", kind="root",
                          snapshot_id=snap.snapshot_id, match_clock_ms=snap.match_clock_ms, sim_time_ms=snap.sim_time_ms,
                          carrier_id=snap.ball.possessor_id, possession_team_id=snap.possession_team_id,
                          score=dict(snap.score), label="Decision", created_at=now)
        s = MultiverseSession(session_id=sid, match_id=dp.match_id, decision_point_id=dp.decision_point_id,
                              root_node_id=root_id, mode=req.mode, created_at=now, seed=snap.seed,
                              max_depth=self.settings.multiverse_max_depth,
                              max_children=self.settings.multiverse_max_children,
                              max_nodes=self.settings.multiverse_max_nodes, actual_action=dp.actual_action,
                              nodes={root_id: root}, snapshots={snap.snapshot_id: snap})
        s.nodes[root_id].children.append(self._observed_node(s, root, md, dp))
        self.sessions[sid] = s
        self.persist(s)
        return s

    def _observed_node(self, s: MultiverseSession, root: BranchNode, md, dp) -> str:
        """The canonical synthetic timeline as a read-only child (never re-simulated)."""
        start = dp.sim_time_ms
        end = (dp.outcome_time_ms or start) + 2500
        frames = [TrackingFrame(t_ms=f.t_ms - start, ball=f.ball, players=f.players, possessor_id=f.possessor_id)
                  for f in md.frames if start <= f.t_ms <= end]
        events = [SimEvent(t_ms=e.sim_time_ms - start, event_type=e.event_type.value, player_ids=e.player_ids,
                           x=e.x or 0.0, y=e.y or 0.0)
                  for e in md.events if start <= e.sim_time_ms <= end and "POSITION" not in e.event_type.value]
        from ..models.multiverse import Transition

        nid = f"{s.session_id}~observed"
        node = BranchNode(
            node_id=nid, session_id=s.session_id, parent_node_id=root.node_id, depth=1, status="terminal",
            kind="observed", snapshot_id=root.snapshot_id, match_clock_ms=dp.match_clock_ms + (end - start),
            sim_time_ms=end, carrier_id=None, possession_team_id=root.possession_team_id, score=dict(root.score),
            entering_action=dp.actual_action, entering_action_source="actual",
            transition=Transition(parent_snapshot_id=root.snapshot_id, child_snapshot_id=None,
                                  action_id=dp.actual_action.action_id, strategy_id="observed",
                                  sample_kind="representative", rollout_index=-1, seed=s.seed,
                                  first_outcome=dp.actual_outcome.lower(), terminal_outcome=dp.actual_outcome.lower(),
                                  duration_ms=end - start, frames=frames, events=events,
                                  selection_rule="Observed synthetic match timeline (not simulated)."),
            label=dp.actual_action.label, outcome_label=dp.actual_outcome, created_at=utcnow().isoformat())
        s.nodes[nid] = node
        return nid

    # ------------------------------------------------------------------ actions
    def validate_action(self, s: MultiverseSession, node: BranchNode, spec: ActionSpec) -> ActionValidation:
        if node.kind == "observed":
            return ActionValidation(ok=False, code="OBSERVED_NODE", message="The observed timeline cannot be branched here; "
                                    "branch from its parent decision.")
        if node.status != "decision":
            return ActionValidation(ok=False, code="NO_DECISION", message=f"Node is {node.status}: no decision available")
        snap = s.snapshots.get(node.snapshot_id)
        if snap is None:
            return ActionValidation(ok=False, code="STATE_MISSING", message="Simulation state expired or missing")
        if snap.ball.possessor_id is None:
            return ActionValidation(ok=False, code="NO_POSSESSION", message="No player has the ball")
        md = self.store.matches[s.match_id]
        roster = md.roster
        actor = snap.ball.possessor_id
        base_id = f"{snap.snapshot_id}-u"
        if spec.candidate_id:
            from ..simulation.candidates import generate_candidates

            cand = next((c for c in generate_candidates(snap, roster) if c.action_id == spec.candidate_id), None)
            if cand is None and spec.candidate_id == s.actual_action.action_id and node.kind == "root":
                cand = s.actual_action
            if cand is None:
                return ActionValidation(ok=False, code="UNKNOWN_CANDIDATE", message="That option is not available here")
            cand = cand.model_copy(update={"source": "agent" if not cand.is_actual else "observed"})
        elif spec.action_type == "shoot":
            cand = CandidateAction(action_id=f"{base_id}-shoot", action_type="shoot", actor_id=actor,
                                   initial_state_id=snap.snapshot_id, label="Shoot", source="agent")
        elif spec.action_type == "pass" and spec.target_player_id:
            t = snap.player(spec.target_player_id)
            if t is None or spec.target_player_id in snap.off_pitch_player_ids:
                return ActionValidation(ok=False, code="TARGET_UNAVAILABLE", message="Target player is not on the pitch")
            if t.team_id != snap.possession_team_id:
                return ActionValidation(ok=False, code="OPPONENT_TARGET", message="That player is an opponent")
            if spec.target_player_id == actor:
                return ActionValidation(ok=False, code="SELF_PASS", message="The ball carrier cannot pass to himself")
            st = state_from_snapshot(snap, roster)
            lp = Engine().lead_point(st, st.index(spec.target_player_id))
            w = g.from_attack_frame(float(lp[0]), float(lp[1]), st.direction)
            cand = CandidateAction(action_id=f"{base_id}-pass-{spec.target_player_id}", action_type="pass", actor_id=actor,
                                   target_player_id=spec.target_player_id, target_x=round(w[0], 2), target_y=round(w[1], 2),
                                   initial_state_id=snap.snapshot_id, label=f"Pass to {roster[spec.target_player_id].short_name}",
                                   source="agent")
        elif spec.action_type == "pass":
            if spec.target_x is None or spec.target_y is None:
                return ActionValidation(ok=False, code="MISSING_TARGET", message="Pick a teammate or a point")
            if not g.in_bounds(spec.target_x, spec.target_y, margin=-1.0):
                return ActionValidation(ok=False, code="TARGET_OFF_PITCH", message="Target outside the pitch")
            st = state_from_snapshot(snap, roster)
            pt = np.array(g.to_attack_frame(spec.target_x, spec.target_y, st.direction))
            mates = [j for j in st.att_idx() if j != st.carrier and not st.is_gk[j]]
            eng = Engine()
            best, best_c = None, -1.0
            for j in mates:
                e = eng.expected_pass(st, st.carrier, int(j), end=pt)
                if e["receiver_margin_s"] > -0.6 and e["completion_est"] > best_c:
                    best, best_c = int(j), e["completion_est"]
            if best is None:
                return ActionValidation(ok=False, code="TARGET_UNREACHABLE",
                                        message="No teammate can reach that space before the ball under the movement model")
            rid = st.profiles[best].player_id
            cand = CandidateAction(action_id=f"{base_id}-space-{round(spec.target_x)}-{round(spec.target_y)}",
                                   action_type="pass", actor_id=actor, target_player_id=rid,
                                   target_x=round(spec.target_x, 2), target_y=round(spec.target_y, 2),
                                   initial_state_id=snap.snapshot_id,
                                   label=f"Pass into space for {roster[rid].short_name}", source="agent")
        elif spec.action_type == "dribble":
            if spec.target_x is None or spec.target_y is None:
                return ActionValidation(ok=False, code="MISSING_TARGET", message="Pick a point to dribble to")
            cand = CandidateAction(action_id=f"{base_id}-dribble-{round(spec.target_x)}-{round(spec.target_y)}",
                                   action_type="dribble", actor_id=actor, target_x=round(spec.target_x, 2),
                                   target_y=round(spec.target_y, 2), initial_state_id=snap.snapshot_id,
                                   label="Dribble", source="agent")
        else:
            return ActionValidation(ok=False, code="INVALID_ACTION", message="Unsupported action")
        v = validate_candidate(snap, roster, cand)
        if not v.ok:
            return ActionValidation(ok=False, code=v.code, message=v.message)
        return ActionValidation(ok=True, code="OK", message="Feasible", action=cand)

    def _check_limits(self, s: MultiverseSession, node: BranchNode) -> None:
        if node.kind == "observed":
            raise MultiverseError(409, "OBSERVED_NODE", "Branch from the decision, not from the observed timeline")
        if node.status != "decision":
            raise MultiverseError(409, "NO_DECISION", f"Node is {node.status}: it has no decision to branch from")
        if node.depth >= s.max_depth:
            raise MultiverseError(409, "DEPTH_LIMIT", f"Maximum branch depth ({s.max_depth}) reached")
        if len([c for c in node.children if s.nodes[c].kind != "observed"]) >= s.max_children:
            raise MultiverseError(409, "TOO_MANY_BRANCHES", f"At most {s.max_children} branches per decision")
        if len(s.nodes) >= s.max_nodes:
            raise MultiverseError(409, "SESSION_FULL", f"At most {s.max_nodes} nodes per session")

    # ------------------------------------------------------------------ jobs
    def _publish(self, sid: str, kind: str, payload: dict) -> None:
        self.hub.publish(f"mv:{sid}", {"type": kind, "session_id": sid, **payload})

    async def start_step(self, sid: str, node_id: str, req: BranchActionRequest) -> MultiverseJob:
        s, node = self.node(sid, node_id)
        mode = req.mode or s.mode
        self._check_limits(s, node)
        user_action: CandidateAction | None = None
        if req.action is not None:
            val = self.validate_action(s, node, req.action)
            if not val.ok:
                raise MultiverseError(422, val.code, val.message)
            user_action = val.action
        elif mode == "manual":
            raise MultiverseError(422, "ACTION_REQUIRED", "Manual mode needs a user-selected action")
        fp = f"{node_id}|{action_fingerprint(user_action) if user_action else 'agent'}|{req.sample_kind}|{mode}"
        for cid in node.children:
            c = s.nodes[cid]
            if c.fingerprint == fp and c.status not in ("failed",):
                job = MultiverseJob(job_id=new_id("mvjob"), session_id=sid, parent_node_id=node_id, child_node_id=cid,
                                    planning_id=c.planning_id, status="completed", progress=["Existing branch reused"],
                                    created_at=utcnow().isoformat())
                self.jobs[job.job_id] = job
                return job
        if mode == "assisted" and user_action is None and node.recommendation_planning_id:
            job = MultiverseJob(job_id=new_id("mvjob"), session_id=sid, parent_node_id=node_id,
                                planning_id=node.recommendation_planning_id, status="completed",
                                progress=["Existing recommendation reused"], created_at=utcnow().isoformat())
            self.jobs[job.job_id] = job
            return job
        job = MultiverseJob(job_id=new_id("mvjob"), session_id=sid, parent_node_id=node_id, status="pending",
                            created_at=utcnow().isoformat())
        self.jobs[job.job_id] = job
        cancel = threading.Event()
        self.cancels[job.job_id] = cancel
        self.tasks[job.job_id] = asyncio.create_task(self._run_step(job, user_action, mode, req, fp, cancel))
        return job

    async def _run_step(self, job: MultiverseJob, user_action: CandidateAction | None, mode: str,
                        req: BranchActionRequest, fp: str, cancel: threading.Event) -> BranchNode | None:
        sid = job.session_id
        t0 = time.perf_counter()

        def progress(kind: str, payload: dict) -> None:
            msg = {
                "agent_started": f"{payload.get('agent', '').replace('_', ' ').title()} working",
                "attack_proposals": "Attacking options proposed",
                "defense_proposals": "Defensive responses proposed",
                "cell": "Running Monte Carlo simulations",
                "handoff": f"Handoff {payload.get('from', '')} -> {payload.get('to', '')}",
                "planning_completed": "Planning finished",
            }.get(kind)
            if msg and (not job.progress or job.progress[-1] != msg):
                job.progress.append(msg)
            self._publish(sid, "progress", {"job_id": job.job_id, "event": kind, **{k: v for k, v in payload.items()
                                                                                     if k != "planning_id"}})

        async with self.sem:
            job.status = "running"
            async with self._lock(sid):
                s, node = self.node(sid, job.parent_node_id)
                snap = s.snapshots[node.snapshot_id]
                child_n = len(s.nodes)
                child_id = f"{sid}~n{child_n:03d}"
                child_snap_id = f"{sid}-s{child_n:03d}"
            md = self.store.matches[s.match_id]
            planning = MultiversePlanning(planning_id=new_id("plan"), node_id=node.node_id, snapshot_id=snap.snapshot_id,
                                          correlation_id=new_id("corr"), mode=mode,
                                          max_rounds=req.max_rounds or self.settings.multiverse_max_rounds,
                                          user_action_id=user_action.action_id if user_action else None)
            job.planning_id = planning.planning_id
            s.plannings[planning.planning_id] = planning
            actual = s.actual_action if node.kind == "root" else None
            ctx = MvContext(node=node, snapshot=snap, roster=md.roster, settings=self.settings, planning=planning,
                            evaluator=self.evaluator, user_action=user_action, actual_action=actual,
                            sample_kind=req.sample_kind, child_snapshot_id=child_snap_id,
                            rollouts_per_cell=0, horizon_s=self.settings.simulation_horizon_s, languages=["en", "nl"],
                            cancel=cancel)
            runner = AgentRunner(self.settings, self.provider, planning, progress)
            rt = MvRuntime(ctx, runner, progress)
            try:
                planning = await run_planning(rt, self.settings.multiverse_timeout_s)
            except Exception as exc:
                log.exception("multiverse planning crashed")
                planning.status = "failed"
                planning.errors.append(f"{type(exc).__name__}: {exc}")
                ctx.outcome = None
        metrics.record("multiverse.planning", (time.perf_counter() - t0) * 1000)
        async with self._lock(sid):
            s = self.get(sid)
            parent = s.nodes[job.parent_node_id]
            child: BranchNode | None = None
            if planning.status == "completed" and mode == "assisted" and user_action is None:
                parent.recommendation_planning_id = planning.planning_id
                job.status = "completed"
            elif planning.status == "completed" and ctx.outcome is not None:
                t = ctx.outcome.transition
                cs = ctx.outcome.child_snapshot
                s.snapshots[cs.snapshot_id] = cs
                depth = parent.depth + 1
                if t.terminal_outcome is not None:
                    status = "terminal"
                elif depth >= s.max_depth:
                    status = "depth_limit"
                else:
                    status = "decision"
                sel = ctx.action(planning.summary.selected_action_id)
                strat = ctx.strategies.get(t.strategy_id)
                child = BranchNode(
                    node_id=child_id, session_id=sid, parent_node_id=parent.node_id, depth=depth, status=status,
                    snapshot_id=cs.snapshot_id, match_clock_ms=cs.match_clock_ms, sim_time_ms=cs.sim_time_ms,
                    carrier_id=cs.ball.possessor_id if t.terminal_outcome is None else None,
                    possession_team_id=cs.possession_team_id, score=dict(cs.score), entering_action=sel,
                    entering_action_source="user" if user_action is not None else "attacking_agent",
                    entering_strategy=strat, transition=t, planning_id=planning.planning_id,
                    label=sel.label.replace(" (actual)", ""), outcome_label=(t.terminal_outcome or t.first_outcome),
                    created_at=utcnow().isoformat(), fingerprint=fp)
                s.nodes[child_id] = child
                parent.children.append(child_id)
                job.child_node_id = child_id
                job.status = "completed"
            else:
                job.status = "cancelled" if cancel.is_set() else ("timed_out" if planning.status == "timed_out" else "failed")
                job.error = "; ".join(planning.errors)[-400:] or planning.status
            self.persist(s)
        metrics.record("multiverse.branch_creation", (time.perf_counter() - t0) * 1000)
        self._publish(sid, "job_completed", {"job_id": job.job_id, "status": job.status,
                                             "child_node_id": job.child_node_id, "planning_id": job.planning_id})
        self.tasks.pop(job.job_id, None)
        return child

    async def auto_play(self, sid: str, node_id: str, max_steps: int, sample_kind: str) -> MultiverseJob:
        s, node = self.node(sid, node_id)
        self._check_limits(s, node)
        job = MultiverseJob(job_id=new_id("mvjob"), session_id=sid, parent_node_id=node_id, status="running",
                            created_at=utcnow().isoformat())
        self.jobs[job.job_id] = job
        cancel = threading.Event()
        self.cancels[job.job_id] = cancel

        async def loop() -> None:
            current = node_id
            for k in range(max_steps):
                if cancel.is_set():
                    job.status = "cancelled"
                    break
                ss, cur = self.node(sid, current)
                if cur.status != "decision" or cur.depth >= ss.max_depth:
                    break
                step_job = await self.start_step(sid, current, BranchActionRequest(mode="autonomous",
                                                                                    sample_kind=sample_kind))
                job.progress.append(f"Step {k + 1}: planning")
                t = self.tasks.get(step_job.job_id)
                if t is not None:
                    await t
                if step_job.status != "completed" or not step_job.child_node_id:
                    job.status = "failed"
                    job.error = step_job.error
                    break
                current = step_job.child_node_id
                job.child_node_id = current
                job.progress.append(f"Step {k + 1}: {self.node(sid, current)[1].label}")
            if job.status == "running":
                job.status = "completed"
            self._publish(sid, "job_completed", {"job_id": job.job_id, "status": job.status,
                                                 "child_node_id": job.child_node_id})

        self.tasks[job.job_id] = asyncio.create_task(loop())
        return job

    def cancel(self, job_id: str) -> bool:
        ev = self.cancels.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True

    async def wait(self, job_id: str, timeout: float = 600) -> MultiverseJob:
        t = self.tasks.get(job_id)
        if t is not None:
            await asyncio.wait_for(asyncio.shield(t), timeout)
        return self.jobs[job_id]

    # ------------------------------------------------------------------ reads
    def lineage(self, s: MultiverseSession, node_id: str) -> list[BranchNode]:
        out = []
        cur: str | None = node_id
        while cur is not None:
            n = s.nodes[cur]
            out.append(n)
            cur = n.parent_node_id
        return list(reversed(out))

    def path_frames(self, s: MultiverseSession, node_id: str) -> dict:
        """Concatenated frames/events from the root decision to `node_id` (time continues across steps)."""
        frames: list[dict] = []
        events: list[dict] = []
        offset = 0
        nodes = self.lineage(s, node_id)
        root_snap = s.snapshots[nodes[0].snapshot_id]
        frames.append({"t_ms": 0, "ball": [root_snap.ball.x, root_snap.ball.y, 0.0],
                       "players": {p.player_id: [p.x, p.y] for p in root_snap.players},
                       "possessor_id": root_snap.ball.possessor_id})
        boundaries = []
        for n in nodes[1:]:
            t = n.transition
            if t is None:
                continue
            for f in t.frames:
                if f.t_ms == 0 and frames:
                    continue
                d = f.model_dump()
                d["t_ms"] = f.t_ms + offset
                frames.append(d)
            for e in t.events:
                d = e.model_dump()
                d["t_ms"] = e.t_ms + offset
                d["node_id"] = n.node_id
                events.append(d)
            offset += t.duration_ms
            boundaries.append({"node_id": n.node_id, "t_ms": offset, "label": n.label, "outcome": n.outcome_label,
                               "kind": n.kind})
        return {"node_id": node_id, "duration_ms": offset, "frames": frames, "events": events, "boundaries": boundaries,
                "simulated": any(n.kind == "simulated" for n in nodes)}

    def tree(self, s: MultiverseSession) -> dict:
        nodes = []
        for n in s.nodes.values():
            pl = s.plannings.get(n.planning_id) if n.planning_id else None
            nodes.append({
                "node_id": n.node_id, "parent_node_id": n.parent_node_id, "depth": n.depth, "status": n.status,
                "kind": n.kind, "label": n.label, "outcome": n.outcome_label, "children": n.children,
                "match_clock_ms": n.match_clock_ms, "source": n.entering_action_source,
                "strategy": n.entering_strategy.label if n.entering_strategy else None,
                "value_vs_counter": pl.summary.selected_value_vs_counter if pl and pl.summary else None,
                "verification": pl.verification_status if pl else None,
                "sample_kind": n.transition.sample_kind if n.transition else None,
            })
        return {"session_id": s.session_id, "root_node_id": s.root_node_id, "nodes": nodes,
                "max_depth": s.max_depth, "mode": s.mode}

    def _steps(self, s: MultiverseSession, node_id: str) -> list[PathStep]:
        out = []
        for n in self.lineage(s, node_id)[1:]:
            pl = s.plannings.get(n.planning_id) if n.planning_id else None
            out.append(PathStep(node_id=n.node_id, depth=n.depth, action_label=n.label,
                                action_source=n.entering_action_source,
                                strategy_label=n.entering_strategy.label if n.entering_strategy else
                                ("balanced shape" if n.kind == "simulated" else None),
                                first_outcome=n.transition.first_outcome if n.transition else None,
                                terminal_outcome=n.transition.terminal_outcome if n.transition else None,
                                match_clock_ms=n.match_clock_ms,
                                p_goal_vs_counter=pl.summary.selected_value_vs_counter if pl and pl.summary else None))
        return out

    def compare(self, a_id: str, b_id: str, lang: str = "en") -> BranchComparison:
        sa, a = self.find_node(a_id)
        sb, b = self.find_node(b_id)
        if sa.session_id != sb.session_id:
            raise MultiverseError(422, "DIFFERENT_SESSIONS", "Both branches must belong to one session")
        la = [n.node_id for n in self.lineage(sa, a_id)]
        lb = [n.node_id for n in self.lineage(sa, b_id)]
        common = [x for x, y in zip(la, lb, strict=False) if x == y][-1]
        steps_a, steps_b = self._steps(sa, a_id), self._steps(sa, b_id)

        def metrics_for(node: BranchNode, steps: list[PathStep]) -> dict:
            pf = self.path_frames(sa, node.node_id)
            first_val = steps[0].p_goal_vs_counter if steps else None
            terminal = node.transition.terminal_outcome if node.transition else None
            turnovers = sum(1 for e in pf["events"] if e["event_type"] in ("INTERCEPTION", "TACKLE"))
            shots = sum(1 for e in pf["events"] if e["event_type"] == "SHOT_ATTEMPTED")
            return {"final_outcome": terminal or node.status, "elapsed_s": round(pf["duration_ms"] / 1000, 1),
                    "steps": len(steps), "shots": shots, "turnovers": turnovers,
                    "first_step_xg_vs_counter": first_val, "kind": node.kind,
                    "goals": 1 if terminal == "goal" else 0}

        ma, mb = metrics_for(a, steps_a), metrics_for(b, steps_b)
        name = {sa.root_node_id: "the original decision"}
        an, bn = (" -> ".join(s.action_label or "?" for s in steps_a), " -> ".join(s.action_label or "?" for s in steps_b))
        if lang == "nl":
            expl = (f"Beide takken starten bij {name.get(common, 'dezelfde beslissing')} met dezelfde bevroren toestand. "
                    f"Tak A ({an}) eindigt na {ma['elapsed_s']} s met {ma['final_outcome']}; tak B ({bn}) na "
                    f"{mb['elapsed_s']} s met {mb['final_outcome']}. ")
        else:
            expl = (f"Both branches start from {name.get(common, 'the same decision')} with the same frozen state. "
                    f"Branch A ({an}) ends after {ma['elapsed_s']} s with {ma['final_outcome']}; branch B ({bn}) after "
                    f"{mb['elapsed_s']} s with {mb['final_outcome']}. ")
        va, vb = ma["first_step_xg_vs_counter"], mb["first_step_xg_vs_counter"]
        if va is not None and vb is not None:
            if lang == "nl":
                expl += (f"Tegen het beste verdedigende antwoord gaf het model de eerste stap van A {pct(va, 'nl')} en die "
                         f"van B {pct(vb, 'nl')} verwachte doelpunten binnen 10 s. ")
            else:
                expl += (f"Against the defence's best counter the model gave A's first step {pct(va)} and B's {pct(vb)} "
                         f"expected goals within 10 s. ")
        expl += ("Getoonde vervolgen zijn steekproeven uit een model, geen zekerheden." if lang == "nl" else
                 "The shown continuations are samples from a model, not certainties.")
        return BranchComparison(node_a=a_id, node_b=b_id, common_ancestor=common, steps_a=steps_a, steps_b=steps_b,
                                metrics_a=ma, metrics_b=mb, explanation=expl,
                                evidence_refs=[x for x in (a.planning_id, b.planning_id) if x])

    def recommendation(self, s: MultiverseSession, node: BranchNode) -> MultiversePlanning | None:
        return s.plannings.get(node.recommendation_planning_id) if node.recommendation_planning_id else None


def dumps_tree(tree: dict) -> str:
    return json.dumps(tree)

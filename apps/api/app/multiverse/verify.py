"""Deterministic verification of an adversarial planning result (cannot be overridden by agents)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..models.simulation import SimulationConfig
from ..simulation.candidates import validate_candidate
from ..simulation.defense import BASELINE, build_runtime, validate_strategy
from ..simulation.monte_carlo import rollout_rng, wilson
from ..simulation.rollout import resolve_candidate, run_first_action, state_from_snapshot
from .core import snapshot_digest

if TYPE_CHECKING:
    from .workflow import MvContext


def _c(cid: str, name: str, ok: bool, details: str = "", severity: str = "error") -> dict:
    return {"check_id": cid, "name": name, "passed": bool(ok), "details": details, "severity": severity}


def verify_planning(ctx: MvContext) -> list[dict]:
    from .workflow import compute_summary

    checks: list[dict] = []
    snap = ctx.snapshot
    acts = [ctx.action(a) for a in ctx.attack_set]
    checks.append(_c("same_snapshot", "Every attacking option starts from the node's frozen snapshot",
                     all(a.initial_state_id == snap.snapshot_id for a in acts), snap.snapshot_id))
    bad = [f"{a.action_id}: {v.code}" for a in acts if not (v := validate_candidate(snap, ctx.roster, a)).ok]
    checks.append(_c("actions_valid", "Every attacking option is feasible", not bad, "; ".join(bad) or f"{len(acts)} valid"))
    bad_s = []
    for sid in ctx.defense_set:
        s = ctx.strategies.get(sid)
        if s is None:
            bad_s.append(f"{sid}: unknown")
            continue
        ok, code, _ = validate_strategy(s, snap, ctx.roster)
        if not ok:
            bad_s.append(f"{sid}: {code}")
    checks.append(_c("strategies_valid", "Every defensive response is valid and physically reachable", not bad_s,
                     "; ".join(bad_s) or f"{len(ctx.defense_set)} valid + balanced baseline"))
    sids = ctx.all_strategy_ids()
    missing = [(a, s) for a in ctx.attack_set for s in sids if (a, s) not in ctx.cells]
    checks.append(_c("matrix_complete", "Every option was simulated against every response", not missing,
                     f"{len(ctx.attack_set)} x {len(sids)} cells" if not missing else f"missing {missing[:3]}"))
    ns = {ctx.cells[k].cell.n_rollouts for k in ctx.cells}
    seeds = {ctx.cells[k].seed for k in ctx.cells}
    checks.append(_c("equal_budget", "Equal rollouts per cell and one seed schedule (common random numbers)",
                     len(ns) == 1 and len(seeds) == 1, f"rollouts={sorted(ns)}, seeds={sorted(seeds)}"))
    num = []
    for (a, s), r in ctx.cells.items():
        c = r.cell
        if not (0 <= c.xg_ci95_low <= c.xg + 1e-9 and c.xg <= c.xg_ci95_high + 1e-9 and c.xg_ci95_high <= 1):
            num.append(f"{a}/{s}: xg interval")
        xs = np.array([x.shot_goal_prob if x.shot_time is not None else 0.0 for x in r.summaries])
        if len(xs) and abs(float(xs.mean()) - c.xg) > 1e-5:
            num.append(f"{a}/{s}: xg != mean of rollouts")
        for est in (c.p_goal, c.p_shot, c.p_turnover):
            w = wilson(est.successes, est.trials)
            if abs(w.value - est.value) > 1e-5 or abs(w.ci95_high - est.ci95_high) > 1e-5:
                numberr = f"{a}/{s}: Wilson mismatch"
                num.append(numberr)
    checks.append(_c("values_consistent", "Values, intervals and rollout records agree", not num,
                     "; ".join(num[:5]) or "all consistent"))
    if ctx.planning.summary is not None and not missing:
        ref = compute_summary(ctx, ctx.planning.summary.selected_action_id)
        same = ref.model_dump() == ctx.planning.summary.model_dump()
        checks.append(_c("summary_consistent", "Best / robust / upside / counter recomputed from the matrix", same,
                         f"counter={ref.defensive_counter_id}"))
    if ctx.user_action is not None and ctx.planning.summary is not None:
        checks.append(_c("user_action_respected", "The user's action was evaluated and realised unchanged",
                         ctx.planning.summary.selected_action_id == ctx.user_action.action_id
                         and ctx.user_action.action_id in ctx.attack_set, ctx.user_action.label))
    checks.append(_c("rounds_bounded", "Planning rounds within the configured limit",
                     ctx.round <= ctx.planning.max_rounds, f"{ctx.round}/{ctx.planning.max_rounds}"))
    checks.append(_c("parent_immutable", "The parent snapshot is unchanged",
                     snapshot_digest(snap) == ctx.parent_digest, ctx.parent_digest))
    if ctx.outcome is not None:
        t = ctx.outcome.transition
        strat = None if t.strategy_id == BASELINE.strategy_id else ctx.strategies.get(t.strategy_id)
        base = state_from_snapshot(snap, ctx.roster)
        act = ctx.action(t.action_id)
        rng = rollout_rng(SimulationConfig(rollouts=max(1, ctx.rollouts_per_cell), seed=t.seed), act.action_id,
                          t.rollout_index)
        again = run_first_action(base, resolve_candidate(base, snap, act), rng, record=True,
                                 defense=build_runtime(strat, snap))
        same = (again.phase.outcome == t.first_outcome and len(again.frames) == len(t.frames)
                and (not t.frames or again.frames[-1] == t.frames[-1]))
        checks.append(_c("transition_reproducible", "The realised continuation replays identically from its seed",
                         same, f"rollout {t.rollout_index}: {t.first_outcome}"))
        cs = ctx.outcome.child_snapshot
        inside = all(-1 <= p.x <= 106 and -1 <= p.y <= 69 for p in cs.players)
        later = cs.sim_time_ms > snap.sim_time_ms
        consistent = (t.terminal_outcome is None) == (cs.ball.possessor_id is not None and
                                                       cs.possession_team_id == snap.possession_team_id)
        checks.append(_c("successor_valid", "Successor state is valid (in bounds, later, possession consistent)",
                         inside and later and consistent,
                         f"t+{cs.sim_time_ms - snap.sim_time_ms} ms, possessor {cs.ball.possessor_id}"))
    return checks

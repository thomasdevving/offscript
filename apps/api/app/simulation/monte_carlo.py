"""Monte Carlo evaluation of candidate actions from one frozen snapshot.

Primary metric (identical for every candidate):

    P(goal within H seconds | snapshot, first action)

estimated as goals / rollouts with a Wilson 95% interval. The interval describes Monte
Carlo sampling error only; it says nothing about whether the football model itself is
right.

Fairness: all candidates start from the same snapshot, use the same horizon and the same
rollout count, and rollout *i* of every candidate uses the same random streams (common
random numbers). Rollouts are interleaved (rollout-major order) so that a time-budget
cut-off leaves every candidate with the same number of samples.
"""

from __future__ import annotations

import math
import threading
import time
import zlib
from collections import Counter
from dataclasses import dataclass

import numpy as np

from ..models.decisions import CandidateAction
from ..models.match import Player
from ..models.simulation import (
    ROLLOUT_OUTCOMES,
    ActionResult,
    ComparisonVerdict,
    PairwiseComparison,
    ProbabilityEstimate,
    SimulationConfig,
    Trajectory,
)
from ..models.state import MatchStateSnapshot
from . import geometry as g
from .engine import Engine, RolloutRng
from .rollout import RolloutSummary, resolve_candidate, run_rollout, state_from_snapshot

EQUIVALENCE_MARGIN = 0.03
REPRESENTATIVE_RULE = (
    "Medoid of the most frequent outcome: among rollouts whose outcome equals the modal outcome, the one "
    "minimising the summed distance to the others in (end time, final ball x, final ball y, number of actions) space."
)


def rollout_rng(config: SimulationConfig, action_id: str, rollout_index: int) -> RolloutRng:
    """Random streams for rollout `rollout_index`.

    With common random numbers every action shares the streams of a given index; without,
    each action gets its own seed derived deterministically from its id.
    """
    seed = config.seed if config.common_random_numbers else (config.seed ^ zlib.crc32(action_id.encode()))
    return RolloutRng(seed, rollout_index)


def wilson(successes: int, trials: int, z: float = 1.96) -> ProbabilityEstimate:
    if trials <= 0:
        return ProbabilityEstimate(value=0.0, ci95_low=0.0, ci95_high=1.0, successes=0, trials=0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return ProbabilityEstimate(
        value=round(p, 6),
        ci95_low=round(max(0.0, centre - half), 6),
        ci95_high=round(min(1.0, centre + half), 6),
        successes=successes,
        trials=trials,
    )


def paired_difference(a: np.ndarray, b: np.ndarray, z: float = 1.96) -> tuple[float, float, float]:
    """Mean and normal-approximation CI of a - b for paired binary samples."""
    d = a.astype(float) - b.astype(float)
    n = len(d)
    if n == 0:
        return 0.0, -1.0, 1.0
    mean = float(d.mean())
    sd = float(d.std(ddof=1)) if n > 1 else 0.0
    half = z * sd / math.sqrt(n)
    return mean, mean - half, mean + half


def verdict_for(diff: float, lo: float, hi: float) -> ComparisonVerdict:
    if lo > 0:
        return "more_promising"
    if hi < 0:
        return "less_promising"
    if max(abs(lo), abs(hi)) < EQUIVALENCE_MARGIN:
        return "similar"
    return "inconclusive"


@dataclass
class EvaluationOutput:
    results: list[ActionResult]
    comparisons: list[PairwiseComparison]
    ranking: list[str]
    overall_verdict: ComparisonVerdict | None
    partial: bool
    completed_rollouts: int
    elapsed_s: float
    timed_out: bool
    cancelled: bool
    summaries: list[list[RolloutSummary]] | None = None


def _medoid(summaries: list[RolloutSummary], idxs: list[int], horizon: float) -> int:
    if len(idxs) == 1:
        return idxs[0]
    feats = np.array([[summaries[i].t_end / horizon, summaries[i].end_ball[0] / g.PITCH_LENGTH,
                       summaries[i].end_ball[1] / g.PITCH_WIDTH, summaries[i].n_actions / 4.0] for i in idxs])
    if len(idxs) > 300:
        feats = feats[:300]
        idxs = idxs[:300]
    d = np.linalg.norm(feats[:, None, :] - feats[None, :, :], axis=2).sum(axis=1)
    return idxs[int(np.argmin(d))]


def evaluate_actions(
    snapshot: MatchStateSnapshot,
    roster: dict[str, Player],
    actions: list[CandidateAction],
    config: SimulationConfig,
    cancel: threading.Event | None = None,
    progress: callable | None = None,
    baseline_action_id: str | None = None,
    defense=None,
    conditional_shots: int = 0,
) -> EvaluationOutput:
    """Evaluate `actions` from `snapshot`; `defense` is an optional DefenseRuntime (same for all actions)."""
    started = time.perf_counter()
    base = state_from_snapshot(snapshot, roster)
    resolved = [resolve_candidate(base, snapshot, a) for a in actions]
    summaries: list[list[RolloutSummary]] = [[] for _ in actions]
    timed_out = cancelled = False
    done = 0
    for i in range(config.rollouts):
        if cancel is not None and cancel.is_set():
            cancelled = True
            break
        if time.perf_counter() - started > config.time_budget_s:
            timed_out = True
            break
        for k, act in enumerate(resolved):
            rng = rollout_rng(config, actions[k].action_id, i)
            s, _, _ = run_rollout(base, act, rng, config.horizon_s, record=False, defense=defense,
                                  conditional_shots=conditional_shots)
            summaries[k].append(s)
        done += 1
        if progress is not None and (done % 25 == 0):
            progress(done, config.rollouts)

    engine = Engine()
    results: list[ActionResult] = []
    goal_vectors: dict[str, np.ndarray] = {}
    shot_vectors: dict[str, np.ndarray] = {}
    turnover_vectors: dict[str, np.ndarray] = {}
    for k, action in enumerate(actions):
        sm = summaries[k]
        n = len(sm)
        counts = Counter(s.outcome for s in sm)
        goals = counts.get("goal", 0)
        shots = sum(1 for s in sm if s.shot_time is not None)
        turnovers = counts.get("turnover", 0)
        firsts = sum(1 for s in sm if s.first_success)
        shot_times = [s.shot_time for s in sm if s.shot_time is not None]
        goal_vectors[action.action_id] = np.array([s.outcome == "goal" for s in sm], dtype=bool)
        shot_vectors[action.action_id] = np.array([s.shot_time is not None for s in sm], dtype=bool)
        turnover_vectors[action.action_id] = np.array([s.outcome == "turnover" for s in sm], dtype=bool)
        modal = max(ROLLOUT_OUTCOMES, key=lambda o: (counts.get(o, 0), -ROLLOUT_OUTCOMES.index(o))) if n else "retained"
        rep = _medoid(sm, [i for i, s in enumerate(sm) if s.outcome == modal], config.horizon_s) if n else 0
        examples = {}
        for o in ROLLOUT_OUTCOMES:
            ids = [i for i, s in enumerate(sm) if s.outcome == o]
            if ids:
                examples[o] = _medoid(sm, ids, config.horizon_s)
        detail: dict[str, float] = {}
        ra = resolved[k]
        if ra.action_type == "shoot":
            detail["modeled_shot_scoring_probability"] = round(engine.shot_probability(base, ra.actor, 1000,
                                                                                       seed=config.seed), 4)
            sc = engine.shot_components(base, ra.actor)
            detail.update({k2: round(v, 3) for k2, v in sc.items()})
        elif ra.action_type == "pass" and ra.receiver is not None:
            e = engine.expected_pass(base, ra.actor, ra.receiver)
            detail.update({"pass_length_m": round(e["length_m"], 2), "ball_speed_mps": round(e["ball_speed_mps"], 2),
                           "flight_time_s": round(e["flight_time_s"], 3),
                           "lane_best_defender_margin_s": round(e["lane_best_defender_margin_s"], 3)})
        elif ra.action_type == "dribble" and ra.target is not None:
            e = engine.expected_dribble(base, ra.actor, ra.target)
            detail.update({"dribble_length_m": round(e["length_m"], 2), "duels_expected": e["duels"]})
        results.append(
            ActionResult(
                action_id=action.action_id,
                n_rollouts=n,
                p_goal=wilson(goals, n),
                p_shot=wilson(shots, n),
                p_turnover=wilson(turnovers, n),
                p_first_action_success=wilson(firsts, n),
                mean_time_to_shot_s=round(float(np.mean(shot_times)), 3) if shot_times else None,
                mean_progression_m=round(float(np.mean([s.progression for s in sm])), 3) if n else 0.0,
                outcome_distribution={o: round(counts.get(o, 0) / n, 6) if n else 0.0 for o in ROLLOUT_OUTCOMES},
                outcome_counts={o: counts.get(o, 0) for o in ROLLOUT_OUTCOMES},
                representative_rollout=rep,
                representative_outcome=modal,
                example_rollouts=examples,
                first_action_detail=detail,
            )
        )

    baseline = baseline_action_id or next((a.action_id for a in actions if a.is_actual), actions[0].action_id)
    comparisons: list[PairwiseComparison] = []
    for a in actions:
        if a.action_id == baseline:
            continue
        diff, lo, hi = paired_difference(goal_vectors[a.action_id], goal_vectors[baseline])
        sd, slo, shi = paired_difference(shot_vectors[a.action_id], shot_vectors[baseline])
        td, tlo, thi = paired_difference(turnover_vectors[a.action_id], turnover_vectors[baseline])
        notes = []
        if slo > 0:
            notes.append("creates a shot more often")
        elif shi < 0:
            notes.append("creates a shot less often")
        if tlo > 0:
            notes.append("loses the ball more often")
        elif thi < 0:
            notes.append("loses the ball less often")
        comparisons.append(PairwiseComparison(
            action_id=a.action_id, baseline_action_id=baseline, diff_p_goal=round(diff, 6),
            diff_ci95_low=round(lo, 6), diff_ci95_high=round(hi, 6), paired=config.common_random_numbers,
            verdict=verdict_for(diff, lo, hi),
            diff_p_shot=round(sd, 6), diff_p_shot_ci95_low=round(slo, 6), diff_p_shot_ci95_high=round(shi, 6),
            diff_p_turnover=round(td, 6), diff_p_turnover_ci95_low=round(tlo, 6),
            diff_p_turnover_ci95_high=round(thi, 6), secondary_note="; ".join(notes)))
    by_id = {r.action_id: r for r in results}
    ranking = sorted(by_id, key=lambda aid: (-by_id[aid].p_goal.value, -by_id[aid].p_shot.value,
                                             by_id[aid].p_turnover.value))
    overall: ComparisonVerdict | None = None
    if comparisons:
        best_alt = max(comparisons, key=lambda c: c.diff_p_goal)
        overall = best_alt.verdict
        if overall != "more_promising" and any(c.verdict == "less_promising" for c in comparisons) and all(
            c.verdict in ("less_promising", "similar") for c in comparisons
        ):
            overall = "less_promising"
    return EvaluationOutput(
        results=results,
        comparisons=comparisons,
        ranking=ranking,
        overall_verdict=overall,
        partial=timed_out or cancelled,
        completed_rollouts=done,
        elapsed_s=time.perf_counter() - started,
        timed_out=timed_out,
        cancelled=cancelled,
        summaries=summaries,
    )


def replay_rollout(
    snapshot: MatchStateSnapshot,
    roster: dict[str, Player],
    action: CandidateAction,
    config: SimulationConfig,
    rollout_index: int,
    simulation_run_id: str,
    selection_rule: str = REPRESENTATIVE_RULE,
) -> Trajectory:
    """Deterministically re-run one rollout with frame recording enabled."""
    base = state_from_snapshot(snapshot, roster)
    act = resolve_candidate(base, snapshot, action)
    rng = rollout_rng(config, action.action_id, rollout_index)
    summary, frames, events = run_rollout(base, act, rng, config.horizon_s, record=True)
    return Trajectory(
        simulation_run_id=simulation_run_id,
        action_id=action.action_id,
        rollout_index=rollout_index,
        seed_key=rng.key,
        outcome=summary.outcome,
        terminated_reason=summary.outcome,
        selection_rule=selection_rule,
        frames=frames,
        events=events,
        start_match_clock_ms=snapshot.match_clock_ms,
    )

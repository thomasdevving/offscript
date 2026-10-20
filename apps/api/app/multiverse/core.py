"""Deterministic core of the Football Multiverse: response-matrix cells, successor states, transitions.

Everything numerical here is produced by the existing simulator (`app.simulation`). Agents only
choose which cells to evaluate and which action to take; they never produce numbers.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass

import numpy as np

from ..models.common import SIMULATOR_VERSION
from ..models.decisions import CandidateAction
from ..models.match import Player
from ..models.multiverse import DefensiveStrategy, MatrixCell, SampleKind, Transition
from ..models.simulation import SimulationConfig
from ..models.state import BallState, MatchStateSnapshot, PlayerState
from ..simulation.defense import build_runtime
from ..simulation.engine import EngineState, RolloutRng
from ..simulation.monte_carlo import evaluate_actions, rollout_rng
from ..simulation.rollout import (
    RolloutSummary,
    StepResult,
    resolve_candidate,
    run_first_action,
    state_from_snapshot,
)

CONDITIONAL_SHOT_DRAWS = 24
TURNOVER_FIRST = {"intercepted", "tackled", "loose_lost", "out_of_play", "blocked", "saved", "off_target"}


def action_fingerprint(a: CandidateAction) -> str:
    tx = None if a.target_x is None else round(a.target_x, 1)
    ty = None if a.target_y is None else round(a.target_y, 1)
    return f"{a.action_type}|{a.actor_id}|{a.target_player_id}|{tx}|{ty}"


def strategy_fingerprint(s: DefensiveStrategy | None) -> str:
    if s is None:
        return "balanced"
    return json.dumps({"style": s.style, "a": [a.model_dump() for a in s.assignments]}, sort_keys=True)


def snapshot_digest(s: MatchStateSnapshot) -> str:
    return hashlib.sha256(s.model_dump_json().encode()).hexdigest()[:16]


@dataclass
class CellResult:
    cell: MatrixCell
    summaries: list[RolloutSummary]
    seed: int


class CellEvaluator:
    """Evaluates (state, action, defence) cells with common random numbers and an LRU cache.

    Cache key = immutable snapshot id + action fingerprint + defence fingerprint + rollouts + seed +
    horizon + simulator version + estimator settings, so results are never reused across states.
    """

    def __init__(self, max_entries: int = 2000):
        self.cache: OrderedDict[str, CellResult] = OrderedDict()
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def key(self, snapshot: MatchStateSnapshot, action: CandidateAction, strategy: DefensiveStrategy | None,
            rollouts: int, seed: int, horizon: float) -> str:
        raw = "|".join([snapshot.snapshot_id, snapshot_digest(snapshot), action_fingerprint(action),
                        strategy_fingerprint(strategy), str(rollouts), str(seed), f"{horizon:g}", SIMULATOR_VERSION,
                        str(CONDITIONAL_SHOT_DRAWS)])
        return hashlib.sha256(raw.encode()).hexdigest()

    def evaluate(self, snapshot: MatchStateSnapshot, roster: dict[str, Player], action: CandidateAction,
                 strategy: DefensiveStrategy | None, rollouts: int, seed: int, horizon: float, round_no: int = 1,
                 cancel: threading.Event | None = None) -> CellResult:
        k = self.key(snapshot, action, strategy, rollouts, seed, horizon)
        with self.lock:
            if k in self.cache:
                self.hits += 1
                self.cache.move_to_end(k)
                hit = self.cache[k]
                return CellResult(hit.cell.model_copy(update={"cached": True, "action_id": action.action_id}),
                                  hit.summaries, hit.seed)
            self.misses += 1
        cfg = SimulationConfig(rollouts=rollouts, seed=seed, horizon_s=horizon, time_budget_s=120)
        out = evaluate_actions(snapshot, roster, [action], cfg, cancel=cancel, defense=build_runtime(strategy, snapshot),
                               conditional_shots=CONDITIONAL_SHOT_DRAWS)
        r = out.results[0]
        sm = out.summaries[0] if out.summaries else []
        xs = np.array([s.shot_goal_prob if s.shot_time is not None else 0.0 for s in sm], dtype=float)
        n = len(xs)
        mean = float(xs.mean()) if n else 0.0
        half = 1.96 * float(xs.std(ddof=1)) / math.sqrt(n) if n > 1 else 1.0
        cell = MatrixCell(
            action_id=action.action_id,
            strategy_id=strategy.strategy_id if strategy else "def-balanced",
            xg=round(mean, 6), xg_ci95_low=round(max(0.0, mean - half), 6), xg_ci95_high=round(min(1.0, mean + half), 6),
            p_goal=r.p_goal, p_shot=r.p_shot, p_turnover=r.p_turnover, p_first_action_success=r.p_first_action_success,
            n_rollouts=r.n_rollouts, round=round_no,
        )
        res = CellResult(cell, sm, seed)
        if not out.partial:
            with self.lock:
                self.cache[k] = res
                while len(self.cache) > self.max_entries:
                    self.cache.popitem(last=False)
        return res


# ---------------------------------------------------------------------------- rollout selection

SELECTION_RULES = {
    "representative": "Representative: the most common outcome of the first action, and among those rollouts the "
                      "medoid of where the ball ended up.",
    "high_upside": "High-upside sample: the rollout with the highest conditional scoring chance (ties: most progress). "
                   "Deliberately optimistic, not typical.",
    "defensive_success": "Defensive-success sample: a rollout where the defence won the ball or stopped the shot "
                         "(medoid of those). Deliberately pessimistic.",
    "random": "Random sample: one rollout drawn with the session seed. Neither best nor typical.",
}


def _medoid(points: np.ndarray, idxs: list[int]) -> int:
    if len(idxs) == 1:
        return idxs[0]
    pts = points[idxs]
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2).sum(axis=1)
    return idxs[int(np.argmin(d))]


def select_rollout(summaries: list[RolloutSummary], kind: SampleKind, seed: int) -> tuple[int, str, str]:
    """(rollout index, selection rule text, effective kind)."""
    if not summaries:
        raise ValueError("no rollouts to select from")
    ends = np.array([s.first_end_ball for s in summaries], dtype=float)
    if kind == "high_upside":
        idx = max(range(len(summaries)), key=lambda i: (summaries[i].shot_goal_prob, summaries[i].progression, -i))
        return idx, SELECTION_RULES["high_upside"], kind
    if kind == "defensive_success":
        idxs = [i for i, s in enumerate(summaries) if s.first_outcome in TURNOVER_FIRST or s.outcome == "turnover"]
        if idxs:
            return _medoid(ends, idxs), SELECTION_RULES["defensive_success"], kind
        kind = "representative"
    if kind == "random":
        idx = int(np.random.default_rng(seed).integers(len(summaries)))
        return idx, SELECTION_RULES["random"], kind
    counts = Counter(s.first_outcome for s in summaries)
    modal = max(counts, key=lambda o: (counts[o], o))
    idxs = [i for i, s in enumerate(summaries) if s.first_outcome == modal]
    return _medoid(ends, idxs), SELECTION_RULES["representative"], "representative"


# ---------------------------------------------------------------------------- successor states

def snapshot_from_state(state: EngineState, parent: MatchStateSnapshot, snapshot_id: str, elapsed_s: float,
                        score: dict[str, int], possessor_id: str | None, possession_team_id: str) -> MatchStateSnapshot:
    wpos = state.to_world(state.pos)
    wvel = state.vel * state.direction
    players = [
        PlayerState(player_id=p.player_id, team_id=p.team_id, x=round(float(np.clip(wpos[i, 0], -0.9, 105.9)), 3),
                    y=round(float(np.clip(wpos[i, 1], -0.9, 68.9)), 3), vx=round(float(wvel[i, 0]), 3),
                    vy=round(float(wvel[i, 1]), 3), facing=round(math.atan2(float(wvel[i, 1]), float(wvel[i, 0])), 3))
        for i, p in enumerate(state.profiles)
    ]
    wb = state.to_world(state.ball)
    ms = int(round(elapsed_s * 1000))
    return MatchStateSnapshot(
        snapshot_id=snapshot_id, match_id=parent.match_id, sim_time_ms=parent.sim_time_ms + ms,
        match_clock_ms=parent.match_clock_ms + ms, period=parent.period, possession_team_id=possession_team_id,
        attack_direction=dict(parent.attack_direction),
        ball=BallState(x=round(float(np.clip(wb[0], -0.9, 105.9)), 3), y=round(float(np.clip(wb[1], -0.9, 68.9)), 3),
                       possessor_id=possessor_id, last_touch_id=possessor_id),
        players=players, off_pitch_player_ids=list(parent.off_pitch_player_ids), score=score,
        source_event_id=None, seed=parent.seed, simulator_version=SIMULATOR_VERSION,
    )


@dataclass
class StepOutcome:
    transition: Transition
    child_snapshot: MatchStateSnapshot
    step: StepResult


def realize_transition(parent: MatchStateSnapshot, roster: dict[str, Player], action: CandidateAction,
                       strategy: DefensiveStrategy | None, cell: CellResult, kind: SampleKind,
                       child_snapshot_id: str, select_seed: int) -> StepOutcome:
    """Replay the selected rollout's first action from the parent snapshot (parent is never mutated)."""
    idx, rule, eff_kind = select_rollout(cell.summaries, kind, select_seed)
    base = state_from_snapshot(parent, roster)
    act = resolve_candidate(base, parent, action)
    cfg = SimulationConfig(rollouts=max(1, cell.cell.n_rollouts), seed=cell.seed)
    rng: RolloutRng = rollout_rng(cfg, action.action_id, idx)
    step = run_first_action(base, act, rng, record=True, defense=build_runtime(strategy, parent))
    att = parent.possession_team_id
    deff = next(t for t in parent.attack_direction if t != att)
    score = dict(parent.score)
    st = step.state
    if step.terminal_outcome is None:
        possessor = st.profiles[st.carrier].player_id
        team = att
    elif step.terminal_outcome == "goal":
        score[att] = score.get(att, 0) + 1
        possessor, team = None, deff
    elif step.terminal_outcome == "turnover" and step.phase.turnover_to is not None or step.terminal_outcome == "saved" and step.phase.turnover_to is not None:
        possessor, team = st.profiles[step.phase.turnover_to].player_id, deff
    else:
        possessor, team = None, deff
    child = snapshot_from_state(st, parent, child_snapshot_id, step.duration_s, score, possessor, team)
    transition = Transition(
        parent_snapshot_id=parent.snapshot_id,
        child_snapshot_id=child.snapshot_id,
        action_id=action.action_id,
        strategy_id=strategy.strategy_id if strategy else "def-balanced",
        sample_kind=eff_kind, rollout_index=idx, seed=cell.seed,
        first_outcome=step.phase.outcome, terminal_outcome=step.terminal_outcome,
        duration_ms=int(round(step.duration_s * 1000)), frames=step.frames, events=step.events, selection_rule=rule,
    )
    return StepOutcome(transition=transition, child_snapshot=child, step=step)

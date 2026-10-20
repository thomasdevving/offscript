"""Lightweight, deterministic decision-point detector.

Runs on the live event stream. For every on-ball action it computes cheap features from
the snapshot taken *before* the action (no future information), waits for the action's
outcome event, assigns triggers and a triage score, and applies rate limiting and
de-duplication so viewers are not flooded with analysis cards. The Decision Agent then
decides which candidates deserve a full counterfactual analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models.decisions import DecisionFeatures, DecisionPoint, DecisionTrigger
from ..models.events import EventType, MatchEvent
from ..models.match import Player
from ..models.state import MatchStateSnapshot
from ..simulation import geometry as g
from ..simulation.candidates import actual_action_from_event, generate_candidates
from ..simulation.engine import Engine, pressure_count
from ..simulation.rollout import state_from_snapshot

ACTION_TYPES = {EventType.PASS_ATTEMPTED, EventType.SHOT_ATTEMPTED, EventType.DRIBBLE_ATTEMPTED}
OUTCOME_TYPES = {
    EventType.PASS_COMPLETED, EventType.PASS_FAILED, EventType.SHOT_BLOCKED, EventType.SHOT_SAVED,
    EventType.SHOT_MISSED, EventType.GOAL, EventType.DRIBBLE_COMPLETED, EventType.DRIBBLE_FAILED,
    EventType.PRESSURE_APPLIED,
}
TURNOVER_OUTCOMES = {EventType.PASS_FAILED, EventType.DRIBBLE_FAILED}

TRIGGER_WEIGHTS = {
    DecisionTrigger.SHOT_WITH_TEAMMATE_AVAILABLE: 0.45,
    DecisionTrigger.DIFFICULT_PASS: 0.35,
    DecisionTrigger.HIGH_VALUE_POSSESSION: 0.2,
    DecisionTrigger.MULTIPLE_OPTIONS: 0.15,
    DecisionTrigger.DANGEROUS_TURNOVER: 0.3,
    DecisionTrigger.DECISION_UNDER_PRESSURE: 0.3,
    DecisionTrigger.MISSED_FORWARD_PASS: 0.2,
}


@dataclass
class DetectorConfig:
    threshold: float = 0.55
    min_gap_ms: int = 12_000
    high_priority: float = 0.8
    same_actor_window_ms: int = 6_000


@dataclass
class _Pending:
    event: MatchEvent
    snapshot: MatchStateSnapshot
    features: DecisionFeatures
    triggers: list[DecisionTrigger]
    actual_label: str


def compute_features(snapshot: MatchStateSnapshot, roster: dict[str, Player], event: MatchEvent
                     ) -> tuple[DecisionFeatures, list[DecisionTrigger], dict]:
    state = state_from_snapshot(snapshot, roster)
    engine = Engine()
    c = state.carrier
    assert c is not None
    s = state.pos[c]
    d_goal = g.distance_to_goal(float(s[0]), float(s[1]))
    ang = math.degrees(g.goal_opening_angle(float(s[0]), float(s[1])))
    d_def = [float(math.hypot(*(state.pos[j] - s))) for j in state.def_idx()]
    cands = generate_candidates(snapshot, roster)
    passes = [a for a in cands if a.action_type == "pass"]
    open_tm = [a for a in passes if a.features.get("completion_estimate", 0) > 0.7]
    forward = [a for a in open_tm if a.features.get("forward_gain_m", 0) > 5]
    zv = g.zone_value(float(s[0]), float(s[1]))
    feats = DecisionFeatures(
        distance_to_goal_m=round(d_goal, 2),
        goal_angle_deg=round(ang, 2),
        pressure_count_5m=pressure_count(state, c, 5.0),
        nearest_defender_m=round(min(d_def), 2) if d_def else 99.0,
        open_teammates=len(open_tm),
        forward_options=len(forward),
        zone_value=round(zv, 4),
    )
    triggers: list[DecisionTrigger] = []
    et = event.event_type
    actual = actual_action_from_event(snapshot, roster, et.value, event.details.intended_receiver_id,
                                      event.end_x, event.end_y)
    hv = [a.features.get("heuristic_value", 0.0) for a in cands]
    best_alt = 0.0
    if et == EventType.SHOT_ATTEMPTED:
        sq = engine.shot_probability(state, c, 400, seed=snapshot.seed)
        feats.actual_shot_quality = round(sq, 4)
        better_placed = [a for a in passes if a.features.get("completion_estimate", 0) > 0.55
                         and a.features.get("receiver_distance_to_goal_m", 99) < d_goal - 2]
        if better_placed:
            triggers.append(DecisionTrigger.SHOT_WITH_TEAMMATE_AVAILABLE)
        best_alt = max([a.features.get("heuristic_value", 0) for a in passes] or [0.0])
    elif et == EventType.PASS_ATTEMPTED and event.details.intended_receiver_id:
        e = engine.expected_pass(state, c, state.index(event.details.intended_receiver_id))
        feats.actual_pass_difficulty = round(1 - e["completion_est"], 4)
        if feats.actual_pass_difficulty > 0.5:
            triggers.append(DecisionTrigger.DIFFICULT_PASS)
        fwd_gain = e["end_x"] - float(s[0])
        if fwd_gain < 2 and forward:
            triggers.append(DecisionTrigger.MISSED_FORWARD_PASS)
        best_alt = max([h for a, h in zip(cands, hv, strict=True)
                        if a.target_player_id != event.details.intended_receiver_id] or [0.0])
    else:
        if forward and feats.distance_to_goal_m > 25:
            triggers.append(DecisionTrigger.MISSED_FORWARD_PASS)
        best_alt = max([a.features.get("heuristic_value", 0) for a in passes] or [0.0])
    feats.best_alternative_gain_estimate = round(best_alt, 4)
    # High-value possession: dangerous zone, or an attacking overload ahead of the ball.
    # Local overload: attackers vs outfield defenders in the 25 m corridor ahead of the ball.
    def _ahead(idx: list[int]) -> int:
        return sum(1 for j in idx if s[0] + 1.0 < state.pos[j, 0] <= s[0] + 25.0)
    ahead_att = _ahead([j for j in state.att_idx() if j != c])
    ahead_def = _ahead([j for j in state.def_idx() if not state.is_gk[j]])
    feats_overload = ahead_att >= 2 and ahead_att > ahead_def and d_goal < 50
    if zv > 0.025 or feats_overload:
        triggers.append(DecisionTrigger.HIGH_VALUE_POSSESSION)
    if feats.pressure_count_5m >= 2 or feats.nearest_defender_m < 1.6:
        triggers.append(DecisionTrigger.DECISION_UNDER_PRESSURE)
    top = sorted(hv, reverse=True)[:4]
    if len(top) >= 3 and top[0] > 0.004 and top[2] >= 0.6 * top[0]:
        triggers.append(DecisionTrigger.MULTIPLE_OPTIONS)
    return feats, triggers, {"actual_label": actual.label}


def triage_score(triggers: list[DecisionTrigger], feats: DecisionFeatures) -> float:
    s = sum(TRIGGER_WEIGHTS[t] for t in triggers)
    if DecisionTrigger.DECISION_UNDER_PRESSURE in triggers:
        # More defenders closing in -> harder, more interesting decision.
        s += 0.07 * max(0, min(3, feats.pressure_count_5m) - 1)
    s += min(0.25, feats.zone_value * 4)
    if DecisionTrigger.DIFFICULT_PASS in triggers and feats.actual_pass_difficulty is not None:
        s += max(0.0, feats.actual_pass_difficulty - 0.5) * 0.4
    return round(min(1.0, s), 4)


class DecisionDetector:
    """Streaming detector. Feed every applied event to `on_event`; returns finalized decisions."""

    def __init__(self, match_id: str, roster: dict[str, Player], snapshots: dict[str, MatchStateSnapshot],
                 config: DetectorConfig | None = None, feature_cache: dict[str, tuple] | None = None):
        self.match_id = match_id
        self.roster = roster
        self.snapshots = snapshots
        self.config = config or DetectorConfig()
        self.pending: _Pending | None = None
        self.decisions: list[DecisionPoint] = []
        self.suppressed: list[dict] = []
        self.last_published_ms: int | None = None
        self._counter = 0
        # Features are a pure function of (snapshot, event): cache them so replays/seeks are cheap.
        self.feature_cache = feature_cache if feature_cache is not None else {}

    def on_event(self, event: MatchEvent) -> list[DecisionPoint]:
        out: list[DecisionPoint] = []
        if event.event_type in ACTION_TYPES and self.pending is not None:
            # The previous action never produced a terminal outcome (e.g. a dribble held up
            # under pressure, ball retained): finalise it now.
            dp = self._finalize(self.pending, None)
            self.pending = None
            if dp is not None:
                out.append(dp)
        if event.event_type in ACTION_TYPES and event.details.scripted:
            return out
        if event.event_type in ACTION_TYPES and event.snapshot_id and event.snapshot_id in self.snapshots:
            snap = self.snapshots[event.snapshot_id]
            if snap.ball.possessor_id is None:
                return out
            if event.event_id not in self.feature_cache:
                self.feature_cache[event.event_id] = compute_features(snap, self.roster, event)
            feats, triggers, extra = self.feature_cache[event.event_id]
            feats = feats.model_copy()
            self.pending = _Pending(event, snap, feats, triggers, extra["actual_label"])
            return out
        if self.pending is not None and event.event_type in OUTCOME_TYPES and event.sim_time_ms >= self.pending.event.sim_time_ms:
            if event.event_type == EventType.PRESSURE_APPLIED:
                return out
            dp = self._finalize(self.pending, event)
            self.pending = None
            if dp is not None:
                out.append(dp)
        return out

    def _finalize(self, p: _Pending, outcome: MatchEvent | None) -> DecisionPoint | None:
        triggers = list(p.triggers)
        if outcome is not None and outcome.event_type in TURNOVER_OUTCOMES:
            direction = p.snapshot.attack_direction[p.snapshot.possession_team_id]
            ox, _ = g.to_attack_frame(outcome.x or 52.5, outcome.y or 34, direction)
            if ox < 45 or p.features.zone_value > 0.02:
                triggers.append(DecisionTrigger.DANGEROUS_TURNOVER)
        score = triage_score(triggers, p.features)
        if outcome is not None and outcome.details.scripted:
            # Scripted build-up actions are choreography, not decisions.
            return None
        if score < self.config.threshold or not triggers:
            return None
        t = p.event.sim_time_ms
        actor = p.event.player_ids[0]
        # De-duplicate: same actor within a short window -> keep the higher score.
        if self.decisions and self.decisions[-1].actor_id == actor and \
                t - self.decisions[-1].sim_time_ms < self.config.same_actor_window_ms:
            # Keep the earlier moment unless the follow-up decision is clearly more significant.
            if score < self.decisions[-1].candidate_score + 0.15:
                self.suppressed.append({"event_id": p.event.event_id, "reason": "duplicate_actor_window"})
                return None
            self.suppressed.append({"event_id": self.decisions[-1].event_id, "reason": "replaced_by_higher_score"})
            self.decisions.pop()
        elif self.last_published_ms is not None and t - self.last_published_ms < self.config.min_gap_ms \
                and score < self.config.high_priority:
            self.suppressed.append({"event_id": p.event.event_id, "reason": "rate_limited"})
            return None
        actual = actual_action_from_event(p.snapshot, self.roster, p.event.event_type.value,
                                          p.event.details.intended_receiver_id, p.event.end_x, p.event.end_y)
        self._counter += 1
        dp = DecisionPoint(
            decision_point_id=f"{self.match_id}-dp-{self._counter:03d}",
            match_id=self.match_id,
            snapshot_id=p.snapshot.snapshot_id,
            event_id=p.event.event_id,
            actor_id=actor,
            actor_name=self.roster[actor].name,
            team_id=self.roster[actor].team_id,
            sim_time_ms=t,
            match_clock_ms=p.event.match_clock_ms,
            actual_action=actual,
            actual_outcome=outcome.event_type.value if outcome is not None else "HELD_UP_UNDER_PRESSURE",
            outcome_event_id=outcome.event_id if outcome is not None else None,
            outcome_time_ms=outcome.sim_time_ms if outcome is not None else None,
            triggers=sorted(set(triggers), key=lambda x: list(TRIGGER_WEIGHTS).index(x)),
            features=p.features,
            candidate_score=score,
        )
        self.decisions.append(dp)
        self.last_published_ms = t
        return dp


def detect_all(match_id: str, events: list[MatchEvent], roster: dict[str, Player],
               snapshots: dict[str, MatchStateSnapshot], config: DetectorConfig | None = None
               ) -> tuple[list[DecisionPoint], DecisionDetector]:
    det = DecisionDetector(match_id, roster, snapshots, config)
    for e in events:
        det.on_event(e)
    return det.decisions, det

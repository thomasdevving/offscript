"""Deterministic candidate-action generation and validation.

Agents never invent coordinates or player ids: they choose from candidates produced here,
and any proposal they make is re-validated by `validate_candidate` before simulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..models.decisions import CandidateAction
from ..models.match import Player
from ..models.state import MatchStateSnapshot
from . import geometry as g
from .engine import Engine
from .rollout import state_from_snapshot

MAX_PASS_LENGTH = 60.0
MIN_DRIBBLE = 3.0
MAX_DRIBBLE = 15.0
MAX_SHOT_DISTANCE = 40.0


@dataclass
class ValidationResult:
    ok: bool
    code: str
    message: str


def _label(action_type: str, roster: dict[str, Player], target_id: str | None, angle_deg: float | None = None) -> str:
    if action_type == "shoot":
        return "Shoot"
    if action_type == "pass" and target_id:
        return f"Pass to {roster[target_id].short_name}"
    if angle_deg is None:
        return "Dribble"
    if abs(angle_deg) < 15:
        return "Dribble towards goal"
    return "Dribble inside" if angle_deg < 0 else "Dribble wide"


def validate_candidate(
    snapshot: MatchStateSnapshot, roster: dict[str, Player], action: CandidateAction
) -> ValidationResult:
    if action.initial_state_id != snapshot.snapshot_id:
        return ValidationResult(False, "SNAPSHOT_MISMATCH", "Candidate does not start from the decision snapshot")
    actor = snapshot.player(action.actor_id)
    if actor is None:
        return ValidationResult(False, "ACTOR_NOT_ON_PITCH", f"{action.actor_id} is not on the pitch")
    if snapshot.ball.possessor_id != action.actor_id:
        return ValidationResult(False, "ACTOR_NOT_IN_POSSESSION", f"{action.actor_id} does not have the ball")
    direction = snapshot.attack_direction[snapshot.possession_team_id]
    bx, by = g.to_attack_frame(snapshot.ball.x, snapshot.ball.y, direction)
    if action.action_type == "shoot":
        if action.target_player_id is not None:
            return ValidationResult(False, "INVALID_FIELDS", "A shot has no target player")
        d = g.distance_to_goal(bx, by)
        if d > MAX_SHOT_DISTANCE:
            return ValidationResult(False, "SHOT_TOO_FAR", f"Shot from {d:.1f} m exceeds {MAX_SHOT_DISTANCE} m")
        return ValidationResult(True, "OK", "valid shot")
    if action.action_type == "pass":
        if not action.target_player_id:
            return ValidationResult(False, "MISSING_TARGET", "A pass needs a target player")
        if action.target_player_id == action.actor_id:
            return ValidationResult(False, "SELF_PASS", "Cannot pass to yourself")
        if action.target_player_id in snapshot.off_pitch_player_ids:
            return ValidationResult(False, "PLAYER_NOT_ON_PITCH",
                                    f"{action.target_player_id} is not on the pitch (substitute)")
        target = snapshot.player(action.target_player_id)
        if target is None:
            return ValidationResult(False, "UNKNOWN_PLAYER", f"{action.target_player_id} is not in this match")
        if target.team_id != actor.team_id:
            return ValidationResult(False, "OPPONENT_TARGET", "Pass target is an opponent")
        dist = g.distance((actor.x, actor.y), (target.x, target.y))
        if dist > MAX_PASS_LENGTH:
            return ValidationResult(False, "PASS_TOO_LONG", f"Pass of {dist:.1f} m exceeds {MAX_PASS_LENGTH} m")
        return ValidationResult(True, "OK", "valid pass")
    if action.action_type == "dribble":
        if action.target_x is None or action.target_y is None:
            return ValidationResult(False, "MISSING_TARGET", "A dribble needs a target point")
        if not g.in_bounds(action.target_x, action.target_y, margin=-1.0):
            return ValidationResult(False, "TARGET_OFF_PITCH", "Dribble target is outside the pitch")
        dist = g.distance((actor.x, actor.y), (action.target_x, action.target_y))
        if not (MIN_DRIBBLE <= dist <= MAX_DRIBBLE):
            return ValidationResult(False, "DRIBBLE_LENGTH",
                                    f"Dribble length {dist:.1f} m outside [{MIN_DRIBBLE}, {MAX_DRIBBLE}] m")
        return ValidationResult(True, "OK", "valid dribble")
    return ValidationResult(False, "UNKNOWN_ACTION", f"Unknown action type {action.action_type}")


def generate_candidates(snapshot: MatchStateSnapshot, roster: dict[str, Player]) -> list[CandidateAction]:
    """Enumerate feasible shots, passes and dribbles with deterministic features.

    Features are cheap noise-free model estimates used for triage and for agent reasoning;
    they are *not* the simulation results shown to viewers.
    """
    state = state_from_snapshot(snapshot, roster)
    engine = Engine()
    c = state.carrier
    if c is None:
        return []
    actor_id = state.profiles[c].player_id
    direction = state.direction
    s = state.pos[c]
    out: list[CandidateAction] = []
    d_goal = g.distance_to_goal(float(s[0]), float(s[1]))
    if d_goal <= MAX_SHOT_DISTANCE:
        sq = engine.shot_probability(state, c, 600, seed=snapshot.seed)
        out.append(CandidateAction(
            action_id=f"{snapshot.snapshot_id}-shoot", action_type="shoot", actor_id=actor_id,
            initial_state_id=snapshot.snapshot_id, label="Shoot",
            features={"distance_to_goal_m": round(d_goal, 2),
                      "goal_angle_deg": round(math.degrees(g.goal_opening_angle(float(s[0]), float(s[1]))), 2),
                      "modeled_shot_scoring_probability": round(sq, 4),
                      "heuristic_value": round(sq, 4)}))
    for j in state.att_idx():
        if j == c or state.profiles[j].role == "GK":
            continue
        pj = state.pos[j]
        length = float(np.linalg.norm(pj - s))
        if length < 4.0 or length > MAX_PASS_LENGTH:
            continue
        e = engine.expected_pass(state, c, j)
        end_w = g.from_attack_frame(e["end_x"], e["end_y"], direction)
        zv = g.zone_value(e["end_x"], e["end_y"])
        tid = state.profiles[j].player_id
        out.append(CandidateAction(
            action_id=f"{snapshot.snapshot_id}-pass-{tid}", action_type="pass", actor_id=actor_id,
            target_player_id=tid, target_x=round(end_w[0], 2), target_y=round(end_w[1], 2),
            initial_state_id=snapshot.snapshot_id, label=_label("pass", roster, tid),
            features={"pass_length_m": round(e["length_m"], 2), "completion_estimate": round(e["completion_est"], 4),
                      "lane_best_defender_margin_s": round(e["lane_best_defender_margin_s"], 3),
                      "receiver_zone_value": round(zv, 4), "forward_gain_m": round(e["end_x"] - float(s[0]), 2),
                      "receiver_distance_to_goal_m": round(g.distance_to_goal(e["end_x"], e["end_y"]), 2),
                      "heuristic_value": round(e["completion_est"] * zv, 4)}))
        through = engine.through_point(state, int(j))
        if through is not None and state.profiles[j].role in ("ST", "RW", "LW", "AM", "CM", "RB", "LB"):
            e2 = engine.expected_pass(state, c, int(j), end=through)
            if e2["length_m"] <= MAX_PASS_LENGTH:
                tw = g.from_attack_frame(float(through[0]), float(through[1]), direction)
                zv2 = g.zone_value(float(through[0]), float(through[1]))
                out.append(CandidateAction(
                    action_id=f"{snapshot.snapshot_id}-through-{tid}", action_type="pass", actor_id=actor_id,
                    target_player_id=tid, target_x=round(tw[0], 2), target_y=round(tw[1], 2),
                    initial_state_id=snapshot.snapshot_id, label=f"Through ball to {roster[tid].short_name}",
                    features={"pass_length_m": round(e2["length_m"], 2),
                              "completion_estimate": round(e2["completion_est"], 4),
                              "lane_best_defender_margin_s": round(e2["lane_best_defender_margin_s"], 3),
                              "receiver_zone_value": round(zv2, 4),
                              "forward_gain_m": round(float(through[0] - s[0]), 2),
                              "receiver_distance_to_goal_m": round(g.distance_to_goal(float(through[0]),
                                                                                     float(through[1])), 2),
                              "through_ball": 1.0,
                              "heuristic_value": round(e2["completion_est"] * zv2, 4)}))
    to_goal = g.unit(g.ATTACK_GOAL - s)
    for ang in (0.0, 35.0, -35.0, 70.0, -70.0):
        dirv = g.rotate(to_goal, math.radians(ang))
        tgt = s + dirv * 8.0
        if not g.in_bounds(float(tgt[0]), float(tgt[1]), margin=-1.5):
            continue
        e = engine.expected_dribble(state, c, tgt)
        tw = g.from_attack_frame(float(tgt[0]), float(tgt[1]), direction)
        zv = g.zone_value(float(tgt[0]), float(tgt[1]))
        # Sign convention for labels: positive angle = towards the high-y (right) side in the attack frame.
        side = "towards goal" if ang == 0 else (
            ("diagonally right" if ang > 0 else "diagonally left") if abs(ang) < 50 else
            ("wide right" if ang > 0 else "wide left"))
        out.append(CandidateAction(
            action_id=f"{snapshot.snapshot_id}-dribble-{int(ang):+d}", action_type="dribble", actor_id=actor_id,
            target_x=round(tw[0], 2), target_y=round(tw[1], 2), initial_state_id=snapshot.snapshot_id,
            label=f"Dribble {side}",
            features={"dribble_length_m": round(e["length_m"], 2), "success_estimate": round(e["success_est"], 4),
                      "duels_expected": e["duels"], "target_zone_value": round(zv, 4),
                      "heuristic_value": round(e["success_est"] * zv, 4)}))
    out.sort(key=lambda a: -a.features.get("heuristic_value", 0.0))
    return out


def actual_action_from_event(snapshot: MatchStateSnapshot, roster: dict[str, Player], event_type: str,
                             receiver_id: str | None, end_x: float | None, end_y: float | None) -> CandidateAction:
    """The observed action expressed as a candidate (so it is simulated exactly like the alternatives)."""
    actor = snapshot.ball.possessor_id
    assert actor is not None
    if event_type == "SHOT_ATTEMPTED":
        return CandidateAction(action_id=f"{snapshot.snapshot_id}-actual", action_type="shoot", actor_id=actor,
                               initial_state_id=snapshot.snapshot_id, is_actual=True, label="Shoot (actual)",
                               source="observed")
    if event_type == "PASS_ATTEMPTED" and receiver_id:
        # Re-derive the intended lead point from the snapshot (not the realised ball end point).
        state = state_from_snapshot(snapshot, roster)
        e = Engine().expected_pass(state, state.carrier, state.index(receiver_id))
        w = g.from_attack_frame(e["end_x"], e["end_y"], state.direction)
        return CandidateAction(action_id=f"{snapshot.snapshot_id}-actual", action_type="pass", actor_id=actor,
                               target_player_id=receiver_id, target_x=round(w[0], 2), target_y=round(w[1], 2),
                               initial_state_id=snapshot.snapshot_id, is_actual=True,
                               label=f"Pass to {roster[receiver_id].short_name} (actual)", source="observed")
    return CandidateAction(action_id=f"{snapshot.snapshot_id}-actual", action_type="dribble", actor_id=actor,
                           target_x=end_x, target_y=end_y, initial_state_id=snapshot.snapshot_id, is_actual=True,
                           label="Dribble (actual)", source="observed")

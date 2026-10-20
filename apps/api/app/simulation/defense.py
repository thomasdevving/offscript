"""Defensive strategies as validated, physically bounded inputs to the simulator.

A defensive strategy never moves a defender faster than his maximum speed and never moves the
ball. It changes two things, both documented model assumptions:

1. **Where defenders run** (their phase targets), e.g. two pressers close the ball, one defender
   sits in a passing lane, one tracks a runner, the block narrows or drops.
2. **Attention / anticipation**: a defender assigned to a lane or runner reacts faster to a ball
   played into his zone and slower to balls elsewhere (he is committed). Reaction times are scaled
   within [0.55, 1.4] x the player's own reaction and clipped to [0.1, 0.8] s.

The interception, tackle and shot models are unchanged; they simply see different defender
positions and reaction times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..models.match import Player
from ..models.multiverse import DefensiveAssignment, DefensiveStrategy
from ..models.state import MatchStateSnapshot
from . import geometry as g

REACT_MIN, REACT_MAX = 0.55, 1.4
MAX_ASSIGNMENTS = 3
MAX_ROLE_REACH_S = 2.5  # an assignment is infeasible if the defender cannot reach his post in this time


@dataclass
class _Assign:
    idx: int
    role: str
    target_idx: int | None
    point: np.ndarray | None


@dataclass
class DefenseRuntime:
    style: str
    assignments: list[_Assign] = field(default_factory=list)
    strategy_id: str = "balanced"

    # ------------------------------------------------------------------ targets
    def adjust_targets(self, state, ball_dest: np.ndarray, targets: np.ndarray, speeds: np.ndarray,
                       exclude: set[int]) -> None:
        goal = g.ATTACK_GOAL
        assigned = {a.idx for a in self.assignments}
        out_def = [j for j in state.def_idx() if not state.is_gk[j] and j not in exclude]
        if self.style == "protect_central":
            for j in out_def:
                if j in assigned:
                    continue
                t = targets[j]
                t[1] = t[1] + (g.PITCH_WIDTH / 2 - t[1]) * 0.35
                t[0] = min(t[0], max(g.PITCH_LENGTH - 16.0, float(ball_dest[0]) + 1.0))
        elif self.style == "contain":
            for j in out_def:
                if j in assigned:
                    continue
                d = float(np.linalg.norm(targets[j] - ball_dest))
                if d < 4.0:  # the nearest man stands off instead of diving in
                    targets[j] = ball_dest + g.unit(goal - ball_dest) * 4.0
                targets[j][0] = min(targets[j][0] + 2.5, g.PITCH_LENGTH - 2.0)
        for a in self.assignments:
            if a.idx in exclude:
                continue
            if a.role == "press":
                targets[a.idx] = ball_dest + g.unit(goal - ball_dest) * 1.2
                speeds[a.idx] = state.vmax[a.idx]
            elif a.role == "track_runner" and a.target_idx is not None:
                runner = state.pos[a.target_idx]
                targets[a.idx] = runner + g.unit(goal - runner) * 1.0
                speeds[a.idx] = state.vmax[a.idx]
            elif a.role == "cover_lane":
                end = state.pos[a.target_idx] if a.target_idx is not None else a.point
                if end is not None:
                    targets[a.idx] = ball_dest + (end - ball_dest) * 0.55
                    speeds[a.idx] = state.vmax[a.idx] * 0.95
        np.clip(targets[:, 0], 0.5, g.PITCH_LENGTH - 0.5, out=targets[:, 0])
        np.clip(targets[:, 1], 0.5, g.PITCH_WIDTH - 0.5, out=targets[:, 1])

    # ------------------------------------------------------------------ anticipation
    def react_multipliers(self, state, ball_end: np.ndarray, receiver: int | None) -> np.ndarray:
        m = np.ones(state.n)
        carrier = state.carrier
        cpos = state.pos[carrier] if carrier is not None else state.ball
        for a in self.assignments:
            if a.role == "press":
                near = float(np.linalg.norm(ball_end - cpos)) < 8.0
                m[a.idx] *= 0.85 if near else 1.25
            elif a.role == "track_runner":
                m[a.idx] *= 0.7 if (receiver is not None and receiver == a.target_idx) else 1.15
            elif a.role == "cover_lane":
                end = state.pos[a.target_idx] if a.target_idx is not None else a.point
                hit = end is not None and float(np.linalg.norm(ball_end - end)) < 6.0
                m[a.idx] *= 0.6 if hit else 1.2
        if self.style == "protect_central":
            central = abs(float(ball_end[1]) - g.PITCH_WIDTH / 2) < 12.0
            for j in state.def_idx():
                if not state.is_gk[j] and j not in {a.idx for a in self.assignments}:
                    m[j] *= 0.85 if central else 1.15
        return np.clip(m, REACT_MIN, REACT_MAX)

    def tackle_scale(self) -> float:
        return {"contain": 0.75, "press": 1.15}.get(self.style, 1.0)


def _index(snapshot: MatchStateSnapshot, pid: str) -> int | None:
    for i, p in enumerate(snapshot.players):
        if p.player_id == pid:
            return i
    return None


def build_runtime(strategy: DefensiveStrategy | None, snapshot: MatchStateSnapshot) -> DefenseRuntime | None:
    """Translate a validated strategy into engine indices / attack-frame points for this snapshot."""
    if strategy is None or (strategy.style == "balanced" and not strategy.assignments):
        return None
    direction = snapshot.attack_direction[snapshot.possession_team_id]
    out = []
    for a in strategy.assignments:
        idx = _index(snapshot, a.defender_id)
        tidx = _index(snapshot, a.target_player_id) if a.target_player_id else None
        pt = None
        if a.target_x is not None and a.target_y is not None:
            pt = np.array(g.to_attack_frame(a.target_x, a.target_y, direction), dtype=float)
        if idx is not None:
            out.append(_Assign(idx, a.role, tidx, pt))
    return DefenseRuntime(style=strategy.style, assignments=out, strategy_id=strategy.strategy_id)


def validate_strategy(strategy: DefensiveStrategy, snapshot: MatchStateSnapshot, roster: dict[str, Player]
                      ) -> tuple[bool, str, str]:
    """(ok, code, message). Checks identities, roles, uniqueness and physical reachability."""
    att = snapshot.possession_team_id
    if len(strategy.assignments) > MAX_ASSIGNMENTS:
        return False, "TOO_MANY_ASSIGNMENTS", f"At most {MAX_ASSIGNMENTS} individual assignments"
    seen: set[str] = set()
    direction = snapshot.attack_direction[att]
    for a in strategy.assignments:
        d = snapshot.player(a.defender_id)
        if d is None:
            return False, "DEFENDER_NOT_ON_PITCH", f"{a.defender_id} is not on the pitch"
        if d.team_id == att:
            return False, "NOT_A_DEFENDER", f"{a.defender_id} belongs to the team in possession"
        if roster[a.defender_id].role == "GK":
            return False, "GOALKEEPER_ASSIGNMENT", "The goalkeeper cannot be assigned to press, cover or track"
        if a.defender_id in seen:
            return False, "DUPLICATE_DEFENDER", f"{a.defender_id} has two assignments"
        seen.add(a.defender_id)
        target = None
        if a.target_player_id:
            t = snapshot.player(a.target_player_id)
            if t is None:
                return False, "UNKNOWN_TARGET", f"{a.target_player_id} is not on the pitch"
            if t.team_id != att:
                return False, "TARGET_NOT_ATTACKER", f"{a.target_player_id} is not an attacker"
            target = (t.x, t.y)
        elif a.role == "cover_lane":
            if a.target_x is None or a.target_y is None or not g.in_bounds(a.target_x, a.target_y):
                return False, "LANE_TARGET_INVALID", "A covered lane needs an attacker or an on-pitch point"
            target = (a.target_x, a.target_y)
        elif a.role == "track_runner":
            return False, "MISSING_RUNNER", "track_runner needs a target attacker"
        # Reachability of the post (straight run at max speed after reaction).
        ball = (snapshot.ball.x, snapshot.ball.y)
        if a.role == "press":
            post = ball
        elif a.role == "cover_lane" and target is not None:
            post = (ball[0] + (target[0] - ball[0]) * 0.55, ball[1] + (target[1] - ball[1]) * 0.55)
        else:
            post = target if target is not None else ball
        dist = math.hypot(post[0] - d.x, post[1] - d.y)
        t = roster[a.defender_id].reaction_time_s + max(0.0, dist - 1.0) / roster[a.defender_id].max_speed_mps
        if t > MAX_ROLE_REACH_S:
            return False, "DEFENDER_CANNOT_REACH", (f"{roster[a.defender_id].short_name} needs {t:.1f} s to reach his post "
                                                    f"(limit {MAX_ROLE_REACH_S} s)")
        _ = direction
    return True, "OK", "valid defensive strategy"


BASELINE = DefensiveStrategy(strategy_id="def-balanced", style="balanced", label="Balanced shape",
                             description="Default model behaviour: nearest defender presses, the rest hold shape and mark.")


def generate_defensive_options(snapshot: MatchStateSnapshot, roster: dict[str, Player],
                               threats: list[tuple[str | None, float, float]]) -> list[DefensiveStrategy]:
    """Deterministic catalogue of feasible defensive responses.

    `threats` are attacking targets (receiver id or None, x, y) in world coordinates, most dangerous first.
    """
    att = snapshot.possession_team_id
    defenders = [p for p in snapshot.players if p.team_id != att and roster[p.player_id].role != "GK"]
    ball = np.array([snapshot.ball.x, snapshot.ball.y])

    def eta(p, pt) -> float:
        r = roster[p.player_id]
        return r.reaction_time_s + max(0.0, float(np.hypot(*(np.array(pt) - (p.x, p.y)))) - 1.0) / r.max_speed_mps

    out: list[DefensiveStrategy] = [BASELINE]
    pressers = sorted(defenders, key=lambda p: eta(p, ball))[:2]
    out.append(DefensiveStrategy(
        strategy_id="def-press", style="press", label="Double press on the ball",
        assignments=[DefensiveAssignment(defender_id=p.player_id, role="press") for p in pressers],
        description="The two closest defenders attack the ball carrier."))
    used_targets: set[str] = set()
    for rid, _x, _y in threats:
        if rid is None or rid in used_targets:
            continue
        runner = snapshot.player(rid)
        if runner is None or runner.team_id != att:
            continue
        used_targets.add(rid)
        # Same lane geometry as validate_strategy: towards the receiver's current position.
        mid = ball + (np.array([runner.x, runner.y]) - ball) * 0.55
        coverer = min(defenders, key=lambda p: eta(p, mid))
        out.append(DefensiveStrategy(
            strategy_id=f"def-cover-{rid}", style="cover_lane", label=f"Cover lane to {roster[rid].short_name}",
            assignments=[DefensiveAssignment(defender_id=coverer.player_id, role="cover_lane", target_player_id=rid)],
            description=f"{roster[coverer.player_id].short_name} steps into the passing lane towards {roster[rid].short_name}."))
        tracker = min((p for p in defenders if p.player_id != coverer.player_id),
                      key=lambda p: eta(p, (runner.x, runner.y)))
        out.append(DefensiveStrategy(
            strategy_id=f"def-track-{rid}", style="track_runner", label=f"Track {roster[rid].short_name}",
            assignments=[DefensiveAssignment(defender_id=tracker.player_id, role="track_runner", target_player_id=rid)],
            description=f"{roster[tracker.player_id].short_name} follows {roster[rid].short_name} tightly."))
        if len(used_targets) >= 2:
            break
    out.append(DefensiveStrategy(strategy_id="def-central", style="protect_central", label="Protect central space",
                                 description="The block narrows towards the middle and drops slightly."))
    out.append(DefensiveStrategy(strategy_id="def-contain", style="contain", label="Retreat and contain",
                                 description="Nobody dives in: the nearest defender stands off and the line drops."))
    return [s for s in out if validate_strategy(s, snapshot, roster)[0]]

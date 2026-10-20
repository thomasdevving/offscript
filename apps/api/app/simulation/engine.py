"""Short-horizon football rollout engine.

The engine is *phase based*: play advances in discrete phases (a pass in flight, a dribble,
a shot, a control/hold moment). Within a phase every player follows a closed-form,
speed-bounded motion: they keep their current velocity for their reaction time and then
run in a straight line towards a phase target at a bounded speed. Because the motion is
closed-form, the same phase description is used both to *resolve* the phase
probabilistically (who reaches the ball first?) and to *render* it frame by frame, so the
animation always matches the computed outcome.

All computations happen in the attack frame of the team in possession (attacking towards
x = 105). Conversion to world coordinates happens only when frames/events are recorded.

Every random draw comes from named per-rollout streams so that two candidate actions
evaluated with the same rollout index share their random numbers (common random numbers).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import geometry as g

FRAME_DT = 0.1
DEF_REACH = 0.9  # metres a defender can stretch to touch a ball
GK_REACH = 1.4
RECEIVER_CONTROL_MARGIN = -0.35  # receiver may arrive this late (s) and still control
MAX_ACTIONS_PER_ROLLOUT = 8


def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass(frozen=True)
class Profile:
    player_id: str
    team_id: str
    name: str
    role: str
    max_speed: float
    reaction: float
    technique: float
    finishing: float
    dribbling: float


@dataclass
class EngineState:
    """Mutable rollout state, expressed in the attack frame of `att_team`."""

    profiles: list[Profile]
    is_att: np.ndarray
    pos: np.ndarray
    vel: np.ndarray
    anchors: np.ndarray
    ball: np.ndarray
    ball_ref: np.ndarray
    carrier: int | None
    t: float
    direction: int  # world attack direction of `att_team` (+1 / -1)
    att_team: str
    def_team: str
    vmax: np.ndarray = field(init=False)
    react: np.ndarray = field(init=False)
    is_gk: np.ndarray = field(init=False)
    is_fwd: np.ndarray = field(init=False)
    is_fb: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.vmax = np.array([p.max_speed for p in self.profiles])
        self.react = np.array([p.reaction for p in self.profiles])
        self.is_gk = np.array([p.role == "GK" for p in self.profiles])
        self.is_fwd = np.array([p.role in ("ST", "RW", "LW", "AM") for p in self.profiles])
        self.is_fb = np.array([p.role in ("RB", "LB") for p in self.profiles])

    @property
    def n(self) -> int:
        return len(self.profiles)

    @property
    def ids(self) -> list[str]:
        return [p.player_id for p in self.profiles]

    def index(self, player_id: str) -> int:
        for i, p in enumerate(self.profiles):
            if p.player_id == player_id:
                return i
        raise KeyError(player_id)

    def att_idx(self) -> np.ndarray:
        return np.flatnonzero(self.is_att)

    def def_idx(self) -> np.ndarray:
        return np.flatnonzero(~self.is_att)

    def gk(self, attacking: bool) -> int | None:
        for i, p in enumerate(self.profiles):
            if p.role == "GK" and bool(self.is_att[i]) == attacking:
                return i
        return None

    def copy(self) -> EngineState:
        s = EngineState(
            profiles=self.profiles,
            is_att=self.is_att.copy(),
            pos=self.pos.copy(),
            vel=self.vel.copy(),
            anchors=self.anchors.copy(),
            ball=self.ball.copy(),
            ball_ref=self.ball_ref.copy(),
            carrier=self.carrier,
            t=self.t,
            direction=self.direction,
            att_team=self.att_team,
            def_team=self.def_team,
        )
        return s

    def flip_possession(self, new_carrier: int | None) -> None:
        """Switch the attacking team: rotate everything into the other team's attack frame."""
        self.pos = g.arr_to_attack_frame(self.pos, -1)
        self.vel = -self.vel
        self.anchors = g.arr_to_attack_frame(self.anchors, -1)
        self.ball = g.arr_to_attack_frame(self.ball, -1)
        self.ball_ref = self.ball.copy()
        self.is_att = ~self.is_att
        self.att_team, self.def_team = self.def_team, self.att_team
        self.direction = -self.direction
        self.carrier = new_carrier

    def to_world(self, xy: np.ndarray) -> np.ndarray:
        return g.arr_to_attack_frame(np.asarray(xy, dtype=float), self.direction)


# ---------------------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------------------


@dataclass
class BallPath:
    kind: str  # "attached" | "flight" | "static"
    start: np.ndarray
    end: np.ndarray
    v0: float = 0.0
    decel: float = 0.0
    z_peak: float = 0.0
    carrier: int | None = None
    total_dist: float = 0.0

    def at(self, tau: float, player_pos: np.ndarray) -> tuple[float, float, float]:
        if self.kind == "attached" and self.carrier is not None:
            p = player_pos[self.carrier]
            return float(p[0]), float(p[1]), 0.0
        if self.kind == "static":
            return float(self.start[0]), float(self.start[1]), 0.0
        d = min(self.total_dist, self.v0 * tau - 0.5 * self.decel * tau * tau) if tau > 0 else 0.0
        if self.decel > 0 and tau > self.v0 / self.decel:
            d = min(self.total_dist, self.v0 * self.v0 / (2 * self.decel))
        direction = g.unit(self.end - self.start)
        p = self.start + direction * max(0.0, d)
        frac = d / self.total_dist if self.total_dist > 1e-6 else 1.0
        z = 4 * self.z_peak * frac * (1 - frac) if self.z_peak > 0 else 0.0
        return float(p[0]), float(p[1]), float(z)


@dataclass
class Motion:
    t0: float
    duration: float
    p0: np.ndarray
    v0: np.ndarray
    react: np.ndarray
    target: np.ndarray
    speed: np.ndarray
    ball: BallPath

    def positions(self, tau: float) -> np.ndarray:
        tau = max(0.0, min(tau, self.duration))
        m = np.minimum(tau, self.react)
        p_react = self.p0 + self.v0 * self.react[:, None]
        p_mom = self.p0 + self.v0 * m[:, None]
        delta = self.target - p_react
        dist = np.linalg.norm(delta, axis=1)
        safe = np.where(dist > 1e-9, dist, 1.0)
        dirs = delta / safe[:, None]
        travel = np.minimum(dist, self.speed * np.maximum(0.0, tau - self.react))
        out = p_mom + dirs * travel[:, None]
        return g.clamp_to_pitch(out, margin=-1.0)

    def velocities(self, tau: float) -> np.ndarray:
        tau = max(0.0, min(tau, self.duration))
        p_react = self.p0 + self.v0 * self.react[:, None]
        delta = self.target - p_react
        dist = np.linalg.norm(delta, axis=1)
        safe = np.where(dist > 1e-9, dist, 1.0)
        dirs = delta / safe[:, None]
        after = tau - self.react
        moving = (after > 0) & (self.speed * np.maximum(after, 0) < dist)
        v = np.where((tau < self.react)[:, None], self.v0, 0.0)
        v = np.where(moving[:, None], dirs * self.speed[:, None], v)
        return v


def time_to_point(state: EngineState, idx: np.ndarray, point: np.ndarray, react: np.ndarray, reach: float) -> np.ndarray:
    """Earliest arrival time of players `idx` at `point` given reaction delays (momentum first)."""
    p_react = state.pos[idx] + state.vel[idx] * react[:, None]
    d = np.linalg.norm(point[None, :] - p_react, axis=1)
    return react + np.maximum(0.0, d - reach) / state.vmax[idx]


def times_to_points(
    state: EngineState, idx: np.ndarray, points: np.ndarray, react: np.ndarray, reach: float
) -> np.ndarray:
    """Arrival times (len(idx), len(points))."""
    p_react = state.pos[idx] + state.vel[idx] * react[:, None]
    d = np.linalg.norm(points[None, :, :] - p_react[:, None, :], axis=2)
    return react[:, None] + np.maximum(0.0, d - reach) / state.vmax[idx][:, None]


# ---------------------------------------------------------------------------------------
# Rng streams (common random numbers)
# ---------------------------------------------------------------------------------------

STREAM_EXECUTION = 0
STREAM_REACTION = 1
STREAM_POLICY = 2
STREAM_MOVEMENT = 3


class RolloutRng:
    """Independent named random streams for one rollout index."""

    def __init__(self, base_seed: int, rollout_index: int):
        self.key = [int(base_seed), int(rollout_index)]
        self._streams = {
            s: np.random.default_rng(np.random.SeedSequence(entropy=int(base_seed), spawn_key=(rollout_index, s)))
            for s in (STREAM_EXECUTION, STREAM_REACTION, STREAM_POLICY, STREAM_MOVEMENT)
        }

    def __getitem__(self, stream: int) -> np.random.Generator:
        return self._streams[stream]


# ---------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------


@dataclass
class PhaseResult:
    kind: str  # pass | shot | dribble | control | restart
    outcome: str  # completed, intercepted, loose_won, loose_lost, out_of_play, goal, saved, blocked, off_target,
    # success, tackled, interrupted, held
    duration: float
    new_carrier: int | None = None
    turnover_to: int | None = None
    events: list[dict] = field(default_factory=list)
    detail: dict = field(default_factory=dict)


Recorder = Callable[[Motion, EngineState], None]


# ---------------------------------------------------------------------------------------
# Off-ball behaviour
# ---------------------------------------------------------------------------------------


def _unit_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.where(n > 1e-9, v / np.where(n > 1e-9, n, 1.0), 0.0)


def team_targets(state: EngineState, ball_dest: np.ndarray, rng: np.random.Generator, exclude: set[int]) -> tuple[
    np.ndarray, np.ndarray
]:
    """Rule-based off-ball targets and running speeds reacting to where the ball is going.

    Attackers: shift with the ball, make forward runs in the final third (never beyond an
    approximate offside line) and drift towards the nearby point with most room (move into space).
    Defenders: goalkeeper guards the line between ball and goal, the closest defender
    presses the ball destination (goal side), the rest blend zonal shape with goal-side
    marking of the nearest attacker and hold a defensive line ~13 m from goal.
    """
    targets = state.pos.copy()
    speeds = state.vmax * 0.6
    shift = ball_dest - state.ball_ref
    goal = g.ATTACK_GOAL
    excl = np.array(sorted(exclude), dtype=int) if exclude else np.zeros(0, dtype=int)
    keep = np.ones(state.n, dtype=bool)
    keep[excl] = False
    is_att = state.is_att
    deff = state.def_idx()
    def_pos = state.pos[deff]
    gk_def = state.gk(attacking=False)
    outfield_def_mask = (~is_att) & ~state.is_gk
    outfield_x = state.pos[outfield_def_mask, 0]
    # Approximate offside line: deepest outfield defender (GK is the last man) or the ball.
    offside_x = max(float(outfield_x.max()) if len(outfield_x) else g.PITCH_LENGTH, float(ball_dest[0]))

    # ---- attackers ----
    A = np.flatnonzero(is_att & keep & ~state.is_gk)
    if len(A):
        tgt = state.anchors[A] + shift * np.array([0.55, 0.3])
        tgt[:, 0] += np.where(state.is_fwd[A] & (ball_dest[0] > 55), 5.0, 0.0)
        tgt[:, 0] += np.where(state.is_fb[A] & (ball_dest[0] > 60), 3.0, 0.0)
        tgt[:, 0] = np.minimum(tgt[:, 0], min(offside_x - 0.3, 101.0))
        angles = rng.uniform(0, 2 * math.pi, (len(A), 6))
        offs = np.stack([np.cos(angles), np.sin(angles)], axis=2) * 4.0
        cands = np.concatenate([tgt[:, None, :], tgt[:, None, :] + offs], axis=1)
        cands = g.clamp_to_pitch(cands, 1.5)
        cands[..., 0] = np.minimum(cands[..., 0], np.maximum(offside_x - 0.3, tgt[:, None, 0]))
        room = np.linalg.norm(cands[:, :, None, :] - def_pos[None, None, :, :], axis=3).min(axis=2)
        score = (np.minimum(room, 8.0) + 0.12 * (cands[..., 0] - tgt[:, None, 0])
                 - 0.05 * np.linalg.norm(cands - tgt[:, None, :], axis=2))
        best = score.argmax(axis=1)
        targets[A] = cands[np.arange(len(A)), best]
        speeds[A] = state.vmax[A] * rng.uniform(0.62, 0.9, len(A))
    gk_att = state.gk(attacking=True)
    if gk_att is not None and keep[gk_att]:
        targets[gk_att] = g.clamp_to_pitch(state.anchors[gk_att] + np.array([shift[0] * 0.4, 0.0]), 1.0)
        speeds[gk_att] = state.vmax[gk_att] * 0.5

    # ---- defenders ----
    if gk_def is not None and keep[gk_def]:
        targets[gk_def] = goalkeeper_target(ball_dest)
        speeds[gk_def] = state.vmax[gk_def] * 0.75
    out_def = np.flatnonzero(outfield_def_mask & keep)
    if len(out_def):
        t_press = time_to_point(state, out_def, ball_dest, state.react[out_def], DEF_REACH)
        presser = int(out_def[int(np.argmin(t_press))])
        targets[presser] = ball_dest + g.unit(goal - ball_dest) * 2.2
        speeds[presser] = state.vmax[presser] * rng.uniform(0.82, 0.95)
        R = out_def[out_def != presser]
        if len(R):
            att_pos = state.pos[state.att_idx()]
            zonal = state.anchors[R] + shift * np.array([0.6, 0.45])
            zonal[:, 0] = np.minimum(zonal[:, 0], np.maximum(state.anchors[R, 0], g.PITCH_LENGTH - 13.0))
            d_att = np.linalg.norm(att_pos[None, :, :] - state.pos[R][:, None, :], axis=2)
            k = d_att.argmin(axis=1)
            dmin = d_att[np.arange(len(R)), k]
            mark = att_pos[k] + _unit_rows(goal - att_pos[k]) * 2.8
            w = np.where(dmin < 9.0, 0.55, 0.2)[:, None]
            tgt = w * mark + (1 - w) * zonal
            line = min(max(g.PITCH_LENGTH - 13.0, float(ball_dest[0]) + 2.0), g.PITCH_LENGTH - 2.0)
            tgt[:, 0] = np.minimum(tgt[:, 0], line)
            targets[R] = g.clamp_to_pitch(tgt, 0.8)
            speeds[R] = state.vmax[R] * rng.uniform(0.7, 0.92, len(R))
    return targets, speeds


def goalkeeper_target(ball: np.ndarray) -> np.ndarray:
    """Goalkeeper stands on the ball-goal line, a little off the line (more for closer balls up to 3.5 m)."""
    goal = g.ATTACK_GOAL
    to_ball = ball - goal
    dist_b = float(np.linalg.norm(to_ball))
    if dist_b < 1e-6:
        return goal - np.array([1.0, 0.0])
    tgt = goal + g.unit(to_ball) * min(3.5, 0.12 * dist_b + 0.5)
    tgt[0] = min(tgt[0], g.PITCH_LENGTH - 0.5)
    return tgt


# ---------------------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------------------


def defender_arrival_times(state: EngineState, deff: np.ndarray, react: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Earliest time each defender can touch each point (shape (len(deff), *pts.shape[:-1])).

    Momentum for the reaction delay, then a straight run at max speed minus a stretching reach.
    A defender who is already (almost) in the ball's path needs only a fraction of his reaction
    delay: he does not have to start running, just put a foot in.
    """
    lead = (1,) * (pts.ndim - 1)
    shape = (len(deff),) + lead
    reach = np.where(state.is_gk[deff], GK_REACH, DEF_REACH).reshape(shape)
    r = react[deff].reshape(shape)
    p_react = state.pos[deff] + state.vel[deff] * react[deff][:, None]
    dist = np.linalg.norm(pts[None, ...] - p_react.reshape(shape + (2,)), axis=-1)
    eff_react = r * np.clip(dist / (reach + 1.0), 0.3, 1.0)
    return eff_react + np.maximum(0.0, dist - reach) / state.vmax[deff].reshape(shape)


def interception_probability(margin: np.ndarray) -> np.ndarray:
    """P(defender wins the ball) given his best time margin over the ball (s).

    Arriving exactly with the ball is not enough: the defender needs ~0.15 s to set body
    shape and control, so the curve is centred at +0.15 s and capped at 0.85.
    """
    return 0.85 * sigmoid((margin - 0.15) / 0.12)


def pass_speed(length: float) -> float:
    return float(np.clip(7.0 + 0.5 * length, 9.0, 25.0))


PASS_DECEL = 1.6


def flight_time(dist: float, v0: float, decel: float) -> float:
    if decel <= 0:
        return dist / v0
    disc = v0 * v0 - 2 * decel * dist
    if disc < 0:
        return math.inf
    return (v0 - math.sqrt(disc)) / decel


def flight_times(dist: np.ndarray, v0: np.ndarray | float, decel: float) -> np.ndarray:
    """Vectorised `flight_time` (inf where the ball stops before covering `dist`)."""
    disc = np.asarray(v0) ** 2 - 2 * decel * np.asarray(dist)
    with np.errstate(invalid="ignore"):
        t = (np.asarray(v0) - np.sqrt(np.maximum(disc, 0.0))) / decel
    return np.where(disc >= 0, t, np.inf)


def pressure_count(state: EngineState, idx: int, radius: float = 4.0) -> int:
    d = np.linalg.norm(state.pos[state.def_idx()] - state.pos[idx], axis=1)
    return int(np.sum(d < radius))


class Engine:
    """Resolves actions on an EngineState. Stateless apart from configuration."""

    def __init__(self, record: Recorder | None = None, defense=None):
        self.record = record
        # Optional validated defensive strategy (app.simulation.defense.DefenseRuntime): changes
        # defender targets and anticipation, never speeds or positions.
        self.defense = defense
        # Scripted off-ball runs (player index -> attack-frame target). Only used by the scenario
        # generator to choreograph an authored build-up; counterfactual rollouts never set it.
        self.run_overrides: dict[int, np.ndarray] = {}

    def _targets(self, state: EngineState, ball_dest: np.ndarray, rng: np.random.Generator, exclude: set[int]):
        targets, speeds = team_targets(state, ball_dest, rng, exclude)
        if self.defense is not None:
            self.defense.adjust_targets(state, ball_dest, targets, speeds, exclude)
        for i, tgt in self.run_overrides.items():
            if i not in exclude:
                targets[i] = tgt
                speeds[i] = state.vmax[i] * 0.85
        return targets, speeds

    # -- helpers ---------------------------------------------------------------------
    def _commit(self, state: EngineState, motion: Motion) -> None:
        if self.record is not None:
            self.record(motion, state)
        state.pos = motion.positions(motion.duration)
        state.vel = motion.velocities(motion.duration)
        state.t += motion.duration

    def _sample_react(self, state: EngineState, rng: np.random.Generator) -> np.ndarray:
        r = state.react + rng.normal(0.0, 0.07, state.n)
        return np.clip(r, 0.12, 0.6)

    # -- control / hold ----------------------------------------------------------------
    def control_phase(self, state: EngineState, duration: float, rng_move: np.random.Generator) -> PhaseResult:
        c = state.carrier
        assert c is not None
        fwd = np.array([2.2 * duration, 0.0])
        carrier_target = g.clamp_to_pitch(state.pos[c] + fwd, 1.0)
        targets, speeds = self._targets(state, carrier_target, rng_move, exclude={c})
        targets[c] = carrier_target
        speeds[c] = min(state.vmax[c] * 0.45, 3.5)
        react = np.full(state.n, 0.15)
        motion = Motion(state.t, duration, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                        BallPath("attached", state.ball.copy(), state.ball.copy(), carrier=c))
        self._commit(state, motion)
        state.ball = state.pos[c].copy()
        return PhaseResult("control", "held", duration, new_carrier=c)

    # -- pass --------------------------------------------------------------------------
    def lead_point(self, state: EngineState, receiver: int) -> np.ndarray:
        """Pass played to feet, slightly ahead of a moving receiver."""
        s = state.ball
        rp = state.pos[receiver]
        length = float(np.linalg.norm(rp - s))
        tf = flight_time(length, pass_speed(length), PASS_DECEL)
        return g.clamp_to_pitch(rp + state.vel[receiver] * min(tf, 1.2) * 0.6, 1.0)

    def through_point(self, state: EngineState, receiver: int) -> np.ndarray | None:
        """Pass into space ahead of the receiver, as far as he can reach while the ball travels."""
        s = state.ball
        rp = state.pos[receiver]
        dirv = g.unit(0.55 * g.unit(g.ATTACK_GOAL - rp) + 0.45 * np.array([1.0, 0.0]))
        end = rp + dirv * 7.0
        for _ in range(2):
            length = float(np.linalg.norm(end - s))
            tf = flight_time(length, pass_speed(length), PASS_DECEL)
            run = min(10.0, state.vmax[receiver] * max(0.0, tf - 0.15) * 0.85)
            end = rp + dirv * run
        end = g.clamp_to_pitch(end, 2.0)
        end[0] = min(end[0], g.PITCH_LENGTH - 2.5)
        if float(np.linalg.norm(end - rp)) < 3.0 or end[0] <= rp[0]:
            return None
        return end

    def expected_pass(self, state: EngineState, passer: int, receiver: int, end: np.ndarray | None = None
                      ) -> dict[str, float]:
        """Deterministic (noise-free) pass assessment used for candidate triage and policy."""
        if end is None:
            end = self.lead_point(state, receiver)
        b = self.pass_batch(state, np.array([receiver]), end[None, :], state.react)
        return {k: float(v[0]) for k, v in b.items()}

    def pass_batch(self, state: EngineState, receivers: np.ndarray, ends: np.ndarray, react: np.ndarray
                   ) -> dict[str, np.ndarray]:
        """Vectorised noise-free assessment of several passes (same model as `interception_scan`)."""
        s = state.ball
        L = np.linalg.norm(ends - s[None, :], axis=1)
        v0 = np.clip(7.0 + 0.5 * L, 9.0, 25.0)
        fr = np.linspace(0.08, 1.0, 16)
        pts = s[None, None, :] + fr[None, :, None] * (ends - s[None, :])[:, None, :]
        t_ball = flight_times(fr[None, :] * L[:, None], v0[:, None], PASS_DECEL)
        deff = state.def_idx()
        t_def = defender_arrival_times(state, deff, react, pts)
        margin = t_ball[None, :, :] - t_def
        pr = state.pos[receivers] + state.vel[receivers] * 0.12
        t_recv = 0.12 + np.maximum(0.0, np.linalg.norm(ends - pr, axis=1) - 0.5) / state.vmax[receivers]
        near = fr >= 0.85
        margin[:, :, near] = np.minimum(margin[:, :, near], t_recv[None, :, None] - t_def[:, :, near])
        best = margin.max(axis=2) if len(deff) else np.full((0, len(receivers)), -5.0)
        p_int = interception_probability(best)
        recv_margin = t_ball[:, -1] - t_recv
        completion = np.prod(1.0 - p_int, axis=0) * sigmoid((recv_margin - RECEIVER_CONTROL_MARGIN) / 0.2)
        return {
            "length_m": L,
            "ball_speed_mps": v0,
            "flight_time_s": t_ball[:, -1],
            "completion_est": completion,
            "lane_best_defender_margin_s": best.max(axis=0) if len(deff) else np.full(len(receivers), -5.0),
            "receiver_margin_s": recv_margin,
            "end_x": ends[:, 0],
            "end_y": ends[:, 1],
        }

    def interception_scan(
        self, state: EngineState, end: np.ndarray, react: np.ndarray, receiver: int | None
    ) -> dict:
        """Where along the ball path can each defender get to the ball first?

        For each defender and each sampled point on the pass line we compare the ball's
        arrival time with the defender's earliest arrival (reaction delay, momentum, then
        a straight run at max speed, minus a stretching reach). Near the end of the path
        the defender must also beat the intended receiver to the ball.
        """
        s = state.ball.copy()
        length = float(np.linalg.norm(end - s))
        v0 = pass_speed(length)
        fr = np.linspace(0.08, 1.0, 16)
        pts = s[None, :] + fr[:, None] * (end - s)[None, :]
        t_ball = flight_times(fr * length, v0, PASS_DECEL)
        deff = state.def_idx()
        t_def = defender_arrival_times(state, deff, react, pts)
        margin = t_ball[None, :] - t_def
        if receiver is not None:
            t_recv = float(time_to_point(state, np.array([receiver]), end, np.array([0.12]), 0.5)[0])
            near_end = fr >= 0.85
            contest = t_recv - t_def  # positive when the defender beats the receiver
            margin[:, near_end] = np.minimum(margin[:, near_end], contest[:, near_end])
        else:
            t_recv = math.inf
        best_k = margin.argmax(axis=1) if len(deff) else np.zeros(0, dtype=int)
        best = margin[np.arange(len(deff)), best_k] if len(deff) else np.zeros(0)
        return {
            "start": s, "length": length, "v0": v0, "fr": fr, "pts": pts, "t_ball": t_ball, "deff": deff,
            "best_k": best_k, "best": best, "p_int": interception_probability(best), "t_recv": t_recv,
        }

    def _lane_assessment(
        self, state: EngineState, passer: int, receiver: int, end: np.ndarray, react: np.ndarray
    ) -> dict[str, float]:
        scan = self.interception_scan(state, end, react, receiver)
        completion = float(np.prod(1.0 - scan["p_int"]))
        recv_margin = float(scan["t_ball"][-1] - scan["t_recv"])
        completion *= float(sigmoid((recv_margin - RECEIVER_CONTROL_MARGIN) / 0.2))
        best = scan["best"]
        return {
            "length_m": scan["length"],
            "ball_speed_mps": scan["v0"],
            "flight_time_s": float(scan["t_ball"][-1]),
            "completion_est": completion,
            "lane_best_defender_margin_s": float(best.max()) if len(best) else -5.0,
            "receiver_margin_s": recv_margin,
            "end_x": float(end[0]),
            "end_y": float(end[1]),
        }

    def resolve_pass(
        self,
        state: EngineState,
        passer: int,
        receiver: int | None,
        aim: np.ndarray | None,
        rng: RolloutRng,
        forced: str | None = None,
    ) -> PhaseResult:
        ex, rx, mv = rng[STREAM_EXECUTION], rng[STREAM_REACTION], rng[STREAM_MOVEMENT]
        s = state.ball.copy()
        if receiver is not None:
            intended = self.lead_point(state, receiver) if aim is None else np.asarray(aim, dtype=float)
        else:
            assert aim is not None
            intended = aim
        length = float(np.linalg.norm(intended - s))
        pressure = pressure_count(state, passer)
        tech = state.profiles[passer].technique
        sigma_ang = (0.022 + 0.0006 * length) * (1.5 - tech) * (1 + 0.35 * pressure)
        ang_err = float(ex.normal(0, sigma_ang))
        len_err = float(ex.normal(0, 0.05))
        u_int = ex.random(state.n)
        u_ctrl = float(ex.random())
        react = self._sample_react(state, rx)
        if self.defense is not None:
            react = np.clip(react * self.defense.react_multipliers(state, intended, receiver), 0.1, 0.8)
        end = intended if forced == "complete" else s + g.rotate(intended - s, ang_err) * (1 + len_err)
        length = float(np.linalg.norm(end - s))
        v0 = pass_speed(length)
        t_arrive = flight_time(length, v0, PASS_DECEL)
        events = [{"type": "PASS_ATTEMPTED", "players": [state.profiles[passer].player_id] + (
            [state.profiles[receiver].player_id] if receiver is not None else []), "pos": s.copy(), "end": end.copy(),
            "detail": {"length": length, "speed": v0}}]

        # --- interception scan along the path ---------------------------------------
        if receiver is not None:
            react[receiver] = 0.12
        scan = self.interception_scan(state, end, react, receiver)
        deff, pts, t_ball = scan["deff"], scan["pts"], scan["t_ball"]
        best_k, best, p_int = scan["best_k"], scan["best"], scan["p_int"]
        winner = None
        win_k = None
        if forced != "complete":
            order = np.argsort(best_k)
            for o in order:
                j = deff[o]
                if u_int[j] < p_int[o]:
                    winner, win_k = j, int(best_k[o])
                    break

        targets, speeds = self._targets(state, end, mv, exclude={passer})
        targets[passer] = state.pos[passer] + np.array([2.0, 0.0])
        speeds[passer] = state.vmax[passer] * 0.6
        if receiver is not None:
            targets[receiver] = end
            speeds[receiver] = state.vmax[receiver]
            react[receiver] = 0.12
        # The best-placed defender attacks the ball path.
        best_def_order = int(np.argmax(best)) if len(best) else None
        if best_def_order is not None and best[best_def_order] > -0.6:
            j = deff[best_def_order]
            targets[j] = pts[best_k[best_def_order]]
            speeds[j] = state.vmax[j]

        if winner is not None:
            t_i = float(t_ball[win_k])
            pt = pts[win_k]
            targets[winner] = pt
            speeds[winner] = state.vmax[winner]
            motion = Motion(state.t, t_i, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                            BallPath("flight", s, pt, v0=v0, decel=PASS_DECEL, total_dist=float(np.linalg.norm(pt - s))))
            self._commit(state, motion)
            # The ball is won within reach; players are never moved discontinuously.
            state.ball = state.pos[winner].copy()
            events.append({"type": "PASS_FAILED", "players": [state.profiles[passer].player_id], "pos": pt.copy(),
                           "detail": {"reason": "intercepted"}})
            events.append({"type": "INTERCEPTION", "players": [state.profiles[winner].player_id], "pos": pt.copy()})
            return PhaseResult("pass", "intercepted", t_i, turnover_to=winner, events=events,
                               detail={"length": length, "speed": v0})

        # --- reception -----------------------------------------------------------------
        in_pitch = g.in_bounds(float(end[0]), float(end[1]))
        if receiver is not None:
            t_recv = float(time_to_point(state, np.array([receiver]), end, np.array([0.12]), 0.5)[0])
        else:
            t_recv = math.inf
        recv_margin = t_arrive - t_recv
        if forced == "complete":
            recv_margin = max(recv_margin, 0.0)
        if receiver is not None and in_pitch and recv_margin >= RECEIVER_CONTROL_MARGIN:
            duration = max(t_arrive, min(t_recv, t_arrive + 0.4))
            motion = Motion(state.t, duration, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                            BallPath("flight", s, end, v0=v0, decel=PASS_DECEL, total_dist=length))
            self._commit(state, motion)
            state.ball = state.pos[receiver].copy()
            press = pressure_count(state, receiver, 2.5)
            p_mis = (0.03 + 0.06 * press) * (1.3 - state.profiles[receiver].technique)
            if forced != "complete" and u_ctrl < p_mis:
                # Heavy touch: nearest defender pounces with 60% chance, otherwise receiver recovers.
                d_def = np.linalg.norm(state.pos[deff] - end, axis=1)
                j = deff[int(np.argmin(d_def))]
                if float(ex.random()) < 0.6 and d_def.min() < 4.0:
                    events.append({"type": "PASS_COMPLETED", "players": [state.profiles[passer].player_id,
                                   state.profiles[receiver].player_id], "pos": end.copy()})
                    events.append({"type": "TACKLE", "players": [state.profiles[j].player_id,
                                   state.profiles[receiver].player_id], "pos": end.copy(),
                                   "detail": {"reason": "heavy_touch"}})
                    return PhaseResult("pass", "loose_lost", duration, turnover_to=j, events=events,
                                       detail={"length": length, "speed": v0})
            events.append({"type": "PASS_COMPLETED", "players": [state.profiles[passer].player_id,
                           state.profiles[receiver].player_id], "pos": end.copy()})
            return PhaseResult("pass", "completed", duration, new_carrier=receiver, events=events,
                               detail={"length": length, "speed": v0})

        # Ball not controlled by the intended receiver: it keeps rolling.
        v_end = max(0.0, v0 - PASS_DECEL * t_arrive) if math.isfinite(t_arrive) else 0.0
        extra = v_end * v_end / (2 * PASS_DECEL) * 0.5
        rest = end + g.unit(end - s) * extra
        total = float(np.linalg.norm(rest - s))
        t_rest = flight_time(total * 0.999, v0, PASS_DECEL)
        if not math.isfinite(t_rest):
            t_rest = v0 / PASS_DECEL
        if not g.in_bounds(float(rest[0]), float(rest[1])):
            # Find where it crosses the boundary (approximate) for the animation.
            out_pt = g.clamp_to_pitch(rest, 0.0)
            dur = min(t_rest, 3.0)
            motion = Motion(state.t, dur, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                            BallPath("flight", s, out_pt, v0=v0, decel=PASS_DECEL,
                                     total_dist=float(np.linalg.norm(out_pt - s))))
            self._commit(state, motion)
            state.ball = out_pt.copy()
            events.append({"type": "PASS_FAILED", "players": [state.profiles[passer].player_id], "pos": out_pt.copy(),
                           "detail": {"reason": "out_of_play"}})
            events.append({"type": "BALL_OUT_OF_PLAY", "players": [], "pos": out_pt.copy()})
            return PhaseResult("pass", "out_of_play", dur, events=events, detail={"length": length, "speed": v0})
        everyone = np.arange(state.n)
        everyone = everyone[everyone != passer]
        t_all = time_to_point(state, everyone, rest, react[everyone], 0.6)
        k = int(np.argmin(t_all))
        winner = int(everyone[k])
        dur = max(min(t_rest, 3.0), float(t_all[k]))
        targets[winner] = rest
        speeds[winner] = state.vmax[winner]
        motion = Motion(state.t, dur, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                        BallPath("flight", s, rest, v0=v0, decel=PASS_DECEL, total_dist=total))
        self._commit(state, motion)
        state.ball = state.pos[winner].copy()
        if state.is_att[winner]:
            events.append({"type": "PASS_COMPLETED", "players": [state.profiles[passer].player_id,
                           state.profiles[winner].player_id], "pos": rest.copy(), "detail": {"reason": "loose_won"}})
            return PhaseResult("pass", "loose_won", dur, new_carrier=winner, events=events,
                               detail={"length": length, "speed": v0})
        events.append({"type": "PASS_FAILED", "players": [state.profiles[passer].player_id], "pos": rest.copy(),
                       "detail": {"reason": "loose_lost"}})
        events.append({"type": "INTERCEPTION", "players": [state.profiles[winner].player_id], "pos": rest.copy()})
        return PhaseResult("pass", "loose_lost", dur, turnover_to=winner, events=events,
                           detail={"length": length, "speed": v0})

    # -- shot --------------------------------------------------------------------------
    def shot_components(self, state: EngineState, shooter: int) -> dict[str, float]:
        s = state.ball
        return {
            "distance_m": g.distance_to_goal(float(s[0]), float(s[1])),
            "angle_deg": math.degrees(g.goal_opening_angle(float(s[0]), float(s[1]))),
            "pressure": float(pressure_count(state, shooter, 2.5)),
        }

    def sample_shot(self, state: EngineState, shooter: int, ex: np.random.Generator) -> dict:
        """Draws one shot outcome. Pure function of state + random draws (no state mutation)."""
        s = state.ball.copy()
        prof = state.profiles[shooter]
        d = g.distance_to_goal(float(s[0]), float(s[1]))
        gk = state.gk(attacking=False)
        gk_pos = state.pos[gk] if gk is not None else np.array([g.PITCH_LENGTH, g.PITCH_WIDTH / 2])
        pressure = pressure_count(state, shooter, 2.5)
        gk_off = float(gk_pos[1] - g.PITCH_WIDTH / 2)
        side = -1.0 if gk_off > 0.15 else (1.0 if gk_off < -0.15 else (1.0 if s[1] < g.PITCH_WIDTH / 2 else -1.0))
        aim_y = g.PITCH_WIDTH / 2 + side * (g.GOAL_HALF - 0.9)
        sigma_y = (0.85 + 0.042 * d) * (1.45 - prof.finishing) * (1 + 0.25 * pressure)
        y_end = aim_y + float(ex.normal(0, sigma_y))
        p_over = min(0.35, 0.02 + 0.006 * d) * (1.3 - prof.finishing)
        over = float(ex.random()) < p_over
        speed = float(np.clip(ex.normal(19 + 9 * prof.finishing - 0.08 * max(0.0, d - 12), 2.0), 12.0, 33.0))
        end = np.array([g.PITCH_LENGTH + 0.4, y_end])
        on_target = (abs(y_end - g.PITCH_WIDTH / 2) < g.GOAL_HALF - 0.11) and not over
        length = float(np.linalg.norm(end - s))
        # Blocks by outfield defenders between ball and goal.
        deff = [j for j in state.def_idx() if j != gk]
        u_block = ex.random(state.n)
        blocked_by, block_t, block_pt = None, None, None
        if deff:
            dl, tl = g.point_segment_distance(state.pos[deff], s, end)
            cands = []
            for o, j in enumerate(deff):
                if tl[o] <= 0.02 or tl[o] >= 0.98:
                    continue
                t_b = tl[o] * length / speed
                reach = 0.4 + max(0.0, t_b - 0.22) * 2.5
                p_b = 0.85 * float(sigmoid((reach - dl[o]) / 0.2))
                cands.append((tl[o], j, p_b, t_b))
            for tpar, j, p_b, t_b in sorted(cands):
                if u_block[j] < p_b:
                    blocked_by, block_t, block_pt = j, t_b, s + (end - s) * tpar
                    break
        u_save = float(ex.random())
        result = {"end": end, "speed": speed, "on_target": on_target, "distance": d, "pressure": pressure}
        if blocked_by is not None:
            result.update(outcome="blocked", by=blocked_by, t=block_t, point=block_pt)
            return result
        if not on_target:
            result.update(outcome="off_target", t=length / speed, point=end)
            return result
        if gk is None:
            result.update(outcome="goal", t=length / speed, point=end)
            return result
        lg, tg = g.point_segment_distance(gk_pos[None, :], s, end)
        lg, tg = float(lg[0]), float(tg[0])
        t_gk = tg * length / speed
        reach_g = 0.85 + 1.7 * min(1.0, t_gk / 0.45) + 2.4 * max(0.0, t_gk - 0.45)
        p_save = 0.97 * float(sigmoid((reach_g - lg) / 0.35))
        if u_save < p_save:
            result.update(outcome="saved", by=gk, t=t_gk, point=s + (end - s) * tg)
        else:
            result.update(outcome="goal", t=length / speed, point=end)
        return result

    def shot_probability(self, state: EngineState, shooter: int, samples: int = 400, seed: int = 0) -> float:
        """Modeled scoring probability of an immediate shot (Monte Carlo over the shot model)."""
        rng = np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(9999,)))
        goals = 0
        for _ in range(samples):
            if self.sample_shot(state, shooter, rng)["outcome"] == "goal":
                goals += 1
        return goals / samples

    def resolve_shot(self, state: EngineState, shooter: int, rng: RolloutRng) -> PhaseResult:
        ex, rx, mv = rng[STREAM_EXECUTION], rng[STREAM_REACTION], rng[STREAM_MOVEMENT]
        s = state.ball.copy()
        res = self.sample_shot(state, shooter, ex)
        react = self._sample_react(state, rx)
        dur = float(res["t"])
        pt = np.array(res["point"], dtype=float)
        targets, speeds = self._targets(state, pt if res["outcome"] != "goal" else s, mv, exclude={shooter})
        targets[shooter] = state.pos[shooter] + np.array([1.5, 0.0])
        if res.get("by") is not None:
            targets[res["by"]] = pt
            speeds[res["by"]] = state.vmax[res["by"]]
        shooter_id = state.profiles[shooter].player_id
        events = [{"type": "SHOT_ATTEMPTED", "players": [shooter_id], "pos": s.copy(), "end": pt.copy(),
                   "detail": {"speed": res["speed"], "distance": res["distance"]}}]
        z_peak = 0.4 if res["outcome"] != "off_target" else 1.6
        motion = Motion(state.t, max(dur, 0.05), state.pos.copy(), state.vel.copy(), react, targets, speeds,
                        BallPath("flight", s, pt, v0=res["speed"], decel=0.0, z_peak=z_peak,
                                 total_dist=float(np.linalg.norm(pt - s))))
        self._commit(state, motion)
        state.ball = g.clamp_to_pitch(pt, 0.0)
        outcome = res["outcome"]
        if outcome == "blocked":
            events.append({"type": "SHOT_BLOCKED", "players": [state.profiles[res["by"]].player_id, shooter_id],
                           "pos": pt.copy()})
        elif outcome == "saved":
            events.append({"type": "SHOT_SAVED", "players": [state.profiles[res["by"]].player_id, shooter_id],
                           "pos": pt.copy()})
        elif outcome == "off_target":
            events.append({"type": "SHOT_MISSED", "players": [shooter_id], "pos": pt.copy()})
        else:
            events.append({"type": "GOAL", "players": [shooter_id], "pos": pt.copy()})
        return PhaseResult("shot", outcome, dur, events=events,
                           turnover_to=res.get("by"),
                           detail={"speed": res["speed"], "distance": res["distance"], "on_target": res["on_target"]})

    # -- dribble -----------------------------------------------------------------------
    def dribble_speed(self, state: EngineState, carrier: int) -> float:
        return float(state.vmax[carrier] * (0.66 + 0.12 * state.profiles[carrier].dribbling))

    def expected_dribble(self, state: EngineState, carrier: int, target: np.ndarray) -> dict[str, float]:
        duels = self._dribble_duels(state, carrier, target, state.react.copy())
        p_ok = 1.0
        for _, _, _, p_tackle in duels:
            # Survive the duel; an interruption (held up) counts as half a success.
            p_ok *= (1 - p_tackle) * (1 - 0.25 * 0.5)
        return {
            "length_m": float(np.linalg.norm(target - state.pos[carrier])),
            "success_est": float(max(0.0, p_ok)),
            "duels": float(len(duels)),
            "end_x": float(target[0]),
            "end_y": float(target[1]),
        }

    def _dribble_duels(
        self, state: EngineState, carrier: int, target: np.ndarray, react: np.ndarray
    ) -> list[tuple[float, int, int, float]]:
        s = state.pos[carrier].copy()
        D = float(np.linalg.norm(target - s))
        vd = self.dribble_speed(state, carrier)
        dur = D / vd if vd > 0 else 0.0
        fr = np.linspace(0.1, 1.0, 10)
        pts = s[None, :] + fr[:, None] * (target - s)[None, :]
        t_c = fr * dur
        deff = state.def_idx()
        near = [j for j in deff if np.linalg.norm(state.pos[j] - s) < D + 10.0 and state.profiles[j].role != "GK"]
        duels = []
        if not near:
            return duels
        near_a = np.array(near)
        t_def = times_to_points(state, near_a, pts, react[near_a], 1.0)
        margin = t_c[None, :] - t_def
        best_k = margin.argmax(axis=1)
        best = margin[np.arange(len(near)), best_k]
        drib = state.profiles[carrier].dribbling
        for o, j in enumerate(near):
            if best[o] > 0.05:
                p_tackle = float(np.clip(0.12 + 0.3 * sigmoid((best[o] - 0.2) / 0.25) - 0.3 * (drib - 0.5), 0.03, 0.6))
                if self.defense is not None:
                    p_tackle = float(np.clip(p_tackle * self.defense.tackle_scale(), 0.03, 0.7))
                duels.append((float(fr[best_k[o]]), int(j), int(best_k[o]), p_tackle))
        duels.sort()
        return duels

    def resolve_dribble(
        self, state: EngineState, carrier: int, target: np.ndarray, rng: RolloutRng, forced: str | None = None
    ) -> PhaseResult:
        ex, rx, mv = rng[STREAM_EXECUTION], rng[STREAM_REACTION], rng[STREAM_MOVEMENT]
        s = state.pos[carrier].copy()
        react = self._sample_react(state, rx)
        if self.defense is not None:
            react = np.clip(react * self.defense.react_multipliers(state, target, None), 0.1, 0.8)
        vd = self.dribble_speed(state, carrier)
        D = float(np.linalg.norm(target - s))
        dur_full = D / vd
        duels = [] if forced == "success" else self._dribble_duels(state, carrier, target, react)
        u = ex.random(state.n)
        cid = state.profiles[carrier].player_id
        events = [{"type": "DRIBBLE_ATTEMPTED", "players": [cid], "pos": s.copy(), "end": target.copy()}]
        stop_frac, outcome, tackler = 1.0, "success", None
        for frac, j, _, p_tackle in duels:
            if u[j] < p_tackle:
                stop_frac, outcome, tackler = frac, "tackled", j
                break
            if u[j] < p_tackle + 0.25 * (1 - p_tackle):
                stop_frac, outcome, tackler = frac, "interrupted", j
                break
        stop_pt = s + (target - s) * stop_frac
        dur = max(0.2, dur_full * stop_frac)
        targets, speeds = self._targets(state, stop_pt, mv, exclude={carrier})
        targets[carrier] = stop_pt
        speeds[carrier] = vd
        react[carrier] = 0.0
        if tackler is not None:
            targets[tackler] = stop_pt
            speeds[tackler] = state.vmax[tackler]
        motion = Motion(state.t, dur, state.pos.copy(), state.vel.copy(), react, targets, speeds,
                        BallPath("attached", s, stop_pt, carrier=carrier))
        self._commit(state, motion)
        state.ball = state.pos[carrier].copy()
        if outcome == "tackled":
            state.ball = state.pos[tackler].copy()
            events.append({"type": "TACKLE", "players": [state.profiles[tackler].player_id, cid], "pos": stop_pt.copy()})
            events.append({"type": "DRIBBLE_FAILED", "players": [cid], "pos": stop_pt.copy()})
            return PhaseResult("dribble", "tackled", dur, turnover_to=tackler, events=events)
        if outcome == "interrupted":
            events.append({"type": "PRESSURE_APPLIED", "players": [state.profiles[tackler].player_id, cid],
                           "pos": stop_pt.copy()})
            return PhaseResult("dribble", "interrupted", dur, new_carrier=carrier, events=events)
        events.append({"type": "DRIBBLE_COMPLETED", "players": [cid], "pos": stop_pt.copy()})
        return PhaseResult("dribble", "success", dur, new_carrier=carrier, events=events)

    # -- in-rollout decision policy ------------------------------------------------------
    def shot_quality_fast(self, state: EngineState, shooter: int) -> float:
        """Closed-form proxy of the shot model, used only to steer simulated teammates."""
        s = state.ball
        d = g.distance_to_goal(float(s[0]), float(s[1]))
        ang = g.goal_opening_angle(float(s[0]), float(s[1]))
        base = float(sigmoid(1.1 - 0.17 * d + 2.2 * ang))
        deff = [j for j in state.def_idx() if state.profiles[j].role != "GK"]
        if deff:
            dl, tl = g.point_segment_distance(state.pos[deff], s, g.ATTACK_GOAL)
            blockers = int(np.sum((dl < 1.2) & (tl > 0.02) & (tl < 0.95)))
        else:
            blockers = 0
        pressure = pressure_count(state, shooter, 2.5)
        return base * (0.55**blockers) * (0.8**pressure) * (0.6 + 0.5 * state.profiles[shooter].finishing)

    def policy_options(self, state: EngineState) -> list[tuple[str, int | None, np.ndarray | None, float]]:
        c = state.carrier
        assert c is not None
        opts: list[tuple[str, int | None, np.ndarray | None, float]] = []
        s = state.pos[c]
        if g.distance_to_goal(float(s[0]), float(s[1])) < 30:
            opts.append(("shoot", None, None, self.shot_quality_fast(state, c)))
        recv = np.array([j for j in state.att_idx() if j != c and not state.is_gk[j]
                         and 5.0 <= float(np.linalg.norm(state.pos[j] - s)) <= 45.0], dtype=int)
        if len(recv):
            ends = np.array([self.lead_point(state, int(j)) for j in recv])
            b = self.pass_batch(state, recv, ends, state.react)
            for k, j in enumerate(recv):
                c_est = float(b["completion_est"][k])
                zv = g.zone_value(float(ends[k, 0]), float(ends[k, 1]))
                opts.append(("pass", int(j), ends[k], c_est * (zv + 0.02) - (1 - c_est) * 0.07))
        for ang in (0.0, 0.6, -0.6):
            dirv = g.rotate(g.unit(g.ATTACK_GOAL - s), ang)
            tgt = g.clamp_to_pitch(s + dirv * 7.0, 1.5)
            e = self.expected_dribble(state, c, tgt)
            val = e["success_est"] * (g.zone_value(float(tgt[0]), float(tgt[1])) + 0.015) - (1 - e["success_est"]) * 0.07
            opts.append(("dribble", None, tgt, val))
        return opts

    def choose_action(self, state: EngineState, rng: np.random.Generator, temperature: float = 0.02):
        opts = self.policy_options(state)
        vals = np.array([o[3] for o in opts])
        logits = (vals - vals.max()) / temperature
        p = np.exp(logits)
        p /= p.sum()
        k = int(rng.choice(len(opts), p=p))
        return opts[k]

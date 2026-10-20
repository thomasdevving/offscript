"""Single counterfactual rollouts from a frozen snapshot, plus snapshot <-> engine conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..models.decisions import CandidateAction
from ..models.events import TrackingFrame
from ..models.match import Player
from ..models.simulation import SimEvent
from ..models.state import MatchStateSnapshot
from . import geometry as g
from .engine import (
    FRAME_DT,
    MAX_ACTIONS_PER_ROLLOUT,
    STREAM_MOVEMENT,
    STREAM_POLICY,
    Engine,
    EngineState,
    Motion,
    PhaseResult,
    Profile,
    RolloutRng,
)

TERMINATION_RULES = (
    "A rollout ends at the first of: a goal (counted only if the ball crosses the line within the horizon); "
    "a shot that is saved, blocked or off target (rebounds are not modelled); a turnover (interception, "
    "tackle or loose ball won by the defending team); the ball leaving the pitch; or the horizon being "
    "reached with possession retained."
)


def profile_from_player(p: Player) -> Profile:
    return Profile(
        player_id=p.player_id,
        team_id=p.team_id,
        name=p.short_name,
        role=p.role,
        max_speed=p.max_speed_mps * (0.92 + 0.08 * p.stamina),
        reaction=p.reaction_time_s,
        technique=p.technique,
        finishing=p.finishing,
        dribbling=p.dribbling,
    )


def state_from_snapshot(snapshot: MatchStateSnapshot, roster: dict[str, Player]) -> EngineState:
    att_team = snapshot.possession_team_id
    teams = {p.team_id for p in snapshot.players}
    def_team = next(t for t in teams if t != att_team)
    direction = snapshot.attack_direction[att_team]
    profiles = [profile_from_player(roster[p.player_id]) for p in snapshot.players]
    pos = np.array([[p.x, p.y] for p in snapshot.players], dtype=float)
    vel = np.array([[p.vx, p.vy] for p in snapshot.players], dtype=float)
    pos = g.arr_to_attack_frame(pos, direction)
    vel = g.vel_to_attack_frame(vel, direction)
    # Bound initial speeds by each player's max speed.
    vmax = np.array([pr.max_speed for pr in profiles])
    sp = np.linalg.norm(vel, axis=1)
    scale = np.where(sp > vmax, vmax / np.maximum(sp, 1e-9), 1.0)
    vel = vel * scale[:, None]
    ball = np.array(g.to_attack_frame(snapshot.ball.x, snapshot.ball.y, direction), dtype=float)
    carrier = None
    if snapshot.ball.possessor_id is not None:
        carrier = next(i for i, p in enumerate(snapshot.players) if p.player_id == snapshot.ball.possessor_id)
    is_att = np.array([p.team_id == att_team for p in snapshot.players])
    return EngineState(
        profiles=profiles,
        is_att=is_att,
        pos=pos,
        vel=vel,
        anchors=pos.copy(),
        ball=ball,
        ball_ref=ball.copy(),
        carrier=carrier,
        t=0.0,
        direction=direction,
        att_team=att_team,
        def_team=def_team,
    )


@dataclass
class ResolvedAction:
    """A candidate action converted into engine terms (attack frame indices / points)."""

    action_type: str
    actor: int
    receiver: int | None
    target: np.ndarray | None


def resolve_candidate(state: EngineState, snapshot: MatchStateSnapshot, action: CandidateAction) -> ResolvedAction:
    actor = state.index(action.actor_id)
    receiver = state.index(action.target_player_id) if action.target_player_id else None
    target = None
    if action.target_x is not None and action.target_y is not None:
        direction = snapshot.attack_direction[snapshot.possession_team_id]
        target = np.array(g.to_attack_frame(action.target_x, action.target_y, direction), dtype=float)
    return ResolvedAction(action.action_type, actor, receiver, target)


@dataclass
class RolloutSummary:
    outcome: str
    t_end: float
    shot_time: float | None
    first_success: bool
    first_outcome: str
    progression: float
    n_actions: int
    end_ball: tuple[float, float]
    first_end_ball: tuple[float, float] = (0.0, 0.0)
    shot_goal_prob: float = 0.0  # conditional P(goal | shot state); 0 when no shot (conditional Monte Carlo)


@dataclass
class _Recorder:
    direction_of: EngineState
    dt: float = FRAME_DT
    next_t: float = 0.0
    frames: list[TrackingFrame] = field(default_factory=list)

    def __call__(self, motion: Motion, state: EngineState) -> None:
        end = motion.t0 + motion.duration
        while self.next_t <= end + 1e-9:
            tau = self.next_t - motion.t0
            pos = motion.positions(tau)
            bx, by, bz = motion.ball.at(tau, pos)
            wpos = state.to_world(pos)
            wb = state.to_world(np.array([bx, by]))
            players = {p.player_id: (round(float(wpos[i, 0]), 2), round(float(wpos[i, 1]), 2))
                       for i, p in enumerate(state.profiles)}
            carrier_id = None
            if motion.ball.kind == "attached" and motion.ball.carrier is not None:
                carrier_id = state.profiles[motion.ball.carrier].player_id
            self.frames.append(TrackingFrame(t_ms=int(round(self.next_t * 1000)),
                                             ball=(round(float(wb[0]), 2), round(float(wb[1]), 2), round(bz, 2)),
                                             players=players, possessor_id=carrier_id))
            self.next_t = round(self.next_t + self.dt, 6)


def _apply(engine: Engine, state: EngineState, act: ResolvedAction, rng: RolloutRng, forced: str | None = None
           ) -> PhaseResult:
    if act.action_type == "shoot":
        return engine.resolve_shot(state, act.actor, rng)
    if act.action_type == "pass":
        return engine.resolve_pass(state, act.actor, act.receiver, act.target, rng, forced=forced)
    assert act.target is not None
    return engine.resolve_dribble(state, act.actor, act.target, rng, forced=forced)


def run_rollout(
    base: EngineState,
    first: ResolvedAction,
    rng: RolloutRng,
    horizon_s: float,
    record: bool = False,
    defense=None,
    conditional_shots: int = 0,
) -> tuple[RolloutSummary, list[TrackingFrame], list[SimEvent]]:
    """Simulate one continuation. With `conditional_shots > 0`, every shot inside the horizon is also
    scored by its conditional goal probability under the shot model (estimated with that many draws
    from an independent stream), giving a lower-variance estimate of P(goal within horizon)."""
    state = base.copy()
    recorder = _Recorder(state) if record else None
    engine = Engine(record=recorder, defense=defense)
    first_end = (float(state.ball[0]), float(state.ball[1]))
    sim_events: list[SimEvent] = []
    start_x = float(state.ball[0])
    shot_time: float | None = None
    first_success = False
    first_outcome = ""
    outcome = "retained"
    n_actions = 0
    act = first
    shot_goal_prob = 0.0
    while True:
        t_before = state.t
        if conditional_shots and act.action_type == "shoot" and t_before <= horizon_s:
            sub_rng = np.random.default_rng(np.random.SeedSequence(entropy=rng.key[0], spawn_key=(rng.key[1], 77)))
            goals = sum(engine.sample_shot(state, act.actor, sub_rng)["outcome"] == "goal"
                        for _ in range(conditional_shots))
            shot_goal_prob = goals / conditional_shots
        res = _apply(engine, state, act, rng)
        n_actions += 1
        if record:
            for k, ev in enumerate(res.events):
                wp = state.to_world(ev["pos"])
                sim_events.append(SimEvent(t_ms=int(round((t_before if k == 0 else state.t) * 1000)),
                                           event_type=ev["type"], player_ids=ev["players"],
                                           x=round(float(wp[0]), 2), y=round(float(wp[1]), 2),
                                           detail=str(ev.get("detail", {}).get("reason", ""))))
        if n_actions == 1:
            first_outcome = res.outcome
            first_end = (float(state.ball[0]), float(state.ball[1]))
            # Pass completed / dribble succeeded / shot on target (goal or saved).
            first_success = res.outcome in ("completed", "loose_won", "success", "goal", "saved")
        if res.kind == "shot":
            shot_time = t_before
            if shot_time > horizon_s:
                shot_time = None
                outcome = "retained"
            elif res.outcome == "goal":
                outcome = "goal" if t_before + res.duration <= horizon_s else "retained"
            else:
                outcome = res.outcome
            break
        if res.turnover_to is not None:
            outcome = "turnover"
            break
        if res.outcome == "out_of_play":
            outcome = "out_of_play"
            break
        if state.t >= horizon_s or n_actions >= MAX_ACTIONS_PER_ROLLOUT:
            outcome = "retained"
            break
        # Control moment before the next decision.
        ctrl = float(rng[STREAM_MOVEMENT].uniform(0.35, 0.8))
        state.carrier = res.new_carrier
        state.ball = state.pos[state.carrier].copy()
        engine.control_phase(state, ctrl, rng[STREAM_MOVEMENT])
        if state.t >= horizon_s:
            outcome = "retained"
            break
        kind, recv, tgt, _ = engine.choose_action(state, rng[STREAM_POLICY])
        act = ResolvedAction(kind, state.carrier, recv, tgt)
    summary = RolloutSummary(
        outcome=outcome,
        t_end=min(state.t, horizon_s),
        shot_time=shot_time,
        first_success=first_success,
        first_outcome=first_outcome,
        progression=float(state.ball[0]) - start_x,
        n_actions=n_actions,
        end_ball=(float(state.ball[0]), float(state.ball[1])),
        first_end_ball=first_end,
        shot_goal_prob=shot_goal_prob,
    )
    frames = recorder.frames if recorder else []
    if frames:
        cutoff = int(math.ceil(summary.t_end * 1000)) + 600
        frames = [f for f in frames if f.t_ms <= cutoff]
    return summary, frames, sim_events


@dataclass
class StepResult:
    """One realized action (plus the control moment before the next decision)."""

    state: EngineState
    phase: PhaseResult
    possession_retained: bool
    terminal_outcome: str | None
    frames: list[TrackingFrame]
    events: list[SimEvent]
    duration_s: float


def run_first_action(base: EngineState, first: ResolvedAction, rng: RolloutRng, record: bool = True,
                     defense=None) -> StepResult:
    """Replays only the first action of rollout `rng` (same random streams as `run_rollout`).

    If possession is retained the new carrier takes the same control moment a rollout would, so the
    returned state is a valid starting point for the next decision. Otherwise the step is terminal.
    """
    state = base.copy()
    recorder = _Recorder(state) if record else None
    engine = Engine(record=recorder, defense=defense)
    events: list[SimEvent] = []
    t0 = state.t
    res = _apply(engine, state, first, rng)
    for k, ev in enumerate(res.events):
        wp = state.to_world(ev["pos"])
        events.append(SimEvent(t_ms=int(round((t0 if k == 0 else state.t) * 1000)), event_type=ev["type"],
                               player_ids=ev["players"], x=round(float(wp[0]), 2), y=round(float(wp[1]), 2),
                               detail=str(ev.get("detail", {}).get("reason", ""))))
    terminal: str | None = None
    if res.kind == "shot":
        terminal = res.outcome
    elif res.turnover_to is not None:
        terminal = "turnover"
    elif res.outcome == "out_of_play":
        terminal = "out_of_play"
    retained = terminal is None
    if retained:
        ctrl = float(rng[STREAM_MOVEMENT].uniform(0.35, 0.8))
        state.carrier = res.new_carrier
        state.ball = state.pos[state.carrier].copy()
        engine.control_phase(state, ctrl, rng[STREAM_MOVEMENT])
    frames = recorder.frames if recorder else []
    return StepResult(state=state, phase=res, possession_retained=retained, terminal_outcome=terminal,
                      frames=frames, events=events, duration_s=state.t - t0)

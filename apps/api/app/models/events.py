from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .common import SCHEMA_VERSION, Contract, FrozenContract


class EventType(StrEnum):
    MATCH_STARTED = "MATCH_STARTED"
    MATCH_ENDED = "MATCH_ENDED"
    PASS_ATTEMPTED = "PASS_ATTEMPTED"
    PASS_COMPLETED = "PASS_COMPLETED"
    PASS_FAILED = "PASS_FAILED"
    SHOT_ATTEMPTED = "SHOT_ATTEMPTED"
    SHOT_BLOCKED = "SHOT_BLOCKED"
    SHOT_SAVED = "SHOT_SAVED"
    SHOT_MISSED = "SHOT_MISSED"
    GOAL = "GOAL"
    DRIBBLE_ATTEMPTED = "DRIBBLE_ATTEMPTED"
    DRIBBLE_COMPLETED = "DRIBBLE_COMPLETED"
    DRIBBLE_FAILED = "DRIBBLE_FAILED"
    TACKLE = "TACKLE"
    INTERCEPTION = "INTERCEPTION"
    POSSESSION_CHANGED = "POSSESSION_CHANGED"
    PRESSURE_APPLIED = "PRESSURE_APPLIED"
    BALL_OUT_OF_PLAY = "BALL_OUT_OF_PLAY"
    RESTART = "RESTART"
    PLAYER_POSITION_UPDATED = "PLAYER_POSITION_UPDATED"
    BALL_POSITION_UPDATED = "BALL_POSITION_UPDATED"


ACTION_EVENTS = {EventType.PASS_ATTEMPTED, EventType.SHOT_ATTEMPTED, EventType.DRIBBLE_ATTEMPTED}
MAJOR_EVENTS = {EventType.GOAL, EventType.MATCH_ENDED}


class EventDetails(Contract):
    """Event-specific fields. Every field is optional; which ones are set depends on event type."""

    receiver_id: str | None = None
    intended_receiver_id: str | None = None
    pass_length_m: float | None = None
    ball_speed_mps: float | None = None
    shot_speed_mps: float | None = None
    distance_to_goal_m: float | None = None
    modeled_scoring_probability: float | None = Field(
        default=None, description="Model estimate (not observed). Synthetic, uncalibrated."
    )
    pass_difficulty: float | None = Field(default=None, description="Model estimate in [0,1].")
    outcome: str | None = None
    won_by_id: str | None = None
    lost_by_id: str | None = None
    pressure_count: int | None = None
    nearest_defender_m: float | None = None
    restart_type: str | None = None
    score_home: int | None = None
    score_away: int | None = None
    positions: dict[str, tuple[float, float]] | None = None
    duration_ms: int | None = None
    scripted: bool | None = None


class MatchEvent(FrozenContract):
    """Immutable synthetic match event. `x/y` are world coordinates in metres."""

    schema_version: str = SCHEMA_VERSION
    event_id: str
    match_id: str
    seq: int
    sim_time_ms: int = Field(description="Milliseconds since the start of the simulated segment")
    match_clock_ms: int = Field(description="Match clock in milliseconds")
    event_type: EventType
    team_id: str | None = None
    player_ids: list[str] = []
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    snapshot_id: str | None = None
    details: EventDetails = EventDetails()


class TrackingFrame(FrozenContract):
    """Positions of ball and all players at one instant (world coords, metres)."""

    t_ms: int
    ball: tuple[float, float, float]
    players: dict[str, tuple[float, float]]
    possessor_id: str | None = None

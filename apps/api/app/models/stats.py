from __future__ import annotations

from pydantic import Field

from .common import Contract


class TeamStats(Contract):
    team_id: str
    passes_attempted: int = 0
    passes_completed: int = 0
    pass_accuracy: float | None = None
    mean_pass_length_m: float | None = None
    mean_pass_difficulty_model: float | None = Field(default=None, description="Model estimate, not observed")
    max_ball_speed_mps: float | None = None
    shots: int = 0
    shots_on_target: int = 0
    goals: int = 0
    total_modeled_shot_quality: float = Field(default=0.0, description="Sum of modeled scoring probabilities")
    interceptions: int = 0
    tackles: int = 0
    dribbles_attempted: int = 0
    dribbles_completed: int = 0
    possession_changes_won: int = 0
    pressure_events: int = 0
    possession_share: float | None = None


class PlayerStats(Contract):
    player_id: str
    name: str
    team_id: str
    passes_attempted: int = 0
    passes_completed: int = 0
    key_passes: int = 0
    shots: int = 0
    goals: int = 0
    modeled_shot_quality: float = 0.0
    interceptions: int = 0
    tackles: int = 0
    dribbles_completed: int = 0
    turnovers: int = 0
    involvement: int = 0


class MatchStateView(Contract):
    match_id: str
    last_seq: int
    sim_time_ms: int
    match_clock_ms: int
    score: dict[str, int]
    possession_team_id: str | None
    ball: tuple[float, float] | None
    team_stats: dict[str, TeamStats]
    player_stats: list[PlayerStats]
    recent_event_ids: list[str]
    duplicates_ignored: int
    reordered_events: int
    decisions_detected: int

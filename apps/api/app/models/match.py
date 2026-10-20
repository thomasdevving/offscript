from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import SCHEMA_VERSION, Contract

Role = Literal["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
MatchStatus = Literal["scheduled", "live", "finished"]


class Team(Contract):
    team_id: str
    name: str
    short_name: str
    color_primary: str
    color_secondary: str
    formation: str


class Player(Contract):
    player_id: str
    team_id: str
    name: str
    short_name: str
    shirt_number: int
    role: Role
    max_speed_mps: float = Field(ge=5.0, le=10.5)
    acceleration_mps2: float = Field(ge=2.0, le=8.0)
    reaction_time_s: float = Field(ge=0.1, le=0.6)
    technique: float = Field(ge=0.0, le=1.0, description="Passing execution quality")
    finishing: float = Field(ge=0.0, le=1.0)
    dribbling: float = Field(ge=0.0, le=1.0)
    stamina: float = Field(default=1.0, ge=0.0, le=1.0)
    starting: bool = True


class SimulationSettings(Contract):
    mode: Literal["scenario", "procedural"]
    seed: int
    simulator_version: str
    frame_rate_hz: int
    description: str


class MatchInfo(Contract):
    schema_version: str = SCHEMA_VERSION
    match_id: str
    title: str
    scenario_id: str | None = None
    home: Team
    away: Team
    players: list[Player]
    settings: SimulationSettings
    period: int
    start_clock_ms: int
    end_clock_ms: int
    duration_ms: int
    initial_score: dict[str, int]
    final_score: dict[str, int]
    status: MatchStatus = "finished"
    home_attack_direction_first_half: int = 1
    description: str = ""
    tags: list[str] = []


class MatchSummary(Contract):
    match_id: str
    title: str
    scenario_id: str | None
    home: str
    away: str
    period: int
    start_clock: str
    duration_s: float
    mode: str
    description: str
    decision_count: int

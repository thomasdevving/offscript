from __future__ import annotations

from pydantic import Field

from .common import SCHEMA_VERSION, SIMULATOR_VERSION, FrozenContract


class PlayerState(FrozenContract):
    player_id: str
    team_id: str
    x: float = Field(ge=-1.0, le=106.0)
    y: float = Field(ge=-1.0, le=69.0)
    vx: float = 0.0
    vy: float = 0.0
    facing: float = 0.0


class BallState(FrozenContract):
    x: float
    y: float
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    possessor_id: str | None = None
    last_touch_id: str | None = None
    in_play: bool = True
    current_event: str | None = None


class MatchStateSnapshot(FrozenContract):
    """Immutable, reconstructable moment of the match (world coordinates).

    Counterfactual simulations always start from exactly one snapshot, and never use
    information recorded after `sim_time_ms`.
    """

    schema_version: str = SCHEMA_VERSION
    snapshot_id: str
    match_id: str
    sim_time_ms: int
    match_clock_ms: int
    period: int
    possession_team_id: str
    attack_direction: dict[str, int] = Field(description="team_id -> +1 (towards x=105) or -1")
    ball: BallState
    players: list[PlayerState]
    off_pitch_player_ids: list[str] = []
    score: dict[str, int]
    source_event_id: str | None = None
    seed: int
    simulator_version: str = SIMULATOR_VERSION

    def player(self, player_id: str) -> PlayerState | None:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

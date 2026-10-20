from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Contract

ActionType = Literal["shoot", "pass", "dribble"]


class DecisionTrigger(StrEnum):
    SHOT_WITH_TEAMMATE_AVAILABLE = "SHOT_WITH_TEAMMATE_AVAILABLE"
    DIFFICULT_PASS = "DIFFICULT_PASS"
    HIGH_VALUE_POSSESSION = "HIGH_VALUE_POSSESSION"
    MULTIPLE_OPTIONS = "MULTIPLE_OPTIONS"
    DANGEROUS_TURNOVER = "DANGEROUS_TURNOVER"
    DECISION_UNDER_PRESSURE = "DECISION_UNDER_PRESSURE"
    MISSED_FORWARD_PASS = "MISSED_FORWARD_PASS"


class CandidateAction(Contract):
    action_id: str
    action_type: ActionType
    actor_id: str
    target_player_id: str | None = None
    target_x: float | None = Field(default=None, description="World x of the intended target point")
    target_y: float | None = Field(default=None, description="World y of the intended target point")
    initial_state_id: str
    is_actual: bool = False
    label: str = ""
    source: Literal["observed", "generator", "agent"] = "generator"
    features: dict[str, float] = {}


class DecisionFeatures(Contract):
    distance_to_goal_m: float
    goal_angle_deg: float
    pressure_count_5m: int
    nearest_defender_m: float
    open_teammates: int
    forward_options: int
    zone_value: float
    actual_shot_quality: float | None = None
    actual_pass_difficulty: float | None = None
    best_alternative_gain_estimate: float | None = Field(
        default=None, description="Cheap heuristic estimate used only for triage, never shown as a result"
    )


class DecisionPoint(Contract):
    decision_point_id: str
    match_id: str
    snapshot_id: str
    event_id: str
    actor_id: str
    actor_name: str
    team_id: str
    sim_time_ms: int
    match_clock_ms: int
    actual_action: CandidateAction
    actual_outcome: str
    outcome_event_id: str | None = None
    outcome_time_ms: int | None = None
    triggers: list[DecisionTrigger]
    features: DecisionFeatures
    candidate_score: float = Field(description="Deterministic triage score in [0,1]")
    source: Literal["detector", "manual"] = "detector"
    analysis_ids: list[str] = []

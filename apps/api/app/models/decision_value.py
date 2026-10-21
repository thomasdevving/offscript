from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract

DecisionValueScope = Literal["player", "team", "match"]


class DecisionValueItem(Contract):
    """Decision Value Added of one analysed decision (probabilities, not percentages)."""

    decision_point_id: str
    analysis_id: str
    match_clock_ms: int
    player_id: str
    player_name: str
    team_id: str
    chosen_action_id: str
    chosen_label: str
    chosen_p_goal: float
    best_action_id: str = Field(description="Option with the highest estimated P(goal); the chosen action when no "
                                            "alternative scored higher")
    best_label: str
    best_p_goal: float
    best_alternative_action_id: str = Field(description="Highest-scoring option other than the chosen action")
    paired_diff: float = Field(description="Paired mean of goal(chosen) - goal(best alternative) over rollouts")
    paired_ci95_low: float
    paired_ci95_high: float
    dva: float = Field(le=0.0, description="min(0, paired_diff) = P(goal | chosen) - P(goal | best option)")
    ci95_low: float = Field(le=0.0, description="min(0, paired_ci95_low)")
    ci95_high: float = Field(le=0.0, description="min(0, paired_ci95_high)")
    clearly_better_alternative: bool = Field(description="The paired 95% interval of the best alternative lies "
                                                         "entirely above the chosen action")
    alternatives: int
    n_rollouts: int


class DecisionValueAggregate(Contract):
    scope: DecisionValueScope
    key: str = Field(description="Player id, team id or match id")
    name: str
    team_id: str | None = None
    n_decisions: int
    enough_decisions: bool = Field(description="False below the minimum sample; sums, means and intervals are then "
                                               "withheld")
    dva_sum: float | None = None
    dva_sum_ci95_low: float | None = None
    dva_sum_ci95_high: float | None = None
    dva_mean: float | None = None
    dva_mean_ci95_low: float | None = None
    dva_mean_ci95_high: float | None = None
    clear_misses: int = Field(default=0, description="Decisions with a clearly better alternative under the model")


class DecisionValueReport(Contract):
    match_id: str
    generated_at: str
    metric: Literal["p_goal_within_horizon"] = "p_goal_within_horizon"
    horizon_s: float | None = None
    min_decisions: int
    decisions_detected: int
    decisions_analysed: int = Field(description="Detected or manual decisions with a verified analysis")
    decisions_pending: int = Field(description="Decisions whose analysis is still pending or running")
    decisions: list[DecisionValueItem]
    players: list[DecisionValueAggregate]
    teams: list[DecisionValueAggregate]
    match: DecisionValueAggregate
    method: str
    disclaimer: str

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import SIMULATOR_VERSION, Contract, JobStatus
from .events import TrackingFrame

RolloutOutcome = Literal["goal", "saved", "blocked", "off_target", "turnover", "out_of_play", "retained"]
ROLLOUT_OUTCOMES: tuple[RolloutOutcome, ...] = (
    "goal",
    "saved",
    "blocked",
    "off_target",
    "turnover",
    "out_of_play",
    "retained",
)
ComparisonVerdict = Literal["more_promising", "less_promising", "similar", "inconclusive"]


class SimulationConfig(Contract):
    horizon_s: float = Field(default=10.0, ge=4.0, le=15.0)
    rollouts: int = Field(default=200, ge=20, le=500)
    seed: int = 0
    simulator_version: str = SIMULATOR_VERSION
    common_random_numbers: bool = True
    time_budget_s: float = Field(default=20.0, gt=0, le=120)
    metric: Literal["p_goal_within_horizon"] = "p_goal_within_horizon"


class ProbabilityEstimate(Contract):
    value: float = Field(ge=0.0, le=1.0)
    ci95_low: float = Field(ge=0.0, le=1.0)
    ci95_high: float = Field(ge=0.0, le=1.0)
    successes: int
    trials: int
    method: Literal["wilson"] = "wilson"


class ActionResult(Contract):
    action_id: str
    n_rollouts: int
    p_goal: ProbabilityEstimate = Field(description="P(goal within horizon | state, action) under the model")
    p_shot: ProbabilityEstimate
    p_turnover: ProbabilityEstimate
    p_first_action_success: ProbabilityEstimate = Field(
        description="Completion rate of the first action itself (pass completed, dribble succeeded, shot on target)"
    )
    mean_time_to_shot_s: float | None = None
    mean_progression_m: float = Field(description="Mean ball progression towards goal at rollout end")
    outcome_distribution: dict[str, float]
    outcome_counts: dict[str, int]
    representative_rollout: int
    representative_outcome: str
    example_rollouts: dict[str, int] = Field(default_factory=dict, description="outcome -> rollout index")
    first_action_detail: dict[str, float] = Field(default_factory=dict)


class PairwiseComparison(Contract):
    action_id: str
    baseline_action_id: str
    diff_p_goal: float
    diff_ci95_low: float
    diff_ci95_high: float
    paired: bool
    verdict: ComparisonVerdict
    diff_p_shot: float = 0.0
    diff_p_shot_ci95_low: float = 0.0
    diff_p_shot_ci95_high: float = 0.0
    diff_p_turnover: float = 0.0
    diff_p_turnover_ci95_low: float = 0.0
    diff_p_turnover_ci95_high: float = 0.0
    secondary_note: str = ""


class SimulationRun(Contract):
    simulation_run_id: str
    analysis_id: str
    snapshot_id: str
    simulator_version: str = SIMULATOR_VERSION
    config: SimulationConfig
    status: JobStatus = "pending"
    partial: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: float | None = None
    results: list[ActionResult] = []
    comparisons: list[PairwiseComparison] = []
    ranking: list[str] = []
    overall_verdict: ComparisonVerdict | None = None
    error: str | None = None


class SimEvent(Contract):
    t_ms: int
    event_type: str
    player_ids: list[str] = []
    x: float
    y: float
    detail: str = ""


class Trajectory(Contract):
    """One sampled continuation (world coordinates). Always a simulation, never an observation."""

    kind: Literal["simulated"] = "simulated"
    simulation_run_id: str
    action_id: str
    rollout_index: int
    seed_key: list[int]
    outcome: str
    terminated_reason: str
    selection_rule: str
    frames: list[TrackingFrame]
    events: list[SimEvent]
    start_match_clock_ms: int

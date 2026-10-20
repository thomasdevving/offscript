"""Football Multiverse contracts: branching timelines, adversarial planning, defensive strategies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .common import SIMULATOR_VERSION, Contract, JobStatus
from .decisions import CandidateAction
from .events import TrackingFrame
from .narrative import Narrative
from .simulation import ProbabilityEstimate, SimEvent
from .state import MatchStateSnapshot
from .workflow import AgentStep, HandoffRecord

DefensiveStyle = Literal["balanced", "press", "cover_lane", "track_runner", "protect_central", "contain"]
DefensiveRole = Literal["press", "cover_lane", "track_runner"]
InteractionMode = Literal["manual", "assisted", "autonomous"]
SampleKind = Literal["representative", "high_upside", "defensive_success", "random"]
NodeStatus = Literal["decision", "terminal", "pending", "running", "failed", "depth_limit"]


class DefensiveAssignment(Contract):
    defender_id: str
    role: DefensiveRole
    target_player_id: str | None = Field(default=None, description="Attacker covered/tracked (cover_lane, track_runner)")
    target_x: float | None = Field(default=None, description="World x of a lane point (cover_lane without player)")
    target_y: float | None = None


class DefensiveStrategy(Contract):
    strategy_id: str
    style: DefensiveStyle
    label: str
    assignments: list[DefensiveAssignment] = []
    description: str = ""


class ActionSpec(Contract):
    """A user/agent requested action at a node. Never silently converted into another action."""

    action_type: Literal["shoot", "pass", "dribble"] | None = None
    target_player_id: str | None = None
    target_x: float | None = None
    target_y: float | None = None
    candidate_id: str | None = Field(default=None, description="Use a generated candidate as-is")

    @model_validator(mode="after")
    def _one_of(self) -> ActionSpec:
        if self.candidate_id is None and self.action_type is None:
            raise ValueError("either candidate_id or action_type is required")
        return self


class ActionValidation(Contract):
    ok: bool
    code: str
    message: str
    action: CandidateAction | None = None


class AttackProposal(Contract):
    proposal_id: str
    round: int
    action: CandidateAction
    source: Literal["user", "attacking_agent", "actual"]
    rationale: str = ""
    follow_up: str = ""


class DefenseProposal(Contract):
    proposal_id: str
    round: int
    strategy: DefensiveStrategy
    source: Literal["defending_agent", "baseline"]
    rationale: str = ""
    targets_action_id: str | None = None


class MatrixCell(Contract):
    action_id: str
    strategy_id: str
    xg: float = Field(description="Modelled expected goals within the horizon (conditional Monte Carlo)")
    xg_ci95_low: float
    xg_ci95_high: float
    p_goal: ProbabilityEstimate
    p_shot: ProbabilityEstimate
    p_turnover: ProbabilityEstimate
    p_first_action_success: ProbabilityEstimate
    n_rollouts: int
    cached: bool = False
    round: int = 1


class PlanningRound(Contract):
    round: int
    attack_proposal_ids: list[str]
    defense_proposal_ids: list[str]
    new_cells: int
    best_robust_action_id: str | None = None
    best_robust_value: float | None = None
    note: str = ""


class StrategySummary(Contract):
    best_expected_action_id: str | None = Field(default=None, description="Highest mean value across defensive responses")
    most_robust_action_id: str | None = Field(default=None, description="Highest worst-case value (maximin)")
    highest_upside_action_id: str | None = Field(default=None, description="Highest best-case value")
    selected_action_id: str
    defensive_counter_id: str = Field(description="Defending agent's chosen response to the selected action")
    selected_value_vs_counter: float
    selected_value_vs_baseline: float
    counter_effect_pp: float = Field(description="Value change caused by the counter vs balanced defence (points)")
    per_action: dict[str, dict[str, float]] = {}


class Transition(Contract):
    """The realized step from a parent node to a child node (one sampled continuation)."""

    parent_snapshot_id: str
    child_snapshot_id: str | None
    action_id: str
    strategy_id: str
    sample_kind: SampleKind
    rollout_index: int
    seed: int
    first_outcome: str
    terminal_outcome: str | None = None
    duration_ms: int
    frames: list[TrackingFrame]
    events: list[SimEvent]
    selection_rule: str


class MultiversePlanning(Contract):
    planning_id: str
    node_id: str
    snapshot_id: str
    correlation_id: str
    state_version: int = 0
    updated_at: str | None = None
    max_rounds: int = 3
    user_action_id: str | None = None
    mode: InteractionMode
    status: JobStatus = "pending"
    rounds: list[PlanningRound] = []
    attack_proposals: list[AttackProposal] = []
    defense_proposals: list[DefenseProposal] = []
    matrix: list[MatrixCell] = []
    rollouts_per_cell: int = 0
    summary: StrategySummary | None = None
    termination_reason: str = ""
    verification_status: str = "pending"
    verification_checks: list[dict[str, Any]] = []
    narratives: list[Narrative] = []
    steps: list[AgentStep] = []
    handoffs: list[HandoffRecord] = []
    errors: list[str] = []
    degraded: bool = False
    live_model_calls: int = 0
    duration_ms: float | None = None
    cache_hits: int = 0
    cells_computed: int = 0


class BranchNode(Contract):
    node_id: str
    session_id: str
    kind: Literal["root", "simulated", "observed"] = "simulated"
    parent_node_id: str | None
    depth: int
    status: NodeStatus
    snapshot_id: str
    match_clock_ms: int
    sim_time_ms: int
    carrier_id: str | None
    possession_team_id: str
    score: dict[str, int]
    entering_action: CandidateAction | None = None
    entering_action_source: Literal["user", "attacking_agent", "actual"] | None = None
    entering_strategy: DefensiveStrategy | None = None
    transition: Transition | None = None
    planning_id: str | None = Field(default=None, description="Planning that produced this node (from its parent)")
    children: list[str] = []
    label: str = ""
    outcome_label: str = ""
    created_at: str
    error: str | None = None
    fingerprint: str | None = None
    recommendation_planning_id: str | None = Field(default=None, description="Assisted-mode plan for this node")


class MultiverseSession(Contract):
    session_id: str
    match_id: str
    decision_point_id: str
    root_node_id: str
    mode: InteractionMode
    created_at: str
    simulator_version: str = SIMULATOR_VERSION
    seed: int
    max_depth: int
    max_children: int
    max_nodes: int
    actual_action: CandidateAction
    nodes: dict[str, BranchNode] = {}
    snapshots: dict[str, MatchStateSnapshot] = {}
    plannings: dict[str, MultiversePlanning] = {}


class SessionCreate(Contract):
    match_id: str | None = None
    decision_point_id: str
    mode: InteractionMode = "manual"


class BranchActionRequest(Contract):
    action: ActionSpec | None = Field(default=None, description="Omit in assisted/autonomous continuation")
    mode: InteractionMode | None = None
    sample_kind: SampleKind = "representative"
    max_rounds: int | None = Field(default=None, ge=1, le=3)


class AutoPlayRequest(Contract):
    max_steps: int = Field(default=3, ge=1, le=5)
    sample_kind: SampleKind = "representative"


class CompareRequest(Contract):
    node_a: str
    node_b: str
    language: Literal["en", "nl"] = "en"


class PathStep(Contract):
    node_id: str
    depth: int
    action_label: str | None
    action_source: str | None
    strategy_label: str | None
    first_outcome: str | None
    terminal_outcome: str | None
    match_clock_ms: int
    p_goal_vs_counter: float | None = None


class BranchComparison(Contract):
    node_a: str
    node_b: str
    common_ancestor: str
    steps_a: list[PathStep]
    steps_b: list[PathStep]
    metrics_a: dict[str, float | str | None]
    metrics_b: dict[str, float | str | None]
    explanation: str
    evidence_refs: list[str] = []


class MultiverseJob(Contract):
    job_id: str
    session_id: str
    parent_node_id: str
    child_node_id: str | None = None
    planning_id: str | None = None
    status: JobStatus = "pending"
    progress: list[str] = []
    error: str | None = None
    created_at: str

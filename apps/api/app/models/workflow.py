from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import Contract

AgentName = Literal[
    "attacking_agent",
    "defending_agent",
    "decision_agent",
    "strategy_agent",
    "simulation_agent",
    "verification_agent",
    "explanation_agent",
    "publisher",
]
StepStatus = Literal["running", "completed", "failed", "rejected", "skipped", "degraded"]
WorkflowStatus = Literal["pending", "running", "completed", "unavailable", "failed", "cancelled", "timed_out"]
FaultInjection = Literal["invalid_candidate", "contradictory_claim", "model_unavailable", "simulation_timeout"]


class ToolCallRecord(Contract):
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = {}
    result_summary: Any = None
    status: Literal["ok", "error"] = "ok"
    duration_ms: float = 0.0
    started_at: str


class AgentStep(Contract):
    step_id: str
    agent: AgentName
    task: str
    attempt: int = 1
    status: StepStatus = "running"
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    model: str = Field(description="'foundry:<deployment>' for live model calls, 'policy' for the deterministic planner")
    live_model: bool = False
    tool_calls: list[ToolCallRecord] = []
    output: dict[str, Any] = {}
    handoff_to: str | None = None
    handoff_reason: str | None = None
    error: str | None = None
    notes: list[str] = []


class HandoffRecord(Contract):
    from_agent: str
    to_agent: str
    reason: str
    at: str


class RejectedCandidate(Contract):
    proposal: dict[str, Any]
    reason: str
    stage: str


class AnalysisWorkflowState(Contract):
    """Shared, typed state every agent reads from and writes to (one per analysis)."""

    analysis_id: str
    match_id: str
    snapshot_id: str
    decision_point_id: str
    correlation_id: str
    state_version: int = 0
    actual_action_id: str | None = None
    candidate_action_ids: list[str] = []
    rejected_candidates: list[RejectedCandidate] = []
    revision_feedback: list[str] = []
    simulation_run_id: str | None = None
    simulation_budget: int | None = None
    verification_status: str = "pending"
    verification_issues: list[str] = []
    retry_count: int = 0
    explanation_retries: int = 0
    narrative_ids: list[str] = []
    workflow_status: WorkflowStatus = "pending"
    steps: list[AgentStep] = []
    handoffs: list[HandoffRecord] = []
    errors: list[str] = []
    degraded: bool = False
    fault_injection: list[FaultInjection] = []
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract
from .decisions import CandidateAction
from .narrative import Narrative
from .simulation import SimulationRun
from .verification import VerificationRecord
from .workflow import AnalysisWorkflowState, FaultInjection

AnalysisStatus = Literal["pending", "running", "verified", "unavailable", "failed", "cancelled"]


class ModelInfo(Contract):
    agent_mode: Literal["foundry", "policy"]
    provider: str
    deployment: str | None = None
    live_model_calls: int = 0
    policy_fallbacks: int = 0
    degraded: bool = False


class CounterfactualAnalysis(Contract):
    analysis_id: str
    match_id: str
    decision_point_id: str
    snapshot_id: str
    correlation_id: str
    status: AnalysisStatus = "pending"
    created_at: str
    completed_at: str | None = None
    candidates: list[CandidateAction] = []
    actual_action_id: str | None = None
    simulation: SimulationRun | None = None
    verification: VerificationRecord | None = None
    narratives: list[Narrative] = []
    workflow: AnalysisWorkflowState
    model: ModelInfo
    decision_summary: dict[str, str | float | int | bool | None] = {}
    cached: bool = Field(default=False, description="True when served from the analysis cache (replay)")
    cache_key: str | None = None
    fault_injection: list[FaultInjection] = []
    unavailable_reason: str | None = None


class AnalyzeRequest(Contract):
    rollouts: int | None = Field(default=None, ge=20, le=500)
    horizon_s: float | None = Field(default=None, ge=4.0, le=15.0)
    fault_injection: list[FaultInjection] = []
    force_refresh: bool = False
    languages: list[Literal["en", "nl"]] = ["en", "nl"]


class SimulateRequest(Contract):
    rollouts: int = Field(default=200, ge=20, le=500)
    horizon_s: float | None = Field(default=None, ge=4.0, le=15.0)
    action_ids: list[str] | None = None

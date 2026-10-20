"""Typed, versioned data contracts shared by the backend, the API and (via OpenAPI) the web app."""

from .analysis import AnalyzeRequest, CounterfactualAnalysis, ModelInfo, SimulateRequest
from .common import SCHEMA_VERSION, SIMULATOR_VERSION, Language, ViewerMode
from .decisions import CandidateAction, DecisionFeatures, DecisionPoint, DecisionTrigger
from .events import EventDetails, EventType, MatchEvent, TrackingFrame
from .match import MatchInfo, MatchSummary, Player, SimulationSettings, Team
from .narrative import Narrative
from .overlay import Overlay, OverlayDataField, OverlayExpiry
from .recap import Recap
from .simulation import (
    ActionResult,
    PairwiseComparison,
    ProbabilityEstimate,
    SimEvent,
    SimulationConfig,
    SimulationRun,
    Trajectory,
)
from .state import BallState, MatchStateSnapshot, PlayerState
from .verification import EvidenceItem, VerificationCheck, VerificationRecord
from .workflow import AgentStep, AnalysisWorkflowState, HandoffRecord, ToolCallRecord

__all__ = [
    "SCHEMA_VERSION",
    "SIMULATOR_VERSION",
    "ActionResult",
    "AgentStep",
    "AnalysisWorkflowState",
    "AnalyzeRequest",
    "BallState",
    "CandidateAction",
    "CounterfactualAnalysis",
    "DecisionFeatures",
    "DecisionPoint",
    "DecisionTrigger",
    "EventDetails",
    "EventType",
    "EvidenceItem",
    "HandoffRecord",
    "Language",
    "MatchEvent",
    "MatchInfo",
    "MatchStateSnapshot",
    "MatchSummary",
    "ModelInfo",
    "Narrative",
    "Overlay",
    "OverlayDataField",
    "OverlayExpiry",
    "PairwiseComparison",
    "Player",
    "PlayerState",
    "ProbabilityEstimate",
    "Recap",
    "SimEvent",
    "SimulateRequest",
    "SimulationConfig",
    "SimulationRun",
    "SimulationSettings",
    "Team",
    "ToolCallRecord",
    "TrackingFrame",
    "Trajectory",
    "VerificationCheck",
    "VerificationRecord",
    "ViewerMode",
]

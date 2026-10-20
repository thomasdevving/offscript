/**
 * PARALLEL shared contracts.
 *
 * Generated from the backend's Pydantic models via FastAPI's OpenAPI schema
 * (`npm run contracts`). Do not edit api.d.ts by hand; CI fails when it is stale.
 */
import type { components } from "./api";

type S = components["schemas"];

export type MatchSummary = S["MatchSummary"];
export type MatchInfo = S["MatchInfo"];
export type Player = S["Player"];
export type Team = S["Team"];
export type MatchEvent = S["MatchEvent"];
export type TrackingFrame = S["TrackingFrame"];
export type MatchStateSnapshot = S["MatchStateSnapshot"];
export type MatchStateView = S["MatchStateView"];
export type DecisionPoint = S["DecisionPoint"];
export type CandidateAction = S["CandidateAction"];
export type CounterfactualAnalysis = S["CounterfactualAnalysis"];
export type AnalyzeRequest = S["AnalyzeRequest"];
export type SimulationRun = S["SimulationRun"];
export type ActionResult = S["ActionResult"];
export type PairwiseComparison = S["PairwiseComparison"];
export type ProbabilityEstimate = S["ProbabilityEstimate"];
export type Trajectory = S["Trajectory"];
export type SimEvent = S["SimEvent"];
export type Narrative = S["Narrative"];
export type Overlay = S["Overlay"];
export type EvidenceItem = S["EvidenceItem"];
export type VerificationRecord = S["VerificationRecord"];
export type VerificationCheck = S["VerificationCheck"];
export type AnalysisWorkflowState = S["AnalysisWorkflowState"];
export type AgentStep = S["AgentStep"];
export type ToolCallRecord = S["ToolCallRecord"];
export type HandoffRecord = S["HandoffRecord"];
export type Recap = S["Recap"];
export type TeamStats = S["TeamStats"];

export type ViewerMode = "casual" | "analyst" | "broadcaster";
export type Language = "en" | "nl";
export type FaultInjection = "invalid_candidate" | "contradictory_claim" | "model_unavailable" | "simulation_timeout";

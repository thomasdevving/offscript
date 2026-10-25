import type {
  AnalysisWorkflowState,
  AnalyzeRequest,
  CounterfactualAnalysis,
  DecisionPoint,
  DecisionValueReport,
  MatchEvent,
  MatchInfo,
  MatchStateSnapshot,
  MatchStateView,
  Overlay,
  Recap,
  Trajectory,
} from "@offscript/contracts";
import { API_BASE } from "./config";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    // Only requests with a body declare JSON: plain GETs stay "simple" cross-origin requests (no preflight).
    headers: { ...(init?.body ? { "content-type": "application/json" } : {}), ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface Health {
  status: string;
  agent_mode: "foundry" | "policy";
  foundry_configured: boolean;
  foundry_deployment: string | null;
  foundry_client_error: string | null;
  simulator_version: string;
  matches: number;
}

export interface ScenarioInfo {
  scenario_id: string;
  match_id: string;
  title: string;
  description: string;
  mode: string;
  seed: number;
  start_clock: string;
  duration_s: number | null;
  decision_count: number | null;
}

export const api = {
  health: () => req<Health>("/api/health"),
  scenarios: () => req<ScenarioInfo[]>("/api/scenarios"),
  match: (id: string) => req<MatchInfo>(`/api/matches/${id}`),
  events: (id: string) => req<MatchEvent[]>(`/api/matches/${id}/events`),
  state: (id: string, t?: number) => req<MatchStateView>(`/api/matches/${id}/state${t != null ? `?t_ms=${Math.round(t)}` : ""}`),
  decisions: (id: string) => req<DecisionPoint[]>(`/api/matches/${id}/decisions`),
  manualDecision: (matchId: string, eventId: string) =>
    req<DecisionPoint>(`/api/matches/${matchId}/events/${eventId}/decision`, { method: "POST" }),
  snapshot: (decisionId: string) => req<MatchStateSnapshot>(`/api/decisions/${decisionId}/snapshot`),
  analyze: (decisionId: string, body: Partial<AnalyzeRequest> = {}) =>
    req<CounterfactualAnalysis>(`/api/decisions/${decisionId}/analyze`, { method: "POST", body: JSON.stringify(body) }),
  analysis: (id: string) => req<CounterfactualAnalysis>(`/api/analyses/${id}`),
  workflow: (id: string) => req<AnalysisWorkflowState>(`/api/analyses/${id}/workflow`),
  trajectory: (id: string, actionId: string, rollout?: number) =>
    req<Trajectory>(`/api/analyses/${id}/trajectories/${encodeURIComponent(actionId)}${rollout != null ? `?rollout=${rollout}` : ""}`),
  overlays: (matchId: string) => req<Overlay[]>(`/api/matches/${matchId}/overlays`),
  analysisOverlays: (id: string) => req<Overlay[]>(`/api/analyses/${id}/overlays`),
  decisionValue: (matchId: string) => req<DecisionValueReport>(`/api/matches/${matchId}/decision-value`),
  analyseAllDecisions: (matchId: string) =>
    req<DecisionValueReport>(`/api/matches/${matchId}/decision-value/analyze`, { method: "POST" }),
  /** Adds verified narratives in another language to a finished analysis (instant, no new simulation). */
  addNarratives: (id: string, language: string) =>
    req<CounterfactualAnalysis>(`/api/analyses/${id}/narratives?language=${language}`, { method: "POST" }),
  recap: (matchId: string, language: string) =>
    req<Recap>(`/api/matches/${matchId}/recap?language=${language}`, { method: "POST" }),
};

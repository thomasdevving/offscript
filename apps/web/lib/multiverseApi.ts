import type {
  ActionSpec,
  ActionValidation,
  BranchComparison,
  BranchNode,
  CandidateAction,
  InteractionMode,
  MatchStateSnapshot,
  MultiverseJob,
  MultiversePlanning,
  SampleKind,
} from "@parallel/contracts";
import { API_BASE } from "./config";

export class MvError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: init?.body ? { "content-type": "application/json" } : {} });
  if (!res.ok) {
    let code = String(res.status);
    let msg = res.statusText;
    try {
      const b = await res.json();
      const d = b.detail;
      if (d && typeof d === "object" && "code" in d) {
        code = d.code;
        msg = d.message;
      } else if (Array.isArray(d)) {
        code = "INVALID_REQUEST";
        msg = d.map((x: { msg: string }) => x.msg).join("; ");
      } else if (typeof d === "string") msg = d;
    } catch {
      /* ignore */
    }
    throw new MvError(res.status, code, msg);
  }
  return (await res.json()) as T;
}

export interface MvSessionLite {
  session_id: string;
  match_id: string;
  decision_point_id: string;
  root_node_id: string;
  mode: InteractionMode;
  max_depth: number;
  max_children: number;
  max_nodes: number;
  actual_action: CandidateAction;
  node_count: number;
}

export interface TreeNode {
  node_id: string;
  parent_node_id: string | null;
  depth: number;
  status: string;
  kind: "root" | "simulated" | "observed";
  label: string;
  outcome: string;
  children: string[];
  match_clock_ms: number;
  source: string | null;
  strategy: string | null;
  value_vs_counter: number | null;
  verification: string | null;
  sample_kind: string | null;
}

export interface MvTree {
  session_id: string;
  root_node_id: string;
  nodes: TreeNode[];
  max_depth: number;
  mode: InteractionMode;
}

export interface PathFrames {
  node_id: string;
  duration_ms: number;
  frames: { t_ms: number; ball: [number, number, number]; players: Record<string, [number, number]>; possessor_id: string | null }[];
  events: { t_ms: number; event_type: string; player_ids: string[]; x: number; y: number; node_id: string }[];
  boundaries: { node_id: string; t_ms: number; label: string; outcome: string; kind: string }[];
  simulated: boolean;
}

export interface NodeOptions {
  node_id: string;
  options: CandidateAction[];
  actual: CandidateAction | null;
  recommendation_planning_id: string | null;
}

const enc = encodeURIComponent;

export const mvApi = {
  createSession: (decisionId: string, mode: InteractionMode) =>
    req<MvSessionLite>("/api/multiverse/sessions", { method: "POST", body: JSON.stringify({ decision_point_id: decisionId, mode }) }),
  session: (id: string) => req<MvSessionLite>(`/api/multiverse/sessions/${enc(id)}`),
  tree: (id: string) => req<MvTree>(`/api/multiverse/sessions/${enc(id)}/tree`),
  node: (id: string) => req<BranchNode>(`/api/multiverse/branches/${enc(id)}`),
  state: (id: string) => req<MatchStateSnapshot>(`/api/multiverse/branches/${enc(id)}/state`),
  options: (id: string) => req<NodeOptions>(`/api/multiverse/branches/${enc(id)}/options`),
  validate: (id: string, spec: ActionSpec) =>
    req<ActionValidation>(`/api/multiverse/branches/${enc(id)}/validate`, { method: "POST", body: JSON.stringify(spec) }),
  act: (id: string, spec: ActionSpec, mode: InteractionMode, sampleKind: SampleKind) =>
    req<MultiverseJob>(`/api/multiverse/branches/${enc(id)}/actions`, {
      method: "POST", body: JSON.stringify({ action: spec, mode, sample_kind: sampleKind }),
    }),
  recommend: (id: string) =>
    req<MultiverseJob>(`/api/multiverse/branches/${enc(id)}/continue`, { method: "POST", body: JSON.stringify({ mode: "assisted" }) }),
  autoPlay: (id: string, steps: number, sampleKind: SampleKind) =>
    req<MultiverseJob>(`/api/multiverse/branches/${enc(id)}/auto-play`, {
      method: "POST", body: JSON.stringify({ max_steps: steps, sample_kind: sampleKind }),
    }),
  job: (id: string) => req<MultiverseJob>(`/api/multiverse/jobs/${enc(id)}`),
  cancel: (nodeId: string) => req<{ cancelled: string[] }>(`/api/multiverse/branches/${enc(nodeId)}/cancel`, { method: "POST" }),
  trajectory: (id: string) => req<PathFrames>(`/api/multiverse/branches/${enc(id)}/trajectory`),
  planning: (id: string) => req<MultiversePlanning>(`/api/multiverse/plannings/${enc(id)}`),
  compare: (a: string, b: string, language: string) =>
    req<BranchComparison>("/api/multiverse/compare", { method: "POST", body: JSON.stringify({ node_a: a, node_b: b, language }) }),
};

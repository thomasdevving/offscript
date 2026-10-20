"use client";

import type {
  ActionSpec,
  ActionValidation,
  BranchComparison,
  BranchNode,
  InteractionMode,
  MatchStateSnapshot,
  MultiverseJob,
  MultiversePlanning,
  SampleKind,
} from "@parallel/contracts";
import { create } from "zustand";
import { wsUrl } from "./config";
import { MvError, mvApi, type MvSessionLite, type MvTree, type NodeOptions, type PathFrames } from "./multiverseApi";

export type ComposerType = "pass" | "pass_space" | "dribble" | "shoot" | null;

interface Composer {
  type: ComposerType;
  targetId: string | null;
  point: [number, number] | null;
  candidateId: string | null;
  validation: ActionValidation | null;
}

export interface LiveItem {
  event: string;
  text: string;
  at: number;
}

interface CompareState {
  a: string | null;
  b: string | null;
  data: BranchComparison | null;
  pathA: PathFrames | null;
  pathB: PathFrames | null;
  t: number;
  playing: boolean;
  speed: number;
  open: boolean;
  loading: boolean;
}

export interface MvState {
  session: MvSessionLite | null;
  tree: MvTree | null;
  selected: string | null;
  nodes: Record<string, BranchNode>;
  states: Record<string, MatchStateSnapshot>;
  options: Record<string, NodeOptions>;
  plannings: Record<string, MultiversePlanning>;
  interaction: InteractionMode;
  sampleKind: SampleKind;
  composer: Composer;
  job: MultiverseJob | null;
  live: LiveItem[];
  error: string | null;
  path: PathFrames | null;
  playT: number;
  playing: boolean;
  compare: CompareState;
  starting: boolean;
}

const emptyComposer: Composer = { type: null, targetId: null, point: null, candidateId: null, validation: null };
const emptyCompare: CompareState = {
  a: null, b: null, data: null, pathA: null, pathB: null, t: 0, playing: false, speed: 1, open: false, loading: false,
};

export const useMv = create<MvState>(() => ({
  session: null,
  tree: null,
  selected: null,
  nodes: {},
  states: {},
  options: {},
  plannings: {},
  interaction: "manual",
  sampleKind: "representative",
  composer: emptyComposer,
  job: null,
  live: [],
  error: null,
  path: null,
  playT: 0,
  playing: false,
  compare: emptyCompare,
  starting: false,
}));

const set = useMv.setState;
const get = useMv.getState;
let socket: WebSocket | null = null;

const storageKey = (decisionId: string) => `parallel.mv.${decisionId}`;

function safeStore(k: string, v: string | null) {
  try {
    if (v === null) localStorage.removeItem(k);
    else localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
}

function safeLoad(k: string): string | null {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
}

function errText(e: unknown): string {
  if (e instanceof MvError) return `${e.code}: ${e.message}`;
  return (e as Error).message;
}

const PROGRESS_TEXT: Record<string, string> = {
  agent_started: "agent started",
  attack_proposals: "Attacking agent proposed options",
  defense_proposals: "Defending agent proposed responses",
  cell: "Simulated a strategy pair",
  handoff: "Handoff",
  planning_completed: "Planning finished",
  tool_call: "Tool call",
};

function connect(sessionId: string) {
  socket?.close();
  try {
    socket = new WebSocket(wsUrl(`/ws/multiverse/${sessionId}`));
  } catch {
    return;
  }
  socket.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data as string);
      if (m.type !== "progress") return;
      let text = PROGRESS_TEXT[m.event] ?? m.event;
      if (m.event === "agent_started") text = `${String(m.agent).replace("_", " ")}: ${m.task ?? ""}`;
      if (m.event === "handoff") text = `${m.from} → ${m.to}: ${m.reason ?? ""}`;
      if (m.event === "cell") text = `Simulated ${m.action} vs ${m.strategy}${m.cached ? " (cached)" : ""}`;
      if (m.event === "attack_proposals") text = `Round ${m.round}: attack ${m.revised ? "revised → " : "→ "}${(m.actions ?? []).join(", ")}`;
      if (m.event === "defense_proposals") text = `Round ${m.round}: defence → ${(m.strategies ?? []).join(", ")}`;
      if (m.event === "tool_call") text = `${String(m.agent).replace("_", " ")} called ${m.tool}`;
      set({ live: [...get().live, { event: m.event, text, at: Date.now() }].slice(-40) });
    } catch {
      /* ignore */
    }
  };
}

async function refreshTree() {
  const s = get().session;
  if (!s) return;
  set({ tree: await mvApi.tree(s.session_id) });
}

async function trackJob(jobId: string): Promise<MultiverseJob> {
  for (let i = 0; i < 1500; i++) {
    const j = await mvApi.job(jobId);
    set({ job: j });
    if (!["pending", "running"].includes(j.status)) return j;
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("timeout waiting for the branch job");
}

export const mv = {
  async open(decisionId: string, matchId: string, opts: { fresh?: boolean } = {}): Promise<void> {
    set({ starting: true, error: null });
    try {
      let lite = null;
      const saved = opts.fresh ? null : safeLoad(storageKey(decisionId));
      if (saved) {
        try {
          lite = await mvApi.session(saved);
        } catch {
          lite = null;
        }
      }
      if (!lite || lite.match_id !== matchId) {
        lite = await mvApi.createSession(decisionId, get().interaction);
        safeStore(storageKey(decisionId), lite.session_id);
      }
      set({ session: lite, nodes: {}, states: {}, options: {}, plannings: {}, live: [], compare: emptyCompare,
        composer: emptyComposer, job: null });
      connect(lite.session_id);
      await refreshTree();
      await mv.select(lite.root_node_id);
    } catch (e) {
      set({ error: errText(e) });
    } finally {
      set({ starting: false });
    }
  },

  close(): void {
    socket?.close();
    socket = null;
    set({ session: null, tree: null, selected: null, path: null, compare: emptyCompare });
  },

  async newSession(): Promise<void> {
    const s = get().session;
    if (!s) return;
    await mv.open(s.decision_point_id, s.match_id, { fresh: true });
  },

  async select(nodeId: string, opts: { play?: boolean } = {}): Promise<void> {
    set({ selected: nodeId, composer: emptyComposer, error: null });
    const [node, path] = await Promise.all([mvApi.node(nodeId), mvApi.trajectory(nodeId)]);
    set({ nodes: { ...get().nodes, [nodeId]: node }, path });
    const lastStart = path.boundaries.length > 1 ? path.boundaries[path.boundaries.length - 2].t_ms : 0;
    set({ playT: opts.play ? lastStart : path.duration_ms, playing: !!opts.play });
    const tasks: Promise<unknown>[] = [];
    if (!get().states[nodeId]) tasks.push(mvApi.state(nodeId).then((st) => set({ states: { ...get().states, [nodeId]: st } })));
    if (node.status === "decision" && node.kind !== "observed")
      tasks.push(mvApi.options(nodeId).then((o) => set({ options: { ...get().options, [nodeId]: o } })));
    for (const pid of [node.planning_id, node.recommendation_planning_id]) {
      if (pid && !get().plannings[pid])
        tasks.push(mvApi.planning(pid).then((p) => set({ plannings: { ...get().plannings, [pid]: p } })));
    }
    await Promise.all(tasks);
  },

  async rewind(): Promise<void> {
    const sel = get().selected;
    const n = sel ? get().nodes[sel] : null;
    if (n?.parent_node_id) await mv.select(n.parent_node_id);
  },

  setInteraction(mode: InteractionMode): void {
    set({ interaction: mode });
  },
  setSampleKind(k: SampleKind): void {
    set({ sampleKind: k });
  },

  setComposer(type: ComposerType): void {
    set({ composer: { ...emptyComposer, type } });
    if (type === "shoot") void mv.validate({ action_type: "shoot" });
  },

  chooseCandidate(candidateId: string): void {
    set({ composer: { ...emptyComposer, type: null, candidateId } });
    void mv.validate({ candidate_id: candidateId } as ActionSpec);
  },

  async playerClicked(playerId: string): Promise<void> {
    const c = get().composer;
    if (c.type !== "pass") return;
    set({ composer: { ...c, targetId: playerId, point: null } });
    await mv.validate({ action_type: "pass", target_player_id: playerId });
  },

  async pitchClicked(x: number, y: number): Promise<void> {
    const c = get().composer;
    if (c.type !== "dribble" && c.type !== "pass_space") return;
    set({ composer: { ...c, point: [x, y], targetId: null } });
    await mv.validate({ action_type: c.type === "dribble" ? "dribble" : "pass", target_x: x, target_y: y });
  },

  async validate(spec: ActionSpec): Promise<void> {
    const sel = get().selected;
    if (!sel) return;
    try {
      const v = await mvApi.validate(sel, spec);
      set({ composer: { ...get().composer, validation: v } });
    } catch (e) {
      set({ composer: { ...get().composer, validation: { ok: false, code: "ERROR", message: errText(e) } } });
    }
  },

  async submit(): Promise<void> {
    const { selected, composer, interaction, sampleKind } = get();
    if (!selected || !composer.validation?.ok || !composer.validation.action) return;
    const a = composer.validation.action;
    const spec: ActionSpec = composer.candidateId
      ? ({ candidate_id: composer.candidateId } as ActionSpec)
      : a.action_type === "shoot" ? { action_type: "shoot" }
        : composer.targetId ? { action_type: "pass", target_player_id: composer.targetId }
          : { action_type: a.action_type, target_x: composer.point?.[0], target_y: composer.point?.[1] };
    await mv.runJob(() => mvApi.act(selected, spec, interaction === "autonomous" ? "manual" : interaction, sampleKind));
  },

  async recommend(): Promise<void> {
    const sel = get().selected;
    if (!sel) return;
    await mv.runJob(() => mvApi.recommend(sel), { selectChild: false });
    await mv.select(sel);
  },

  async acceptRecommendation(): Promise<void> {
    const sel = get().selected;
    const node = sel ? get().nodes[sel] : null;
    const plan = node?.recommendation_planning_id ? get().plannings[node.recommendation_planning_id] : null;
    const rec = plan?.summary?.most_robust_action_id;
    if (!sel || !rec) return;
    const opt = get().options[sel]?.options.find((o) => o.action_id === rec);
    if (opt) {
      await mv.runJob(() => mvApi.act(sel, { candidate_id: rec } as ActionSpec, "assisted", get().sampleKind));
    } else {
      // The recommendation is the user's earlier pick or an agent proposal: submit its components.
      const p = plan?.attack_proposals.find((x) => x.action.action_id === rec)?.action;
      if (!p) return;
      const spec: ActionSpec = p.action_type === "shoot" ? { action_type: "shoot" }
        : p.action_type === "pass" && p.target_player_id && !p.action_id.includes("-space-") ? { action_type: "pass", target_player_id: p.target_player_id }
          : { action_type: p.action_type, target_x: p.target_x, target_y: p.target_y };
      await mv.runJob(() => mvApi.act(sel, spec, "assisted", get().sampleKind));
    }
  },

  async autoPlay(steps = 3): Promise<void> {
    const sel = get().selected;
    if (!sel) return;
    await mv.runJob(() => mvApi.autoPlay(sel, steps, get().sampleKind));
  },

  async runJob(start: () => Promise<MultiverseJob>, opts: { selectChild?: boolean } = {}): Promise<void> {
    set({ error: null, live: [] });
    try {
      const job = await start();
      set({ job });
      const done = ["pending", "running"].includes(job.status) ? await trackJob(job.job_id) : job;
      await refreshTree();
      if (done.status !== "completed") {
        set({ error: `Branch ${done.status}: ${done.error ?? ""}` });
        return;
      }
      if (opts.selectChild !== false && done.child_node_id) await mv.select(done.child_node_id, { play: true });
    } catch (e) {
      set({ error: errText(e) });
    } finally {
      set({ job: get().job && ["pending", "running"].includes(get().job!.status) ? get().job : null });
    }
  },

  async cancel(): Promise<void> {
    const j = get().job;
    if (j) await mvApi.cancel(j.parent_node_id);
  },

  setPlay(patch: Partial<Pick<MvState, "playT" | "playing">>): void {
    set(patch);
  },

  async openCompare(a: string, b: string, lang: string): Promise<void> {
    set({ compare: { ...emptyCompare, a, b, open: true, loading: true } });
    try {
      const [data, pathA, pathB] = await Promise.all([mvApi.compare(a, b, lang), mvApi.trajectory(a), mvApi.trajectory(b)]);
      set({ compare: { ...get().compare, data, pathA, pathB, loading: false, t: 0, playing: true } });
    } catch (e) {
      set({ compare: { ...get().compare, loading: false }, error: errText(e) });
    }
  },
  setCompare(patch: Partial<CompareState>): void {
    set({ compare: { ...get().compare, ...patch } });
  },
};

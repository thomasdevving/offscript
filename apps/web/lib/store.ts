"use client";

import type {
  CounterfactualAnalysis,
  DecisionPoint,
  DecisionValueReport,
  FaultInjection,
  Language,
  MatchEvent,
  MatchInfo,
  MatchStateSnapshot,
  MatchStateView,
  Overlay,
  Recap,
  TrackingFrame,
  Trajectory,
  ViewerMode,
} from "@offscript/contracts";
import { create } from "zustand";
import { api, type Health, type ScenarioInfo } from "./api";
import { setLabelLanguage } from "./format";
import { type Follow, FOLLOW_KEY, decodeFollow, encodeFollow, pausesFor } from "./follow";
import { MatchSocket, type ServerMessage } from "./socket";

export type View = "observed" | "snapshot" | "simulated";
export type ConnState = "idle" | "connecting" | "open" | "closed";

export interface ProgressItem {
  event: string;
  agent?: string;
  tool?: string;
  status?: string;
  task?: string;
  attempt?: number;
  from?: string;
  to?: string;
  reason?: string;
  at: number;
}

interface Playback {
  playing: boolean;
  speed: number;
  serverT: number;
  baseT: number;
  lastTickAt: number;
  durationMs: number;
  startClockMs: number;
}

interface WhatIf {
  trajectory: Trajectory | null;
  t: number;
  playing: boolean;
  loading: boolean;
  error: string | null;
}

export interface AppState {
  health: Health | null;
  healthError: string | null;
  scenarios: ScenarioInfo[];
  scenarioId: string | null;
  matchId: string | null;
  match: MatchInfo | null;
  decisions: DecisionPoint[];
  detected: string[];
  feed: MatchEvent[];
  seenEvents: Pick<MatchEvent, "event_type" | "sim_time_ms">[];
  frames: TrackingFrame[];
  playback: Playback;
  score: Record<string, number>;
  possession: string | null;
  stats: MatchStateView | null;
  selectedDecisionId: string | null;
  snapshot: MatchStateSnapshot | null;
  analyses: Record<string, CounterfactualAnalysis>;
  analysisErrors: Record<string, string>;
  progress: Record<string, ProgressItem[]>;
  recovery: CounterfactualAnalysis | null;
  recoveryFault: FaultInjection | null;
  selectedActionId: string | null;
  whatIf: WhatIf;
  view: View;
  overlays: Overlay[];
  mode: ViewerMode;
  lang: Language;
  autoPause: boolean;
  follow: Follow;
  autoAnalyze: boolean;
  conn: ConnState;
  recap: Recap | null;
  recapOpen: boolean;
  recapLoading: boolean;
  /** Decision Value Added report for the current match (verified analyses only). */
  decisionValue: DecisionValueReport | null;
  decisionValueLoading: boolean;
  decisionValueError: string | null;
  inspectorOpen: boolean;
  /** Pitch rendering: flat tactical board or the 3D replay. Shared by the live view and the Multiverse. */
  pitchDim: "2d" | "3d";
  appView: "live" | "multiverse";
}

const initialPlayback: Playback = {
  playing: false, speed: 1, serverT: 0, baseT: 0, lastTickAt: 0, durationMs: 0, startClockMs: 0,
};

const initialWhatIf: WhatIf = { trajectory: null, t: 0, playing: false, loading: false, error: null };

export const useApp = create<AppState>(() => ({
  health: null,
  healthError: null,
  scenarios: [],
  scenarioId: null,
  matchId: null,
  match: null,
  decisions: [],
  detected: [],
  feed: [],
  seenEvents: [],
  frames: [],
  playback: initialPlayback,
  score: {},
  possession: null,
  stats: null,
  selectedDecisionId: null,
  snapshot: null,
  analyses: {},
  analysisErrors: {},
  progress: {},
  recovery: null,
  recoveryFault: null,
  selectedActionId: null,
  whatIf: initialWhatIf,
  view: "observed",
  overlays: [],
  mode: "casual",
  lang: "en",
  autoPause: true,
  follow: null,
  autoAnalyze: true,
  conn: "idle",
  recap: null,
  recapOpen: false,
  recapLoading: false,
  decisionValue: null,
  decisionValueLoading: false,
  decisionValueError: null,
  inspectorOpen: true,
  pitchDim: "2d",
  appView: "live",
}));

const set = useApp.setState;
const get = useApp.getState;
let socket: MatchSocket | null = null;
const polling = new Set<string>();
const MAX_FRAMES = 900;
const LANG_KEY = "offscript.lang";
let dvTimer: ReturnType<typeof setTimeout> | null = null;

/** Re-reads the Decision Value report shortly after analyses finish (only once it has been opened). */
function scheduleDecisionValueRefresh(delayMs = 600): void {
  if (!get().decisionValue || dvTimer) return;
  dvTimer = setTimeout(() => {
    dvTimer = null;
    void actions.loadDecisionValue(true);
  }, delayMs);
}

// ------------------------------------------------------------------ socket messages
function onMessage(msg: ServerMessage): void {
  const s = get();
  switch (msg.type) {
    case "hello":
      set({
        playback: { ...s.playback, durationMs: msg.duration_ms, startClockMs: msg.start_clock_ms, speed: msg.speed,
          playing: msg.playing },
      });
      break;
    case "reset": {
      const frames = msg.frame ? [msg.frame] : [];
      set({
        frames,
        feed: [...(msg.recent_events || [])].reverse(),
        seenEvents: (msg.recent_events || []).map((e: MatchEvent) => ({ event_type: e.event_type, sim_time_ms: e.sim_time_ms })),
        score: msg.score,
        possession: msg.possession_team_id,
        stats: msg.stats,
        detected: msg.detected_decisions || [],
        playback: { ...get().playback, serverT: msg.t_ms, baseT: msg.t_ms, lastTickAt: performance.now(),
          playing: msg.playing, speed: msg.speed },
      });
      break;
    }
    case "status":
      set({ playback: { ...get().playback, playing: msg.playing, speed: msg.speed, serverT: msg.t_ms, baseT: msg.t_ms,
        lastTickAt: performance.now() } });
      break;
    case "tick": {
      const frames = msg.frames.length ? [...s.frames, ...msg.frames].slice(-MAX_FRAMES) : s.frames;
      const newEvents: MatchEvent[] = msg.events.filter((e: MatchEvent) => e.event_type !== "BALL_POSITION_UPDATED");
      set({
        frames,
        feed: newEvents.length ? [...newEvents.reverse(), ...s.feed].slice(0, 80) : s.feed,
        seenEvents: msg.events.length
          ? [...s.seenEvents, ...msg.events.map((e: MatchEvent) => ({ event_type: e.event_type, sim_time_ms: e.sim_time_ms }))]
          : s.seenEvents,
        score: msg.score,
        possession: msg.possession_team_id,
        playback: { ...s.playback, serverT: msg.t_ms, baseT: s.playback.serverT, lastTickAt: performance.now() },
      });
      break;
    }
    case "decision_detected": {
      const dp: DecisionPoint = msg.decision;
      const exists = s.decisions.some((d) => d.decision_point_id === dp.decision_point_id);
      set({
        detected: [...s.detected, dp.decision_point_id],
        decisions: exists ? s.decisions : [...s.decisions, dp].sort((a, b) => a.sim_time_ms - b.sim_time_ms),
      });
      // A fan who follows a team or player is only stopped for their decisions; the rest still gets analysed.
      if (s.autoPause && s.view === "observed" && pausesFor(s.follow, dp, s.match)) {
        socket?.send({ type: "pause" });
        actions.selectDecision(dp.decision_point_id, { fromLive: true });
      }
      break;
    }
    case "analysis_started":
    case "analysis_progress":
    case "analysis_completed": {
      const id: string | undefined = msg.analysis_id;
      const dpId: string | undefined = msg.decision_point_id;
      if (id) {
        const item: ProgressItem = { event: msg.event ?? msg.type, agent: msg.agent, tool: msg.tool, status: msg.status,
          task: msg.task, attempt: msg.attempt, from: msg.from, to: msg.to, reason: msg.reason, at: Date.now() };
        set({ progress: { ...get().progress, [id]: [...(get().progress[id] || []), item].slice(-60) } });
        if (dpId && (msg.type === "analysis_started" || msg.type === "analysis_completed")) {
          const known = get().analyses[dpId];
          if (!known || known.analysis_id === id || msg.type === "analysis_started") {
            void actions.trackAnalysis(id, dpId);
          }
        } else if (msg.event === "agent_completed" || msg.event === "handoff") {
          void actions.refreshAnalysis(id);
        }
      }
      if (msg.type === "analysis_completed") {
        void actions.refreshOverlays();
        scheduleDecisionValueRefresh();
      }
      break;
    }
    case "ended":
      set({ playback: { ...get().playback, playing: false, serverT: msg.t_ms } });
      break;
    case "error":
      console.warn(msg.message);
      break;
  }
}

// ------------------------------------------------------------------ actions
export const actions = {
  async init(): Promise<void> {
    try {
      const [health, scenarios] = await Promise.all([api.health(), api.scenarios()]);
      set({ health, scenarios, healthError: null });
      const fromUrl = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("scenario") : null;
      const first = scenarios.find((x) => x.scenario_id === fromUrl) ?? scenarios[0];
      if (first) await actions.selectScenario(first.scenario_id);
      if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("view") === "multiverse") {
        set({ appView: "multiverse" });
      }
    } catch (e) {
      set({ healthError: (e as Error).message });
      setTimeout(() => void actions.init(), 3000);
    }
  },

  async selectScenario(scenarioId: string): Promise<void> {
    const sc = get().scenarios.find((x) => x.scenario_id === scenarioId);
    if (!sc) return;
    socket?.close();
    set({
      scenarioId, matchId: sc.match_id, match: null, decisions: [], detected: [], feed: [], seenEvents: [], frames: [],
      selectedDecisionId: null, snapshot: null, selectedActionId: null, whatIf: initialWhatIf, view: "observed",
      overlays: [], recovery: null, recoveryFault: null, recap: null, decisionValue: null, decisionValueError: null, playback: initialPlayback, stats: null,
    });
    const [match, decisions, overlays] = await Promise.all([
      api.match(sc.match_id), api.decisions(sc.match_id), api.overlays(sc.match_id),
    ]);
    set({ match, decisions, overlays });
    socket = new MatchSocket(sc.match_id, get().autoAnalyze, onMessage, (conn) => set({ conn }));
    socket.connect();
  },

  control(msg: Record<string, unknown>): void {
    socket?.send(msg);
  },

  togglePlay(): void {
    const s = get();
    if (s.view !== "observed") actions.backToMatch();
    actions.control({ type: s.playback.playing ? "pause" : "play" });
  },

  seek(t: number): void {
    set({ frames: [], view: "observed", selectedActionId: null, whatIf: initialWhatIf });
    actions.control({ type: "seek", t_ms: Math.round(t) });
  },

  setSpeed(v: number): void {
    actions.control({ type: "speed", value: v });
  },

  jumpDecision(dir: 1 | -1): void {
    const s = get();
    const t = s.selectedDecisionId
      ? s.decisions.find((d) => d.decision_point_id === s.selectedDecisionId)?.sim_time_ms ?? s.playback.serverT
      : s.playback.serverT;
    const list = dir > 0 ? s.decisions.filter((d) => d.sim_time_ms > t + 1) : [...s.decisions].reverse().filter((d) => d.sim_time_ms < t - 1);
    const target = list[0];
    if (target) {
      actions.control({ type: "pause" });
      actions.control({ type: "seek", t_ms: (target.outcome_time_ms ?? target.sim_time_ms) + 200 });
      actions.selectDecision(target.decision_point_id);
    }
  },

  async selectDecision(decisionId: string, opts: { fromLive?: boolean } = {}): Promise<void> {
    set({ selectedDecisionId: decisionId, selectedActionId: null, whatIf: initialWhatIf, view: "snapshot",
      snapshot: null, recovery: null, recoveryFault: null });
    if (!opts.fromLive) actions.control({ type: "pause" });
    try {
      const snap = await api.snapshot(decisionId);
      if (get().selectedDecisionId === decisionId) set({ snapshot: snap });
    } catch {
      /* snapshot optional for rendering */
    }
    if (!get().analyses[decisionId] && (get().autoAnalyze || !opts.fromLive)) {
      await actions.analyze(decisionId);
    }
    await actions.ensureLanguage();
  },

  async analyze(decisionId: string, rollouts?: number): Promise<void> {
    try {
      const a = await api.analyze(decisionId, rollouts ? { rollouts } : {});
      set({ analyses: { ...get().analyses, [decisionId]: a } });
      await actions.trackAnalysis(a.analysis_id, decisionId);
    } catch (e) {
      set({ analysisErrors: { ...get().analysisErrors, [decisionId]: (e as Error).message } });
    }
  },

  async runRecovery(fault: FaultInjection): Promise<void> {
    const dp = get().selectedDecisionId;
    if (!dp) return;
    set({ recoveryFault: fault, recovery: null });
    const a = await api.analyze(dp, { fault_injection: [fault] });
    set({ recovery: a });
    await actions.trackAnalysis(a.analysis_id, dp, true);
  },

  async trackAnalysis(analysisId: string, decisionId: string, recovery = false): Promise<void> {
    if (polling.has(analysisId)) return;
    polling.add(analysisId);
    try {
      for (let i = 0; i < 400; i++) {
        const a = await api.analysis(analysisId);
        if (recovery || get().recovery?.analysis_id === analysisId) set({ recovery: a });
        else {
          const cur = get().analyses[decisionId];
          if (!cur || cur.analysis_id === analysisId || cur.status !== "verified") {
            set({ analyses: { ...get().analyses, [decisionId]: a } });
          }
        }
        if (!["pending", "running"].includes(a.status)) break;
        await new Promise((r) => setTimeout(r, 450));
      }
    } finally {
      polling.delete(analysisId);
    }
    await actions.ensureLanguage();
    await actions.refreshOverlays();
  },

  async refreshAnalysis(analysisId: string): Promise<void> {
    const s = get();
    const entry = Object.entries(s.analyses).find(([, a]) => a.analysis_id === analysisId);
    if (!entry && s.recovery?.analysis_id !== analysisId) return;
    const a = await api.analysis(analysisId);
    if (s.recovery?.analysis_id === analysisId) set({ recovery: a });
    else if (entry) set({ analyses: { ...get().analyses, [entry[0]]: a } });
  },

  async refreshOverlays(): Promise<void> {
    const id = get().matchId;
    if (id) set({ overlays: await api.overlays(id) });
  },

  async selectAction(actionId: string, rollout?: number): Promise<void> {
    const s = get();
    const a = s.recovery ?? (s.selectedDecisionId ? s.analyses[s.selectedDecisionId] : undefined);
    if (!a) return;
    set({ selectedActionId: actionId, whatIf: { ...initialWhatIf, loading: true }, view: "simulated" });
    actions.control({ type: "pause" });
    try {
      const traj = await api.trajectory(a.analysis_id, actionId, rollout);
      set({ whatIf: { trajectory: traj, t: 0, playing: true, loading: false, error: null } });
    } catch (e) {
      set({ whatIf: { ...initialWhatIf, error: (e as Error).message } });
    }
  },

  setWhatIf(patch: Partial<WhatIf>): void {
    set({ whatIf: { ...get().whatIf, ...patch } });
  },

  showSnapshot(): void {
    set({ view: "snapshot", selectedActionId: null, whatIf: initialWhatIf });
  },

  backToMatch(): void {
    set({ view: "observed", selectedActionId: null, whatIf: initialWhatIf });
  },

  setMode(mode: ViewerMode): void {
    set({ mode });
  },
  setLang(lang: Language): void {
    setLabelLanguage(lang);
    set({ lang, recap: null });
    try {
      if (lang === "en") localStorage.removeItem(LANG_KEY);
      else localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* storage unavailable */
    }
    void actions.ensureLanguage();
  },
  /** Restores the viewer's language (client only, after hydration); ?lang=es in the URL wins. English by default. */
  restoreLang(): void {
    try {
      const v = new URLSearchParams(window.location.search).get("lang") ?? localStorage.getItem(LANG_KEY);
      if (v && ["en", "nl", "es", "fr", "de"].includes(v)) {
        setLabelLanguage(v as Language);
        set({ lang: v as Language });
      }
    } catch {
      /* storage unavailable */
    }
  },
  /**
   * The agents write every analysis in English and Dutch. For Spanish, French and German the API adds
   * verified narratives to the finished analysis on request; until they arrive the English text is shown.
   */
  async ensureLanguage(): Promise<void> {
    const s = get();
    if (s.lang === "en" || s.lang === "nl") return;
    const lang = s.lang;
    const sel = s.selectedDecisionId ? s.analyses[s.selectedDecisionId] : null;
    for (const a of [sel, s.recovery]) {
      if (!a || a.status !== "verified" || a.narratives.some((n) => n.language === lang)) continue;
      try {
        const b = await api.addNarratives(a.analysis_id, lang);
        const now = get();
        if (now.recovery?.analysis_id === b.analysis_id) set({ recovery: b });
        const entry = Object.entries(now.analyses).find(([, x]) => x.analysis_id === b.analysis_id);
        if (entry) set({ analyses: { ...now.analyses, [entry[0]]: b } });
      } catch {
        /* the English narratives stay visible */
      }
    }
  },
  setAutoPause(v: boolean): void {
    set({ autoPause: v });
  },
  setAutoAnalyze(v: boolean): void {
    set({ autoAnalyze: v });
    actions.control({ type: "auto_analyze", value: v });
  },
  setView(v: "live" | "multiverse"): void {
    if (v === "multiverse") actions.control({ type: "pause" });
    set({ appView: v });
    try {
      const url = new URL(window.location.href);
      if (v === "multiverse") url.searchParams.set("view", "multiverse");
      else url.searchParams.delete("view");
      window.history.replaceState(null, "", url.toString());
    } catch {
      /* non-browser */
    }
  },

  setPitchDim(v: "2d" | "3d"): void {
    set({ pitchDim: v });
    try {
      localStorage.setItem("offscript.pitchDim", v);
    } catch {
      /* storage unavailable */
    }
  },
  /** Restores the viewer's last 2D/3D choice (client only, after hydration). */
  restorePitchDim(): void {
    try {
      // ?dim=3d in the URL wins (handy for demo links), then the remembered choice.
      const v = new URLSearchParams(window.location.search).get("dim") ?? localStorage.getItem("offscript.pitchDim");
      if (v === "2d" || v === "3d") set({ pitchDim: v });
    } catch {
      /* storage unavailable */
    }
  },

  setFollow(f: Follow): void {
    set({ follow: f });
    try {
      if (f) localStorage.setItem(FOLLOW_KEY, encodeFollow(f));
      else localStorage.removeItem(FOLLOW_KEY);
    } catch {
      /* storage unavailable */
    }
  },
  /** Restores the fan's follow choice (client only, after hydration); ?follow=team:HCF in the URL wins. */
  restoreFollow(): void {
    try {
      const v = new URLSearchParams(window.location.search).get("follow") ?? localStorage.getItem(FOLLOW_KEY);
      set({ follow: decodeFollow(v) });
    } catch {
      /* storage unavailable */
    }
  },

  toggleInspector(): void {
    set({ inspectorOpen: !get().inspectorOpen });
  },

  async analyseEvent(eventId: string): Promise<void> {
    const id = get().matchId;
    if (!id) return;
    const dp = await api.manualDecision(id, eventId);
    if (!get().decisions.some((d) => d.decision_point_id === dp.decision_point_id)) {
      set({ decisions: [...get().decisions, dp].sort((a, b) => a.sim_time_ms - b.sim_time_ms) });
    }
    await actions.selectDecision(dp.decision_point_id);
  },

  async openRecap(): Promise<void> {
    const id = get().matchId;
    if (!id) return;
    set({ recapOpen: true, recapLoading: true });
    try {
      set({ recap: await api.recap(id, get().lang) });
    } finally {
      set({ recapLoading: false });
    }
  },
  closeRecap(): void {
    set({ recapOpen: false });
  },

  async loadDecisionValue(quiet = false): Promise<void> {
    const id = get().matchId;
    if (!id) return;
    if (!quiet) set({ decisionValueLoading: true, decisionValueError: null });
    try {
      const r = await api.decisionValue(id);
      if (get().matchId === id) set({ decisionValue: r, decisionValueError: null });
      if (r.decisions_pending > 0) scheduleDecisionValueRefresh(1500);
    } catch (e) {
      if (get().matchId === id) set({ decisionValueError: (e as Error).message });
    } finally {
      if (!quiet) set({ decisionValueLoading: false });
    }
  },

  /** Analyse every detected decision that has no analysis yet (cache first), then follow progress. */
  async analyseAllDecisions(): Promise<void> {
    const id = get().matchId;
    if (!id) return;
    set({ decisionValueLoading: true, decisionValueError: null });
    try {
      const r = await api.analyseAllDecisions(id);
      if (get().matchId === id) set({ decisionValue: r });
      if (r.decisions_pending > 0) scheduleDecisionValueRefresh(1500);
    } catch (e) {
      set({ decisionValueError: (e as Error).message });
    } finally {
      set({ decisionValueLoading: false });
    }
  },
};

export function selectedAnalysis(s: AppState): CounterfactualAnalysis | null {
  if (s.recovery) return s.recovery;
  return s.selectedDecisionId ? s.analyses[s.selectedDecisionId] ?? null : null;
}

export function selectedDecision(s: AppState): DecisionPoint | null {
  return s.decisions.find((d) => d.decision_point_id === s.selectedDecisionId) ?? null;
}

"use client";

import type { CounterfactualAnalysis, MatchStateSnapshot, Overlay } from "@offscript/contracts";
import { useEffect, useMemo, useRef, useState } from "react";
import { ballPath, interpolate, type RenderFrame } from "@/lib/frames";
import { clock, cleanLabel, outcomeLabel, pct } from "@/lib/format";
import { t, tr } from "@/lib/i18n";
import { activeOverlay, localizeOverlays } from "@/lib/overlayEngine";
import { actions, selectedAnalysis, selectedDecision, useApp } from "@/lib/store";
import { ScoreBug } from "./MatchIntel";
import OverlayCard from "./OverlayCard";
import { type Arrow, type Ring } from "./Pitch";
import PitchView, { DimToggle } from "./PitchView";

function useRaf(cb: (dt: number) => void, active: boolean) {
  const ref = useRef(cb);
  ref.current = cb;
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      ref.current((now - last) / 1000);
      last = now;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);
}

function snapshotFrame(s: MatchStateSnapshot): RenderFrame {
  const players: Record<string, [number, number]> = {};
  for (const p of s.players) players[p.player_id] = [p.x, p.y];
  return { t_ms: s.sim_time_ms, ball: [s.ball.x, s.ball.y, 0], players, possessor_id: s.ball.possessor_id ?? null };
}

function goalTarget(s: MatchStateSnapshot): [number, number] {
  const dir = s.attack_direction[s.possession_team_id];
  return dir === 1 ? [105, 34] : [0, 34];
}

function candidateArrows(a: CounterfactualAnalysis | null, s: MatchStateSnapshot, selected: string | null): Arrow[] {
  if (!a || !a.candidates.length) return [];
  const carrier = s.players.find((p) => p.player_id === s.ball.possessor_id);
  if (!carrier) return [];
  const res = new Map((a.simulation?.results ?? []).map((r) => [r.action_id, r]));
  const ranked = [...a.candidates].sort((x, y) => (res.get(y.action_id)?.p_goal.value ?? 0) - (res.get(x.action_id)?.p_goal.value ?? 0));
  return a.candidates.map((c) => {
    const to: [number, number] = c.action_type === "shoot" ? goalTarget(s) : [c.target_x ?? carrier.x, c.target_y ?? carrier.y];
    const r = res.get(c.action_id);
    const label = `${cleanLabel(c.label)}${r ? ` ${pct(r.p_goal.value)}` : ""}`;
    return {
      id: c.action_id,
      from: [carrier.x, carrier.y],
      to,
      kind: c.action_id === selected ? "selected" : c.is_actual ? "actual" : "alternative",
      label: c.is_actual ? `${label} (actual)` : label,
      rank: r ? ranked.findIndex((x) => x.action_id === c.action_id) + 1 : undefined,
    } satisfies Arrow;
  });
}

/** End-of-continuation result: what was chosen, how it ended and how likely that kind of outcome is. */
export function OutcomeCard({ action, outcome, lines }: { action: string; outcome: string; lines: string[] }) {
  return (
    <div className="pointer-events-none absolute bottom-2 left-1/2 z-10 w-max max-w-[92%] -translate-x-1/2 animate-rise bg-slate-950/80 px-3 py-1.5 text-center shadow-2xl ring-1 ring-leaf-400/40 backdrop-blur"
      data-testid="outcome-card">
      <div className="text-[13px] font-bold text-white">
        {action} → <span className="text-amber-300">{outcomeLabel(outcome).toLowerCase()}</span>
      </div>
      {lines.filter(Boolean).map((l) => <div key={l} className="font-mono text-[10.5px] leading-snug text-leaf-200">{l}</div>)}
    </div>
  );
}

export default function PitchStage() {
  const s = useApp();
  const L = t(s.lang);
  const [renderT, setRenderT] = useState(0);
  const match = s.match;
  const analysis = selectedAnalysis(s);
  const decision = selectedDecision(s);

  // Observed playback clock: interpolate between the last two server ticks.
  useRaf(() => {
    const pb = useApp.getState().playback;
    const now = performance.now();
    const target = pb.playing ? Math.min(pb.serverT, pb.baseT + (now - pb.lastTickAt) * pb.speed) : pb.serverT;
    setRenderT(target);
  }, s.view === "observed");

  // What-if playback clock (client-side; the trajectory is pre-computed by the simulator).
  useRaf((dt) => {
    const w = useApp.getState().whatIf;
    if (!w.trajectory || !w.playing) return;
    const end = w.trajectory.frames[w.trajectory.frames.length - 1]?.t_ms ?? 0;
    const nt = Math.min(end, w.t + dt * 1000);
    actions.setWhatIf({ t: nt, playing: nt < end });
  }, s.view === "simulated" && s.whatIf.playing);

  const frame: RenderFrame | null = useMemo(() => {
    if (s.view === "simulated" && s.whatIf.trajectory) return interpolate(s.whatIf.trajectory.frames, s.whatIf.t);
    if (s.view === "snapshot" && s.snapshot) return snapshotFrame(s.snapshot);
    return interpolate(s.frames, renderT);
  }, [s.view, s.whatIf, s.snapshot, s.frames, renderT]);

  const arrows = s.view === "snapshot" && s.snapshot ? candidateArrows(analysis, s.snapshot, s.selectedActionId) : [];
  const traj = s.whatIf.trajectory;
  const trail = s.view === "simulated" && traj ? ballPath(traj.frames, 0, s.whatIf.t) : undefined;
  const ghost = s.view === "simulated" && traj ? ballPath(traj.frames) : undefined;

  let rings: Ring[] | undefined;
  let lanes: { from: [number, number]; to: [number, number]; quality: number }[] | undefined;
  if (s.mode === "analyst" && s.view === "snapshot" && s.snapshot) {
    const carrier = s.snapshot.players.find((p) => p.player_id === s.snapshot!.ball.possessor_id);
    if (carrier) {
      rings = [{ x: carrier.x, y: carrier.y, r: 5 }];
      lanes = (analysis?.candidates ?? [])
        .filter((c) => c.action_type === "pass" && c.target_x != null)
        .map((c) => ({ from: [carrier.x, carrier.y], to: [c.target_x!, c.target_y!],
          quality: c.features?.completion_estimate ?? 0.5 }));
    }
  }

  let overlay: Overlay | null = null;
  const overlays = localizeOverlays(s.overlays, Object.values(s.analyses), s.lang);
  if (s.view === "observed") overlay = activeOverlay(overlays, renderT, s.mode, s.lang, s.seenEvents);
  else if (analysis && s.mode === "broadcaster" && !s.recovery)
    overlay = overlays.find((o) => o.analysis_id === analysis.analysis_id && o.viewer_mode === "broadcaster" && o.language === s.lang) ?? null;

  if (!match) {
    return <div className="flex aspect-[111/74] w-full animate-pulse items-center justify-center rounded-xl bg-white/[0.03] text-sm text-slate-500">Loading match…</div>;
  }

  const banner =
    s.view === "simulated" ? { text: L.simulated, cls: "bg-leaf-600/90 text-white shadow-lg shadow-leaf-900/50" }
      : s.view === "snapshot" ? { text: `${L.frozen} · ${decision ? clock(decision.match_clock_ms) : ""}`, cls: "bg-sage-600/90 text-white shadow-lg shadow-sage-900/50" }
        : { text: L.observed, cls: "bg-slate-950/80 text-slate-300 ring-1 ring-white/10" };

  const simRes = traj ? analysis?.simulation?.results.find((r) => r.action_id === traj.action_id) : undefined;
  const atEnd = !!traj && s.whatIf.t >= (traj.frames[traj.frames.length - 1]?.t_ms ?? 0) - 1;
  const traceLabel = traj ? `${cleanLabel(analysis?.candidates.find((c) => c.action_id === traj.action_id)?.label ?? "")} · ${outcomeLabel(traj.outcome).toLowerCase()}` : "";

  return (
    <div className="relative">
      <div className="absolute left-3 top-3 z-10 flex flex-col items-start gap-1.5"><ScoreBug /><DimToggle /></div>
      <div className="absolute bottom-3 right-3 z-10 flex max-w-[60%] flex-col items-end gap-1.5 sm:bottom-auto sm:top-3">
        <span className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider backdrop-blur ${banner.cls}`} data-testid="view-banner">
          <span className={`h-1.5 w-1.5 rounded-full ${s.view === "observed" ? "bg-emerald-400" : "bg-white"} ${s.view !== "snapshot" ? "animate-pulse" : ""}`} />
          {banner.text}
        </span>
        {s.view === "simulated" && <span className="rounded-lg bg-slate-950/80 px-2 py-1 text-right text-[11px] text-leaf-200 backdrop-blur">{L.oneSample}</span>}
      </div>
      {s.view === "simulated" && traj && !atEnd && (
        <div className="absolute bottom-3 left-3 z-10 rounded-lg bg-slate-950/80 px-2 py-1 font-mono text-[11px] text-leaf-200 backdrop-blur" data-testid="trace-label">{traceLabel}</div>
      )}
      {s.view === "simulated" && traj && atEnd && (
        <OutcomeCard
          action={cleanLabel(analysis?.candidates.find((c) => c.action_id === traj.action_id)?.label ?? "")}
          outcome={traj.outcome}
          lines={[
            simRes ? `P(goal) ${pct(simRes.p_goal.value, s.lang)} · ${simRes.n_rollouts} ${L.simulations}` : "",
            tr(s.lang, { en: "one simulated continuation", nl: "één gesimuleerd verloop", es: "una continuación simulada", fr: "une suite simulée", de: "ein simulierter Verlauf" }),
          ]}
        />
      )}
      <PitchView
        match={match}
        frame={frame}
        highlightId={s.view !== "observed" ? decision?.actor_id : null}
        arrows={arrows}
        trail={trail}
        ghostTrail={ghost}
        rings={rings}
        lanes={lanes}
        tint={s.view}
        onArrowClick={(id) => void actions.selectAction(id)}
        ariaLabel={`${match.home.name} versus ${match.away.name} pitch, ${banner.text}`}
      />
      {overlay && <OverlayCard overlay={overlay} />}
    </div>
  );
}

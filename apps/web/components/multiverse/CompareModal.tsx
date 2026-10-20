"use client";

import type { TrackingFrame } from "@parallel/contracts";
import { useEffect, useRef } from "react";
import { interpolate } from "@/lib/frames";
import { pct } from "@/lib/format";
import { mv, useMv } from "@/lib/mvStore";
import { useApp } from "@/lib/store";
import Pitch from "../Pitch";

export default function CompareModal() {
  const c = useMv((s) => s.compare);
  const match = useApp((s) => s.match);
  const lang = useApp((s) => s.lang);
  const last = useRef(0);
  const duration = Math.max(c.pathA?.duration_ms ?? 0, c.pathB?.duration_ms ?? 0);
  useEffect(() => {
    if (!c.playing) return;
    let raf = 0;
    last.current = performance.now();
    const loop = (now: number) => {
      const s = useMv.getState().compare;
      const nt = Math.min(duration, s.t + (now - last.current) * s.speed);
      last.current = now;
      mv.setCompare({ t: nt, playing: nt < duration });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [c.playing, duration]);
  if (!c.open) return null;
  const d = c.data;
  const panel = (which: "a" | "b") => {
    const path = which === "a" ? c.pathA : c.pathB;
    const m = which === "a" ? d?.metrics_a : d?.metrics_b;
    const steps = which === "a" ? d?.steps_a : d?.steps_b;
    const frame = path ? interpolate(path.frames as unknown as TrackingFrame[], Math.min(c.t, path.duration_ms)) : null;
    const observed = m?.kind === "observed";
    return (
      <div className="min-w-0 space-y-2">
        <div className={`rounded px-2 py-1 text-xs font-bold uppercase tracking-wider ${observed ? "bg-slate-200 text-slate-900" : "bg-blue-600 text-white"}`}>
          {which.toUpperCase()} · {observed ? "Canonical synthetic timeline" : "Simulated branch"}
        </div>
        {match && <Pitch match={match} frame={frame} tint={observed ? "observed" : "simulated"} ariaLabel={`Branch ${which}`} />}
        <ol className="text-xs text-slate-300">
          {steps?.map((s) => (
            <li key={s.node_id}>
              {s.action_label} <span className="text-slate-500">({s.action_source}{s.strategy_label ? ` vs ${s.strategy_label}` : ""})</span> → {(s.terminal_outcome ?? s.first_outcome ?? "").replace(/_/g, " ")}
              {s.p_goal_vs_counter != null && <span className="font-mono text-blue-300"> · {pct(s.p_goal_vs_counter, lang)}</span>}
            </li>
          ))}
        </ol>
        {m && (
          <div className="grid grid-cols-3 gap-1 text-center text-[11px]">
            <div className="rounded bg-slate-900 p-1"><div className="font-mono text-white">{String(m.final_outcome).replace(/_/g, " ")}</div><div className="text-slate-500">outcome</div></div>
            <div className="rounded bg-slate-900 p-1"><div className="font-mono text-white">{String(m.elapsed_s)} s</div><div className="text-slate-500">elapsed</div></div>
            <div className="rounded bg-slate-900 p-1"><div className="font-mono text-white">{String(m.shots)} / {String(m.turnovers)}</div><div className="text-slate-500">shots / turnovers</div></div>
          </div>
        )}
      </div>
    );
  };
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4" role="dialog" aria-modal="true" aria-label="Branch comparison"
      onKeyDown={(e) => e.key === "Escape" && mv.setCompare({ open: false, playing: false })} data-testid="compare-modal">
      <div className="w-full max-w-6xl space-y-3 rounded-2xl border border-line bg-panel p-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-extrabold text-white">Branch comparison</h2>
          <span className="text-xs text-slate-400">both start from the same frozen decision state</span>
          <button type="button" onClick={() => mv.setCompare({ open: false, playing: false })} className="ml-auto rounded bg-slate-800 px-3 py-1 text-xs">Close</button>
        </div>
        {c.loading && <p className="text-sm text-slate-400">Loading…</p>}
        <div className="grid gap-3 md:grid-cols-2">{panel("a")}{panel("b")}</div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => mv.setCompare({ playing: !c.playing, t: c.t >= duration ? 0 : c.t })} className="h-8 w-8 rounded bg-blue-600 font-bold text-white" aria-label="Play both">{c.playing ? "❚❚" : "▶"}</button>
          <button type="button" onClick={() => mv.setCompare({ t: 0, playing: true })} className="h-8 w-8 rounded bg-slate-800" aria-label="Restart both">↺</button>
          {[0.5, 1, 2].map((v) => (
            <button key={v} type="button" onClick={() => mv.setCompare({ speed: v })} className={`h-7 rounded px-2 text-xs ${c.speed === v ? "bg-slate-200 text-slate-900" : "bg-slate-800"}`}>{v}×</button>
          ))}
          <input type="range" min={0} max={duration} step={50} value={c.t} onChange={(e) => mv.setCompare({ t: Number(e.target.value), playing: false })} className="timeline flex-1" aria-label="Synchronised time" />
          <span className="font-mono text-xs text-slate-300">+{(c.t / 1000).toFixed(1)}s</span>
        </div>
        {d && <p className="rounded-lg bg-slate-950/60 p-3 text-sm text-slate-200" data-testid="compare-explanation">{d.explanation}</p>}
      </div>
    </div>
  );
}

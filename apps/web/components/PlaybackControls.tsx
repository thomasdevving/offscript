"use client";

import { clock, cleanLabel, pct } from "@/lib/format";
import { t } from "@/lib/i18n";
import { actions, selectedAnalysis, useApp } from "@/lib/store";

const SPEEDS = [0.5, 1, 2, 4];

function Btn(props: { onClick: () => void; label: string; children: React.ReactNode; primary?: boolean; testId?: string }) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      aria-label={props.label}
      title={props.label}
      data-testid={props.testId}
      className={`inline-flex h-9 min-w-9 items-center justify-center rounded-sm px-2 text-sm font-semibold transition ${
        props.primary ? "w-11 h-11 bg-white text-slate-950 shadow-lg shadow-leaf-900/40 hover:bg-leaf-100" : "text-slate-300 hover:bg-white/10 hover:text-white"
      }`}
    >
      {props.children}
    </button>
  );
}

export function MatchTimeline() {
  const s = useApp();
  const L = t(s.lang);
  const dur = Math.max(1, s.playback.durationMs);
  const goals = s.seenEvents.filter((e) => e.event_type === "GOAL");
  return (
    <div className="relative h-6 min-w-[180px] flex-1 basis-full sm:basis-auto" aria-label="Match timeline">
      <input
        type="range"
        min={0}
        max={dur}
        step={100}
        value={Math.min(dur, s.playback.serverT)}
        onChange={(e) => actions.seek(Number(e.target.value))}
        aria-label="Seek"
        className="timeline absolute inset-x-0 top-[11px] w-full"
      />
      {s.decisions.map((d) => {
        const left = (d.sim_time_ms / dur) * 100;
        const sel = d.decision_point_id === s.selectedDecisionId;
        const seen = s.detected.includes(d.decision_point_id);
        return (
          <button
            key={d.decision_point_id}
            type="button"
            onClick={() => {
              actions.control({ type: "seek", t_ms: (d.outcome_time_ms ?? d.sim_time_ms) + 200 });
              void actions.selectDecision(d.decision_point_id);
            }}
            className={`absolute top-[6px] h-3 w-3 -translate-x-1/2 rotate-45 ring-2 ring-ink transition ${sel ? "scale-[1.35] bg-white shadow-[0_0_10px] shadow-sage-400" : seen ? "bg-sage-400" : "bg-slate-600 hover:bg-slate-400"}`}
            style={{ left: `${left}%` }}
            aria-label={`${L.decisions}: ${d.actor_name} ${clock(d.match_clock_ms)}`}
            title={`${clock(d.match_clock_ms)} ${d.actor_name}`}
          />
        );
      })}
      {goals.map((g, i) => (
        <span key={i} className="absolute top-[5px] h-3.5 w-[3px] -translate-x-1/2 bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400" style={{ left: `${(g.sim_time_ms / dur) * 100}%` }} />
      ))}
    </div>
  );
}

export default function PlaybackControls() {
  const s = useApp();
  const L = t(s.lang);
  const clockMs = s.playback.startClockMs + s.playback.serverT;
  return (
    <div className="glass flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2">
      <div className="flex items-center gap-1">
        <Btn onClick={() => actions.control({ type: "restart", play: true })} label={L.restart}>↺</Btn>
        <Btn onClick={() => actions.jumpDecision(-1)} label={L.prevDecision} testId="prev-decision">⏮</Btn>
        <Btn onClick={() => actions.togglePlay()} label={s.playback.playing ? L.pause : L.play} primary testId="play-toggle">
          {s.playback.playing ? "❚❚" : "▶"}
        </Btn>
        <Btn onClick={() => actions.jumpDecision(1)} label={L.nextDecision} testId="next-decision">⏭</Btn>
      </div>
      <span className="num w-12 font-mono text-sm font-semibold text-white" aria-live="off">{clock(clockMs)}</span>
      <MatchTimeline />
      <div className="flex items-center gap-0.5 rounded-lg bg-white/[0.04] p-0.5" role="group" aria-label={L.speed}>
        {SPEEDS.map((v) => (
          <button key={v} type="button" onClick={() => actions.setSpeed(v)} aria-pressed={s.playback.speed === v} className="tab px-2 py-0.5 text-[11px]">
            {v}×
          </button>
        ))}
      </div>
      {/* Playback preferences are rarely changed: tucked behind a settings toggle. */}
      <details className="group relative text-[11px] text-slate-400">
        <summary className="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-sm text-sm hover:bg-white/10 hover:text-white [&::-webkit-details-marker]:hidden"
          aria-label={s.lang === "en" ? "Playback settings" : "Afspeelinstellingen"} title={s.lang === "en" ? "Playback settings" : "Afspeelinstellingen"}>⚙</summary>
        <div className="glass absolute bottom-10 right-0 z-20 flex w-max flex-col gap-2 bg-panel/95 p-3">
        <label className="flex cursor-pointer items-center gap-1.5 hover:text-slate-200">
          <input type="checkbox" checked={s.autoPause} onChange={(e) => actions.setAutoPause(e.target.checked)} className="accent-sage-500" />
          {L.autoPause}
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 hover:text-slate-200">
          <input type="checkbox" checked={s.autoAnalyze} onChange={(e) => actions.setAutoAnalyze(e.target.checked)} className="accent-sage-500" />
          {L.autoAnalyze}
        </label>
        </div>
      </details>
    </div>
  );
}

export function WhatIfControls() {
  const s = useApp();
  const L = t(s.lang);
  const traj = s.whatIf.trajectory;
  const a = selectedAnalysis(s);
  if (s.view === "observed") return null;
  if (s.view === "snapshot") {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-gradient-to-r from-sage-600/20 to-transparent px-4 py-2.5 text-sm text-sage-100 ring-1 ring-sage-400/25">
        <span>{s.lang === "en" ? "Choose an option on the pitch or in the panel to watch a simulated continuation." :
          "Kies een optie op het veld of in het paneel om een gesimuleerd vervolg te bekijken."}</span>
        <button type="button" onClick={() => actions.backToMatch()} className="btn ml-auto">
          {L.returnToMatch}
        </button>
      </div>
    );
  }
  const end = traj?.frames[traj.frames.length - 1]?.t_ms ?? 0;
  const res = a?.simulation?.results.find((r) => r.action_id === s.selectedActionId);
  const examples = res ? Object.entries(res.example_rollouts ?? {}) : [];
  return (
    <div className="rounded-2xl bg-gradient-to-r from-leaf-600/20 to-transparent px-4 py-2.5 ring-1 ring-leaf-400/25" data-testid="whatif-controls">
      {s.whatIf.loading && <div className="text-sm text-leaf-200">{s.lang === "en" ? "Re-running rollout from its seed..." : "Simulatie opnieuw afspelen vanaf seed..."}</div>}
      {s.whatIf.error && <div className="text-sm text-red-300">{s.whatIf.error}</div>}
      {traj && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Btn onClick={() => actions.setWhatIf({ playing: !s.whatIf.playing, t: s.whatIf.t >= end ? 0 : s.whatIf.t })}
              label={s.whatIf.playing ? L.pause : L.play} primary>
              {s.whatIf.playing ? "❚❚" : "▶"}
            </Btn>
            <Btn onClick={() => actions.setWhatIf({ t: 0, playing: true })} label={L.replay}>↺</Btn>
            <span className="font-mono text-xs text-leaf-100">+{(s.whatIf.t / 1000).toFixed(1)}s / {(end / 1000).toFixed(1)}s</span>
            <span className="text-xs text-leaf-200">{cleanLabel(a?.candidates.find((c) => c.action_id === traj.action_id)?.label ?? "")}
              {res && ` · P(goal) ${pct(res.p_goal.value, s.lang)}`}</span>
            <div className="ml-auto flex items-center gap-1">
              {examples.map(([outcome, idx]) => (
                <button key={outcome} type="button" onClick={() => void actions.selectAction(traj.action_id, idx)}
                  className={`rounded-lg px-2 py-1 text-[11px] font-semibold ${traj.rollout_index === idx ? "bg-leaf-500 text-white" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}
                  title={`${L.sampleOutcome}: ${outcome}`}>
                  {outcome}
                </button>
              ))}
              <button type="button" onClick={() => actions.showSnapshot()} className="btn py-1">
                {L.frozen}
              </button>
              <button type="button" onClick={() => actions.backToMatch()} className="btn bg-white py-1 text-slate-900 hover:bg-leaf-100" data-testid="back-to-match">
                {L.returnToMatch}
              </button>
            </div>
          </div>
          <input type="range" min={0} max={end} step={50} value={s.whatIf.t} aria-label="Scrub simulated continuation"
            onChange={(e) => actions.setWhatIf({ t: Number(e.target.value), playing: false })} className="timeline mt-2 w-full" />
          {s.mode === "analyst" && <p className="mt-1 truncate text-[10px] text-leaf-200/60" title={traj.selection_rule}>{traj.selection_rule}</p>}
        </>
      )}
    </div>
  );
}

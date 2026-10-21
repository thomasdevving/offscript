"use client";

import type { MatchEvent } from "@offscript/contracts";
import { useState } from "react";
import { clock, pct } from "@/lib/format";
import { eventLabel, t, triggerLabel } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

const ACTIONS = new Set(["PASS_ATTEMPTED", "SHOT_ATTEMPTED", "DRIBBLE_ATTEMPTED"]);

/** Broadcast-style score bug that sits on the pitch. */
export function ScoreBug() {
  const s = useApp();
  const m = s.match;
  if (!m) return null;
  const clockMs = s.playback.startClockMs + s.playback.serverT;
  const sh = s.score[m.home.team_id] ?? m.initial_score[m.home.team_id];
  const sa = s.score[m.away.team_id] ?? m.initial_score[m.away.team_id];
  const team = (short: string, color: string, poss: boolean) => (
    <span className="flex items-center gap-1.5 px-2.5">
      <span className="h-3.5 w-1 rounded-full" style={{ background: color }} />
      <span className="text-[11px] font-extrabold tracking-wide text-white sm:text-[13px]">{short}</span>
      <span className={`h-1 w-1 rounded-full ${poss ? "bg-white" : "bg-transparent"}`} aria-hidden />
    </span>
  );
  return (
    <div className="flex items-stretch overflow-hidden rounded-lg bg-slate-950/85 text-white shadow-xl ring-1 ring-white/10 backdrop-blur"
      aria-label="Scoreboard" role="group">
      {team(m.home.short_name, m.home.color_primary, s.possession === m.home.team_id)}
      <span className="num flex items-center bg-white px-2.5 font-mono text-[15px] font-black text-slate-950" data-testid="score">{sh} - {sa}</span>
      {team(m.away.short_name, m.away.color_primary, s.possession === m.away.team_id)}
      <span className="num flex items-center bg-white/10 px-2.5 font-mono text-[13px] font-semibold text-leaf-200">{clock(clockMs)}</span>
    </div>
  );
}

/** Detected decisions as a horizontal strip of moment cards. */
export function Moments() {
  const s = useApp();
  const L = t(s.lang);
  return (
    <section aria-label={L.decisions} className="min-w-0">
      <div className="mb-2 flex items-center gap-2 px-1">
        <h2 className="eyebrow">{L.moments}</h2>
        <span className="text-[11px] text-slate-600">{s.decisions.length}</span>
      </div>
      <ul className="flex gap-2 overflow-x-auto pb-1" data-testid="decision-list">
        {s.decisions.map((d) => {
          const a = s.analyses[d.decision_point_id];
          const sel = d.decision_point_id === s.selectedDecisionId;
          const status = a?.status;
          const detected = s.detected.includes(d.decision_point_id);
          const dot = status === "verified" ? "bg-emerald-400" : status === "running" || status === "pending" ? "bg-amber-400 animate-pulse"
            : status ? "bg-slate-400" : detected ? "bg-sage-400" : "bg-slate-600";
          return (
            <li key={d.decision_point_id} className="shrink-0">
              <button type="button" onClick={() => {
                actions.control({ type: "seek", t_ms: (d.outcome_time_ms ?? d.sim_time_ms) + 200 });
                void actions.selectDecision(d.decision_point_id);
              }}
                className={`group w-56 rounded-xl px-3 py-2 text-left transition ${sel ? "bg-sage-500/15 ring-1 ring-sage-400/50" : "bg-white/[0.03] hover:bg-white/[0.06]"}`}>
                <div className="flex items-center gap-2 text-xs">
                  <span className="num font-mono text-slate-400">{clock(d.match_clock_ms)}</span>
                  <span className="truncate font-semibold text-white">{d.actor_name}</span>
                  {d.source === "manual" && <span className="rounded bg-white/10 px-1 text-[9px] uppercase text-slate-300">manual</span>}
                  <span className="ml-auto flex items-center gap-1 text-[10px] text-slate-400">
                    <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
                    {status ?? (detected ? "detected" : `score ${d.candidate_score.toFixed(2)}`)}
                  </span>
                </div>
                <div className="mt-1 truncate text-[11px] text-slate-400">
                  {d.actual_action.label.replace(" (actual)", "")} → <span className="text-amber-200/90">{eventLabel(d.actual_outcome, s.lang)}</span>
                </div>
                {s.mode === "analyst" && <div className="mt-0.5 truncate text-[10px] text-slate-500">{triggerLabel(d.triggers[0] ?? "", s.lang)}</div>}
              </button>
            </li>
          );
        })}
        {!s.decisions.length && <li className="px-1 text-xs text-slate-500">-</li>}
      </ul>
    </section>
  );
}

function EventFeed() {
  const s = useApp();
  const L = t(s.lang);
  const names = new Map((s.match?.players ?? []).map((p) => [p.player_id, p.short_name]));
  const feed = s.feed.filter((e) => e.event_type !== "PLAYER_POSITION_UPDATED" && e.event_type !== "BALL_POSITION_UPDATED");
  return (
    <ol className={`${s.mode === "analyst" ? "max-h-56" : "max-h-40"} overflow-y-auto text-xs`} aria-live="polite" aria-label={L.events} data-testid="event-feed">
      {feed.slice(0, 40).map((e: MatchEvent) => (
        <li key={e.event_id} className={`flex items-center gap-2 rounded-lg px-2 py-1 ${e.event_type === "GOAL" ? "bg-emerald-500/20" : "hover:bg-white/[0.03]"}`}>
          <span className="num w-11 shrink-0 font-mono text-slate-500">{clock(e.match_clock_ms)}</span>
          <span className={`shrink-0 font-semibold ${e.event_type.startsWith("SHOT") || e.event_type === "GOAL" ? "text-amber-300" : "text-slate-200"}`}>
            {eventLabel(e.event_type, s.lang)}
          </span>
          <span className="truncate text-slate-500">{e.player_ids.map((p) => names.get(p) ?? p).join(" → ")}</span>
          {e.details?.scripted && s.mode === "analyst" && <span className="ml-auto text-[9px] uppercase tracking-wider text-slate-600">script</span>}
          {ACTIONS.has(e.event_type) && e.snapshot_id && !e.details?.scripted && (
            <button type="button" onClick={() => void actions.analyseEvent(e.event_id)} title={L.manualHint}
              className="ml-auto shrink-0 rounded-md bg-leaf-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-leaf-200 hover:bg-leaf-500/25">
              {L.analyseAction}
            </button>
          )}
        </li>
      ))}
      {!feed.length && <li className="px-2 py-2 text-slate-500">{s.lang === "en" ? "Press play to start the event stream." : "Druk op afspelen om de stream te starten."}</li>}
    </ol>
  );
}

function StatsPanel() {
  const s = useApp();
  const L = t(s.lang);
  const m = s.match;
  const v = s.stats;
  if (!m) return null;
  const h = v?.team_stats[m.home.team_id];
  const a = v?.team_stats[m.away.team_id];
  const row = (label: string, hv: number | null, av: number | null, fmt: (x: number | null) => string, model = false) => {
    const total = (hv ?? 0) + (av ?? 0);
    const share = total > 0 ? (hv ?? 0) / total : 0.5;
    return (
      <div className="py-1.5">
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="num font-mono font-semibold text-white">{fmt(hv)}</span>
          <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}{model ? " *" : ""}</span>
          <span className="num font-mono font-semibold text-white">{fmt(av)}</span>
        </div>
        <div className="flex h-1 overflow-hidden rounded-full bg-white/5">
          <span style={{ width: `${share * 100}%`, background: m.home.color_primary }} className="opacity-80" />
          <span style={{ width: `${(1 - share) * 100}%`, background: m.away.color_primary }} className="opacity-80" />
        </div>
      </div>
    );
  };
  return (
    <div aria-label={L.stats}>
      {row(L.passAcc, h?.pass_accuracy ?? null, a?.pass_accuracy ?? null, (x) => pct(x, s.lang, 0))}
      {row(L.possession, h?.possession_share ?? null, a?.possession_share ?? null, (x) => pct(x, s.lang, 0))}
      {row(L.shots, h?.shots ?? 0, a?.shots ?? 0, (x) => String(x ?? 0))}
      {row(L.modeledQuality, h?.total_modeled_shot_quality ?? 0, a?.total_modeled_shot_quality ?? 0, (x) => (x ?? 0).toFixed(2), true)}
      <p className="mt-1 text-[10px] text-slate-500">* {s.lang === "en" ? "model estimate (synthetic, uncalibrated); other values observed in the synthetic feed." :
        "modelschatting (synthetisch, ongekalibreerd); overige waarden waargenomen in de synthetische feed."}</p>
    </div>
  );
}

/** Event feed and team statistics share one quiet panel. */
export function MatchCentre() {
  const s = useApp();
  const L = t(s.lang);
  const [tab, setTab] = useState<"feed" | "stats">("feed");
  return (
    <section className="glass p-3" aria-label={L.matchCentre}>
      <div className="mb-2 flex items-center gap-2">
        <h2 className="eyebrow">{L.matchCentre}</h2>
        <div role="tablist" className="ml-auto flex gap-0.5">
          <button type="button" role="tab" aria-selected={tab === "feed"} onClick={() => setTab("feed")} className="tab">{L.feed}</button>
          <button type="button" role="tab" aria-selected={tab === "stats"} onClick={() => setTab("stats")} className="tab">{L.stats}</button>
        </div>
      </div>
      <div hidden={tab !== "feed"}><EventFeed /></div>
      <div hidden={tab !== "stats"}><StatsPanel /></div>
    </section>
  );
}

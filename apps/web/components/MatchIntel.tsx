"use client";

import type { MatchEvent } from "@parallel/contracts";
import { clock, pct } from "@/lib/format";
import { eventLabel, t, triggerLabel } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

const ACTIONS = new Set(["PASS_ATTEMPTED", "SHOT_ATTEMPTED", "DRIBBLE_ATTEMPTED"]);

export function Scoreboard() {
  const s = useApp();
  const m = s.match;
  if (!m) return <div className="h-24 animate-pulse rounded-xl bg-panel" />;
  const clockMs = s.playback.startClockMs + s.playback.serverT;
  const sh = s.score[m.home.team_id] ?? m.initial_score[m.home.team_id];
  const sa = s.score[m.away.team_id] ?? m.initial_score[m.away.team_id];
  const possName = s.possession === m.home.team_id ? m.home.short_name : s.possession === m.away.team_id ? m.away.short_name : "-";
  return (
    <section className="rounded-xl border border-line bg-panel p-3" aria-label="Scoreboard">
      <div className="flex items-center justify-between gap-2">
        <Team name={m.home.name} short={m.home.short_name} color={m.home.color_primary} />
        <div className="text-center">
          <div className="font-mono text-3xl font-black tracking-tight text-white" data-testid="score">{sh} - {sa}</div>
          <div className="font-mono text-sm text-blue-300">{clock(clockMs)}</div>
        </div>
        <Team name={m.away.name} short={m.away.short_name} color={m.away.color_primary} right />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-slate-400">
        <span>{m.settings.mode === "procedural" ? "Procedural synthetic match" : "Synthetic scenario"} · seed {m.settings.seed}</span>
        <span>▸ {possName}</span>
      </div>
    </section>
  );
}

function Team({ name, short, color, right }: { name: string; short: string; color: string; right?: boolean }) {
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-2 ${right ? "flex-row-reverse text-right" : ""}`}>
      <span className="h-8 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <div className="min-w-0">
        <div className="text-sm font-extrabold text-white">{short}</div>
        <div className="truncate text-[11px] text-slate-400">{name}</div>
      </div>
    </div>
  );
}

export function EventFeed() {
  const s = useApp();
  const L = t(s.lang);
  const names = new Map((s.match?.players ?? []).map((p) => [p.player_id, p.short_name]));
  const feed = s.feed.filter((e) => e.event_type !== "PLAYER_POSITION_UPDATED" && e.event_type !== "BALL_POSITION_UPDATED");
  return (
    <section className="flex min-h-0 flex-col rounded-xl border border-line bg-panel" aria-label={L.events}>
      <h2 className="border-b border-line px-3 py-2 text-xs font-bold uppercase tracking-widest text-slate-400">{L.events}</h2>
      <ol className="max-h-64 min-h-24 overflow-y-auto px-2 py-1 text-xs" aria-live="polite" data-testid="event-feed">
        {feed.slice(0, 40).map((e: MatchEvent) => (
          <li key={e.event_id} className={`flex items-center gap-2 rounded px-1.5 py-1 ${e.event_type === "GOAL" ? "bg-emerald-500/20" : ""}`}>
            <span className="w-11 shrink-0 font-mono text-slate-500">{clock(e.match_clock_ms)}</span>
            <span className={`shrink-0 font-semibold ${e.event_type.startsWith("SHOT") || e.event_type === "GOAL" ? "text-amber-300" : "text-slate-200"}`}>
              {eventLabel(e.event_type, s.lang)}
            </span>
            <span className="truncate text-slate-400">{e.player_ids.map((p) => names.get(p) ?? p).join(" → ")}</span>
            {e.details?.scripted && <span className="ml-auto text-[9px] uppercase text-slate-600">script</span>}
            {ACTIONS.has(e.event_type) && e.snapshot_id && !e.details?.scripted && (
              <button type="button" onClick={() => void actions.analyseEvent(e.event_id)} title={L.manualHint}
                className="ml-auto shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-blue-300 hover:bg-slate-700">
                {L.analyseAction}
              </button>
            )}
          </li>
        ))}
        {!feed.length && <li className="px-1.5 py-2 text-slate-500">{s.lang === "en" ? "Press play to start the event stream." : "Druk op afspelen om de stream te starten."}</li>}
      </ol>
    </section>
  );
}

export function DecisionList() {
  const s = useApp();
  const L = t(s.lang);
  return (
    <section className="rounded-xl border border-line bg-panel" aria-label={L.decisions}>
      <h2 className="border-b border-line px-3 py-2 text-xs font-bold uppercase tracking-widest text-slate-400">{L.decisions}</h2>
      <ul className="max-h-72 overflow-y-auto p-1.5" data-testid="decision-list">
        {s.decisions.map((d) => {
          const a = s.analyses[d.decision_point_id];
          const sel = d.decision_point_id === s.selectedDecisionId;
          const status = a?.status;
          return (
            <li key={d.decision_point_id}>
              <button type="button" onClick={() => {
                actions.control({ type: "seek", t_ms: (d.outcome_time_ms ?? d.sim_time_ms) + 200 });
                void actions.selectDecision(d.decision_point_id);
              }}
                className={`w-full rounded-lg px-2.5 py-2 text-left transition ${sel ? "bg-blue-600/20 ring-1 ring-blue-400/60" : "hover:bg-slate-800/70"}`}>
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-slate-400">{clock(d.match_clock_ms)}</span>
                  <span className="truncate font-semibold text-white">{d.actor_name}</span>
                  {d.source === "manual" && <span className="rounded bg-slate-700 px-1 text-[9px] uppercase text-slate-300">manual</span>}
                  <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    status === "verified" ? "bg-emerald-500/15 text-emerald-300" : status === "running" || status === "pending" ? "bg-amber-500/15 text-amber-300"
                      : status ? "bg-slate-700 text-slate-300" : s.detected.includes(d.decision_point_id) ? "bg-violet-500/15 text-violet-300" : "bg-slate-800 text-slate-500"}`}>
                    {status ?? (s.detected.includes(d.decision_point_id) ? "detected" : `score ${d.candidate_score.toFixed(2)}`)}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-[11px] text-slate-400">
                  {d.actual_action.label.replace(" (actual)", "")} → {eventLabel(d.actual_outcome, s.lang)} · {triggerLabel(d.triggers[0] ?? "", s.lang)}
                </div>
              </button>
            </li>
          );
        })}
        {!s.decisions.length && <li className="p-2 text-xs text-slate-500">-</li>}
      </ul>
    </section>
  );
}

export function StatsPanel() {
  const s = useApp();
  const L = t(s.lang);
  const m = s.match;
  const v = s.stats;
  if (!m) return null;
  const h = v?.team_stats[m.home.team_id];
  const a = v?.team_stats[m.away.team_id];
  const row = (label: string, hv: string, av: string, model = false) => (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 py-0.5 text-xs">
      <span className="text-right font-mono text-white">{hv}</span>
      <span className="text-center text-[10px] uppercase tracking-wide text-slate-500">{label}{model ? " *" : ""}</span>
      <span className="font-mono text-white">{av}</span>
    </div>
  );
  return (
    <section className="rounded-xl border border-line bg-panel p-3" aria-label={L.stats}>
      <h2 className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">{L.stats}</h2>
      {row(L.passAcc, pct(h?.pass_accuracy ?? null, s.lang, 0), pct(a?.pass_accuracy ?? null, s.lang, 0))}
      {row(L.possession, pct(h?.possession_share ?? null, s.lang, 0), pct(a?.possession_share ?? null, s.lang, 0))}
      {row(L.shots, String(h?.shots ?? 0), String(a?.shots ?? 0))}
      {row(L.modeledQuality, (h?.total_modeled_shot_quality ?? 0).toFixed(2), (a?.total_modeled_shot_quality ?? 0).toFixed(2), true)}
      <p className="mt-1 text-[10px] text-slate-500">* {s.lang === "en" ? "model estimate (synthetic, uncalibrated); other values observed in the synthetic feed. Updated at stream resets." :
        "modelschatting (synthetisch, ongekalibreerd); overige waarden waargenomen in de synthetische feed."}</p>
    </section>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { pct } from "@/lib/format";
import { t } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";
import DecisionValue from "./DecisionValue";

export default function RecapDrawer() {
  const s = useApp();
  const L = t(s.lang);
  const [tab, setTab] = useState<"casual" | "analyst">(s.mode === "analyst" ? "analyst" : "casual");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (s.recapOpen) ref.current?.focus();
  }, [s.recapOpen]);
  useEffect(() => {
    if (s.recapOpen && !s.recap && !s.recapLoading) void actions.openRecap();
  }, [s.lang, s.recapOpen, s.recap, s.recapLoading]);
  if (!s.recapOpen) return null;
  const r = s.recap;
  const fmt = r ? r[tab] : null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" role="dialog" aria-modal="true" aria-label={L.recap}
      onKeyDown={(e) => e.key === "Escape" && actions.closeRecap()}>
      <div ref={ref} tabIndex={-1} className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-panel p-5 outline-none" data-testid="recap">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-extrabold text-white">{L.recap}</h2>
          <button type="button" onClick={() => actions.closeRecap()} className="rounded bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700">{L.close}</button>
        </div>
        {s.recapLoading && <p className="mt-4 text-sm text-slate-400">…</p>}
        {r && fmt && (
          <>
            <div className="mt-3 flex gap-1" role="tablist">
              {(["casual", "analyst"] as const).map((k) => (
                <button key={k} role="tab" aria-selected={tab === k} type="button" onClick={() => setTab(k)}
                  className={`rounded-md px-3 py-1 text-xs font-semibold ${tab === k ? "bg-slate-200 text-slate-900" : "bg-slate-800 text-slate-300"}`}>
                  {k === "casual" ? L.casual : L.analyst}
                </button>
              ))}
            </div>
            <h3 className="mt-4 text-xl font-black text-white">{fmt.headline}</h3>
            <div className="mt-2 space-y-2 text-sm leading-relaxed text-slate-200">
              {fmt.story.map((p, i) => <p key={i}>{p}</p>)}
            </div>
            {tab === "analyst" && (
              <>
                <h4 className="mt-5 text-xs font-bold uppercase tracking-widest text-slate-400">Momentum</h4>
                <table className="mt-1 w-full text-xs">
                  <tbody>
                    {r.momentum.map((m) => (
                      <tr key={m.start_clock} className="border-t border-line">
                        <td className="py-1 font-mono text-slate-400">{m.start_clock}–{m.end_clock}</td>
                        {Object.entries(m.possession_share).map(([team, v]) => (
                          <td key={team} className="font-mono text-slate-200">{team} {pct(v, s.lang, 0)} · {m.final_third_entries[team]} final-third</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <h4 className="mt-5 text-xs font-bold uppercase tracking-widest text-slate-400">Players</h4>
                <ul className="mt-1 space-y-1 text-xs text-slate-300">
                  {r.player_performances.map((p) => <li key={p.player_id}>{p.summary}</li>)}
                </ul>
              </>
            )}
            <h4 className="mt-5 text-xs font-bold uppercase tracking-widest text-slate-400">{L.decisionValue}</h4>
            <div className="mt-1"><DecisionValue compact={tab === "casual"} /></div>
            <h4 className="mt-5 text-xs font-bold uppercase tracking-widest text-slate-400">Key moments</h4>
            <ul className="mt-1 space-y-1 text-xs text-slate-300">
              {r.key_events.map((k, i) => <li key={i}><span className="font-mono text-slate-500">{k.match_clock}</span> {k.text}</li>)}
            </ul>
            <p className="mt-5 text-[11px] text-slate-500">{r.disclaimer}</p>
            <p className="mt-1 font-mono text-[10px] text-slate-600">refs: {r.referenced_event_ids.length} events · {r.referenced_analysis_ids.length} analyses · {r.generated_by}</p>
          </>
        )}
      </div>
    </div>
  );
}

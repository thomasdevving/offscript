"use client";

import type { DecisionValueAggregate } from "@offscript/contracts";
import { useEffect, useState } from "react";
import { leftOnTable, oneLiner, pp } from "@/lib/decisionValue";
import { activeFollow } from "@/lib/follow";
import { t, tr } from "@/lib/i18n";
import { actions, useApp } from "@/lib/store";

/**
 * Decision Value Added: modelled goal chance each player's choices left on the table, from
 * verified analyses only. Used in the match centre and the recap.
 */
export default function DecisionValue({ compact = false }: { compact?: boolean }) {
  const s = useApp();
  const L = t(s.lang);
  const en = s.lang !== "nl";
  const [showThin, setShowThin] = useState(false);
  const r = s.decisionValue && s.decisionValue.match_id === s.matchId ? s.decisionValue : null;
  useEffect(() => {
    if (s.matchId && !r && !s.decisionValueLoading && !s.decisionValueError) void actions.loadDecisionValue();
  }, [s.matchId, r, s.decisionValueLoading, s.decisionValueError]);

  if (!r) {
    return (
      <div className="py-2 text-xs text-slate-500" data-testid="decision-value">
        {s.decisionValueError ? <span role="alert">{s.decisionValueError}</span> : "…"}
      </div>
    );
  }
  const analyst = s.mode === "analyst";
  const colors: Record<string, string> = s.match
    ? { [s.match.home.team_id]: s.match.home.color_primary, [s.match.away.team_id]: s.match.away.color_primary }
    : {};
  const shortNames = Object.fromEntries((s.match?.players ?? []).map((p) => [p.player_id, p.short_name]));
  const remaining = r.decisions_detected - r.decisions_analysed - r.decisions_pending;
  const notEnough = en ? "Not enough decisions" : "Te weinig beslissingen";
  const f = activeFollow(s.follow, s.match);
  // The followed player or team, and (for a followed team) its players, are marked in the table.
  const followed = (a: DecisionValueAggregate) => !!f && (a.key === f.id || (f.kind === "team" && a.scope === "player" && a.team_id === f.id));

  const row = (a: DecisionValueAggregate) => {
    const lt = leftOnTable(a, s.lang);
    return (
      <tr key={`${a.scope}-${a.key}`} className={`border-t border-line ${followed(a) ? "bg-leaf-500/10" : ""}`} data-testid={`dva-row-${a.scope}`}
        data-followed={followed(a) || undefined}>
        <td className="py-1 pr-2">
          <span className="mr-1.5 inline-block h-2.5 w-1 rounded-full align-middle" style={{ background: colors[a.team_id ?? a.key] ?? "#64748b" }} />
          <span className="font-semibold text-white">{followed(a) && <span className="text-leaf-300">★ </span>}{a.name}</span>
        </td>
        <td className="num px-1 text-right font-mono text-slate-400">{a.n_decisions}</td>
        {lt ? (
          analyst ? (
            <>
              <td className="num px-1 text-right font-mono text-white">{pp(a.dva_sum ?? 0, s.lang)}</td>
              <td className="num px-1 text-right font-mono text-slate-400">{pp(a.dva_sum_ci95_low ?? 0, s.lang)} … {pp(a.dva_sum_ci95_high ?? 0, s.lang)}</td>
              <td className="num px-1 text-right font-mono text-slate-400">{pp(a.dva_mean ?? 0, s.lang)}</td>
              <td className="num pl-1 text-right font-mono text-slate-400">{a.clear_misses}</td>
            </>
          ) : (
            <td className="num pl-1 text-right font-mono text-white">
              {lt.value} pp <span className="text-slate-500">({lt.low}–{lt.high})</span>
            </td>
          )
        ) : (
          <td colSpan={analyst ? 4 : 1} className="pl-1 text-right text-[11px] text-slate-500" data-testid="dva-not-enough">{notEnough}</td>
        )}
      </tr>
    );
  };

  return (
    <div data-testid="decision-value" className="text-xs">
      <p className="text-sm leading-snug text-slate-100" data-testid="dva-oneliner">{oneLiner(r, s.mode, s.lang, shortNames)}</p>
      <p className="mt-1 text-[11px] text-slate-500">
        {en
          ? `${r.decisions_analysed} of ${r.decisions_detected} detected decisions analysed and verified`
          : `${r.decisions_analysed} van ${r.decisions_detected} gedetecteerde beslissingen geanalyseerd en geverifieerd`}
        {r.decisions_pending > 0 && (en ? ` · ${r.decisions_pending} running` : ` · ${r.decisions_pending} bezig`)}
        {remaining > 0 && (
          <button type="button" onClick={() => void actions.analyseAllDecisions()} disabled={s.decisionValueLoading}
            data-testid="dva-analyse-all"
            className="ml-2 rounded-md bg-leaf-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-leaf-200 hover:bg-leaf-500/25 disabled:opacity-50">
            {en ? `Analyse ${remaining} remaining` : `Analyseer ${remaining} resterende`}
          </button>
        )}
      </p>
      <table className="mt-2 w-full" data-testid="dva-table">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500">
            <th className="py-1 font-medium">{tr(s.lang, { en: "Player", nl: "Speler", es: "Jugador", fr: "Joueur", de: "Spieler" })}</th>
            <th className="px-1 text-right font-medium" title={en ? "Analysed decisions" : "Geanalyseerde beslissingen"}>n</th>
            {analyst ? (
              <>
                <th className="px-1 text-right font-medium">DVA (pp)</th>
                <th className="px-1 text-right font-medium">95%</th>
                <th className="px-1 text-right font-medium">{en ? "Mean" : "Gem."}</th>
                <th className="pl-1 text-right font-medium" title={en ? "Decisions with a clearly better alternative" : "Beslissingen met een duidelijk betere optie"}>{en ? "Clear" : "Duidelijk"}</th>
              </>
            ) : (
              <th className="pl-1 text-right font-medium">{tr(s.lang, { en: "Goal chance left (95%)", nl: "Gemiste doelkans (95%)", es: "Probabilidad de gol perdida (95%)", fr: "Chance de but laissée (95%)", de: "Liegengelassene Torchance (95%)" })}</th>
            )}
          </tr>
        </thead>
        <tbody>
          {(() => {
            // Players with too few decisions for a value are folded into one line, unless nobody has a value yet.
            const rated = r.players.filter((p) => leftOnTable(p, s.lang));
            const thin = r.players.filter((p) => !leftOnTable(p, s.lang));
            if (!rated.length || showThin) return r.players.map(row);
            // A followed player stays visible even with too few decisions for a value.
            const keep = thin.filter((p) => f?.kind === "player" && p.key === f.id);
            const folded = thin.filter((p) => !keep.includes(p));
            return (
              <>
                {rated.map(row)}
                {keep.map(row)}
                {folded.length > 0 && (
                  <tr className="border-t border-line">
                    <td colSpan={6} className="py-1">
                      <button type="button" onClick={() => setShowThin(true)} data-testid="dva-show-thin"
                        className="text-[11px] text-slate-500 hover:text-slate-300">
                        {en ? `+ ${folded.length} players with fewer than ${r.min_decisions} decisions` : `+ ${folded.length} spelers met minder dan ${r.min_decisions} beslissingen`}
                      </button>
                    </td>
                  </tr>
                )}
              </>
            );
          })()}
          {!r.players.length && (
            <tr><td colSpan={6} className="py-2 text-slate-500">{en ? "No verified analyses yet." : "Nog geen geverifieerde analyses."}</td></tr>
          )}
        </tbody>
        {!compact && r.players.length > 0 && (
          <tbody className="border-t-2 border-line">{[...r.teams, r.match].map(row)}</tbody>
        )}
      </table>
      <details className="mt-2 text-[11px] text-slate-500">
        <summary className="cursor-pointer">{L.assumptions}</summary>
        <p className="mt-1 leading-relaxed">{r.method}</p>
        <p className="mt-1 leading-relaxed">
          {en
            ? "The best option is picked from the same simulations it is scored on, which makes DVA lean negative; intervals cover simulation noise only."
            : "De beste optie wordt gekozen uit dezelfde simulaties waarop ze wordt gescoord, waardoor DVA naar negatief neigt; intervallen dekken alleen simulatieruis."}
        </p>
      </details>
      <p className="mt-1 text-[10px] text-slate-600">{r.disclaimer}</p>
    </div>
  );
}

"use client";

import type { MultiversePlanning } from "@parallel/contracts";
import { pct } from "@/lib/format";
import { useApp } from "@/lib/store";
import { useMv } from "@/lib/mvStore";

function heat(v: number, max: number): string {
  const k = max > 0 ? Math.min(1, v / max) : 0;
  return `rgba(${Math.round(37 + 200 * k)}, ${Math.round(99 + 80 * k)}, ${Math.round(235 - 150 * k)}, ${0.18 + 0.6 * k})`;
}

export function ResponseMatrix({ p }: { p: MultiversePlanning }) {
  const lang = useApp((s) => s.lang);
  const actions = Array.from(new Map(p.attack_proposals.map((a) => [a.action.action_id, a])).values())
    .filter((a) => p.matrix.some((c) => c.action_id === a.action.action_id));
  const strategies = Array.from(new Set(p.matrix.map((c) => c.strategy_id)));
  const label = (sid: string) => sid === "def-balanced" ? "Balanced" :
    p.defense_proposals.find((d) => d.strategy.strategy_id === sid)?.strategy.label ?? sid;
  const max = Math.max(0.0001, ...p.matrix.map((c) => c.xg));
  const s = p.summary;
  return (
    <div className="overflow-x-auto" data-testid="response-matrix">
      <table className="w-full border-separate border-spacing-0.5 text-[10px]">
        <thead>
          <tr>
            <th className="text-left text-slate-500">Attack ↓ / Defence →</th>
            {strategies.map((sid) => (
              <th key={sid} className={`max-w-20 px-1 text-left font-semibold ${s?.defensive_counter_id === sid ? "text-orange-300" : "text-slate-300"}`}>
                {label(sid)}{s?.defensive_counter_id === sid ? " ★" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {actions.map((a) => (
            <tr key={a.action.action_id}>
              <td className={`pr-1 font-semibold ${s?.selected_action_id === a.action.action_id ? "text-blue-300" : "text-slate-200"}`}>
                {a.action.label.replace(" (actual)", "")}
                <span className="ml-1 rounded bg-slate-800 px-1 text-[8px] uppercase text-slate-400">{a.source === "user" ? "user" : a.source === "actual" ? "actual" : "AI"}</span>
              </td>
              {strategies.map((sid) => {
                const c = p.matrix.find((x) => x.action_id === a.action.action_id && x.strategy_id === sid);
                return (
                  <td key={sid} className="rounded px-1 py-1 text-center font-mono text-white" style={{ background: c ? heat(c.xg, max) : "transparent" }}
                    title={c ? `95%: ${pct(c.xg_ci95_low, lang)}–${pct(c.xg_ci95_high, lang)} · turnover ${pct(c.p_turnover.value, lang, 0)} · ${c.n_rollouts} sims${c.cached ? " · cached" : ""}` : ""}>
                    {c ? pct(c.xg, lang) : "–"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10px] text-slate-500">
        Cells: modelled expected goals within {10} s ({p.rollouts_per_cell} paired simulations each, same frozen state). ★ = defence&apos;s best counter to the selected action.
      </p>
    </div>
  );
}

export default function AgentBattle({ p }: { p: MultiversePlanning }) {
  const s = p.summary;
  const lab = (aid: string | null | undefined) =>
    p.attack_proposals.find((a) => a.action.action_id === aid)?.action.label.replace(" (actual)", "") ?? "–";
  return (
    <section className="space-y-2" data-testid="agent-battle">
      <ol className="space-y-1.5">
        {p.rounds.map((r) => {
          const atk = p.attack_proposals.filter((a) => a.round === r.round);
          const dfn = p.defense_proposals.filter((d) => d.round === r.round);
          const revision = p.steps.find((st) => st.agent === "attacking_agent" && st.attempt === r.round)?.notes.find((n) => n.startsWith("Revision"));
          return (
            <li key={r.round} className="rounded-lg border border-line bg-slate-950/50 p-2 text-[11px]">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">Round {r.round}</div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="font-semibold text-sky-300">Attacking agent</div>
                  {atk.length ? atk.map((a) => <div key={a.proposal_id} className="text-slate-200">+ {a.action.label.replace(" (actual)", "")}</div>)
                    : <div className="text-slate-500">kept plan</div>}
                  {revision && <div className="mt-0.5 text-amber-200">{revision.replace("Revision: ", "↻ ")}</div>}
                </div>
                <div>
                  <div className="font-semibold text-orange-300">Defending agent</div>
                  {dfn.length ? dfn.map((d) => <div key={d.proposal_id} className="text-slate-200">+ {d.strategy.label}</div>)
                    : <div className="text-slate-500">kept responses</div>}
                </div>
              </div>
              <div className="mt-1 text-[10px] text-slate-400">Simulator: {r.new_cells} new pairs · {r.note}</div>
            </li>
          );
        })}
      </ol>
      <ResponseMatrix p={p} />
      {s && (
        <div className="grid grid-cols-2 gap-1.5 text-[11px]" data-testid="strategy-summary">
          <div className="rounded bg-slate-900 p-1.5"><div className="text-slate-500">Most robust</div><div className="font-semibold text-white">{lab(s.most_robust_action_id)}</div></div>
          <div className="rounded bg-slate-900 p-1.5"><div className="text-slate-500">Highest upside</div><div className="font-semibold text-white">{lab(s.highest_upside_action_id)}</div></div>
          <div className="rounded bg-slate-900 p-1.5"><div className="text-slate-500">Best expected</div><div className="font-semibold text-white">{lab(s.best_expected_action_id)}</div></div>
          <div className="rounded bg-slate-900 p-1.5"><div className="text-slate-500">Defence&apos;s counter</div>
            <div className="font-semibold text-orange-200">{s.defensive_counter_id === "def-balanced" ? "Balanced shape" :
              p.defense_proposals.find((d) => d.strategy.strategy_id === s.defensive_counter_id)?.strategy.label}</div>
            <div className="font-mono text-slate-400">{s.counter_effect_pp >= 0 ? "+" : ""}{s.counter_effect_pp.toFixed(1)} pp</div></div>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        <span className={`rounded px-1.5 py-0.5 font-semibold ${p.verification_status === "verified" ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`} data-testid="mv-verification">
          {p.verification_status === "verified" ? "✓ verified" : p.verification_status} ({p.verification_checks.filter((c) => c.passed).length}/{p.verification_checks.length} checks)
        </span>
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{p.cells_computed} simulated · {p.cache_hits} cached</span>
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{p.live_model_calls ? `${p.live_model_calls} live model calls` : "deterministic planner"}</span>
        {p.duration_ms && <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{(p.duration_ms / 1000).toFixed(1)} s</span>}
        {p.degraded && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300">degraded</span>}
      </div>
    </section>
  );
}

export function PlanningSteps({ p }: { p: MultiversePlanning }) {
  return (
    <ol className="space-y-1 text-[10px]" data-testid="mv-steps">
      {p.steps.map((st) => (
        <li key={st.step_id} className="rounded border border-line bg-slate-950/50 px-2 py-1">
          <div className="flex gap-2">
            <span className="font-semibold text-white">{st.agent.replace("_agent", "").replace("_", " ")}</span>
            <span className="text-slate-400">#{st.attempt} {st.task}</span>
            <span className="ml-auto font-mono text-slate-500">{st.duration_ms?.toFixed(0)} ms · {st.model}</span>
          </div>
          <div className="text-slate-400">tools: {st.tool_calls.map((t) => t.tool_name).join(", ") || "–"}{st.handoff_to ? ` → ${st.handoff_to}` : ""}</div>
          {st.notes.slice(0, 2).map((n, i) => <div key={i} className="text-amber-200">• {n}</div>)}
        </li>
      ))}
      {p.verification_checks.length > 0 && (
        <li className="rounded border border-line bg-slate-950/50 px-2 py-1">
          {p.verification_checks.map((c) => (
            <div key={String(c.check_id)} className={c.passed ? "text-emerald-300" : "text-red-300"}>{c.passed ? "✓" : "✗"} {String(c.name)}</div>
          ))}
        </li>
      )}
    </ol>
  );
}

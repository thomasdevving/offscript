"use client";

import type { ActionResult, CounterfactualAnalysis, DecisionPoint, Language, Narrative, Overlay,
  PairwiseComparison } from "@parallel/contracts";
import { useEffect, useState } from "react";
import { clock, cleanLabel, pct, signedPp } from "@/lib/format";
import { eventLabel, t, triggerLabel } from "@/lib/i18n";
import { mv } from "@/lib/mvStore";
import { actions, selectedAnalysis, selectedDecision, useApp } from "@/lib/store";
import ComparisonChart from "./ComparisonChart";
import RecoveryPanel from "./RecoveryPanel";
import WorkflowInspector, { AgentPipeline } from "./WorkflowInspector";

function narrativeFor(a: CounterfactualAnalysis, mode: string, lang: Language): Narrative | undefined {
  return a.narratives.find((n) => n.audience === mode && n.language === lang);
}

function StatusBadges({ a }: { a: CounterfactualAnalysis }) {
  const s = useApp();
  const L = t(s.lang);
  const v = a.verification?.status;
  return (
    <div className="flex flex-wrap gap-1.5 text-[10px] font-semibold uppercase tracking-wide">
      {a.status === "verified" && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300" data-testid="verified-badge">✓ {L.verified}{v === "verified_with_warnings" ? " (warnings)" : ""}</span>}
      {a.status === "unavailable" && <span className="rounded bg-slate-700 px-1.5 py-0.5 text-slate-200">{L.unavailable}</span>}
      {a.cached && <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{L.cached}</span>}
      {a.model.degraded && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300">{L.degraded}</span>}
      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
        {a.model.agent_mode === "foundry" ? `Foundry · ${a.model.deployment} · ${a.model.live_model_calls} live calls` : L.policy}
      </span>
      {a.fault_injection.length > 0 && <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-red-300">fault: {a.fault_injection.join(", ")}</span>}
    </div>
  );
}

function DecisionHeader({ d }: { d: DecisionPoint }) {
  const s = useApp();
  const L = t(s.lang);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-sm text-blue-300">{clock(d.match_clock_ms)}</span>
        <h2 className="text-lg font-extrabold text-white">{d.actor_name}</h2>
      </div>
      <div className="text-sm text-slate-300">
        {cleanLabel(d.actual_action.label)} → <span className="font-semibold text-amber-300">{eventLabel(d.actual_outcome, s.lang)}</span>
        <span className="text-slate-500"> · {L.observedOutcome.toLowerCase()}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {d.triggers.map((tr) => (
          <span key={tr} className="rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5 text-[10px] text-violet-200">{triggerLabel(tr, s.lang)}</span>
        ))}
      </div>
    </div>
  );
}

function CasualCards({ a, res, comps }: { a: CounterfactualAnalysis; res: Map<string, ActionResult>; comps: Map<string, PairwiseComparison> }) {
  const s = useApp();
  const L = t(s.lang);
  const H = a.simulation?.config.horizon_s ?? 10;
  const best = [...a.candidates].filter((c) => !c.is_actual).sort((x, y) => (res.get(y.action_id)?.p_goal.value ?? 0) - (res.get(x.action_id)?.p_goal.value ?? 0))[0];
  const favoured = best && comps.get(best.action_id)?.verdict === "more_promising";
  return (
    <div className="grid gap-2" data-testid="casual-cards">
      {a.candidates.map((c) => {
        const r = res.get(c.action_id);
        const sel = s.selectedActionId === c.action_id;
        return (
          <button key={c.action_id} type="button" onClick={() => void actions.selectAction(c.action_id)}
            className={`flex items-center gap-3 rounded-xl border p-3 text-left transition ${sel ? "border-blue-400 bg-blue-600/15" : c.is_actual ? "border-slate-500/60 bg-slate-800/40" : "border-violet-400/30 bg-slate-900/60 hover:border-violet-300/60"}`}
            data-testid={`option-${c.is_actual ? "actual" : "alt"}`}>
            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                {c.is_actual ? L.actual : L.alternative}{favoured && best?.action_id === c.action_id ? ` · ${L.modelFavours}` : ""}
              </div>
              <div className="truncate text-base font-bold text-white">{cleanLabel(c.label)}</div>
              <div className="text-[11px] text-slate-400">{L.goalChance} {H}{L.seconds} · {r?.n_rollouts ?? "-"} {L.simulations}</div>
            </div>
            <div className="text-right">
              <div className={`font-mono text-2xl font-black ${favoured && best?.action_id === c.action_id ? "text-blue-300" : "text-white"}`}>{r ? pct(r.p_goal.value, s.lang) : "…"}</div>
              <div className="text-[11px] font-semibold text-blue-300">{L.watch} ▸</div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function AnalystTable({ a, res, comps }: { a: CounterfactualAnalysis; res: Map<string, ActionResult>; comps: Map<string, PairwiseComparison> }) {
  const s = useApp();
  const L = t(s.lang);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]" data-testid="analyst-table">
        <thead className="text-[10px] uppercase text-slate-500">
          <tr className="[&>th]:px-1"><th className="py-1 pr-2">Option</th><th>P(goal) [95%]</th><th>{L.shotChance}</th><th>{L.turnover}</th><th>1st ok</th><th>{L.vsActual}</th></tr>
        </thead>
        <tbody>
          {a.candidates.map((c) => {
            const r = res.get(c.action_id);
            const cm = comps.get(c.action_id);
            if (!r) return null;
            return (
              <tr key={c.action_id} className={`border-t border-line [&>td]:px-1 ${s.selectedActionId === c.action_id ? "bg-blue-600/10" : ""}`}>
                <td className="py-1.5 pr-2">
                  <button type="button" onClick={() => void actions.selectAction(c.action_id)} className="text-left font-semibold text-white hover:text-blue-300">
                    {cleanLabel(c.label)}{c.is_actual ? " *" : ""}
                  </button>
                </td>
                <td className="font-mono text-white">{pct(r.p_goal.value, s.lang)} <span className="text-slate-500">[{pct(r.p_goal.ci95_low, s.lang)}–{pct(r.p_goal.ci95_high, s.lang)}]</span></td>
                <td className="font-mono">{pct(r.p_shot.value, s.lang, 0)}</td>
                <td className="font-mono">{pct(r.p_turnover.value, s.lang, 0)}</td>
                <td className="font-mono">{pct(r.p_first_action_success.value, s.lang, 0)}</td>
                <td className="font-mono">
                  {cm ? (<span title={`[${signedPp(cm.diff_ci95_low, s.lang)}, ${signedPp(cm.diff_ci95_high, s.lang)}]`}
                    className={cm.verdict === "more_promising" ? "text-emerald-300" : cm.verdict === "less_promising" ? "text-red-300" : "text-slate-300"}>
                    {signedPp(cm.diff_p_goal, s.lang)}</span>) : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-1 space-y-0.5 text-[10px] text-slate-400">
        {a.simulation?.comparisons.map((cm) => {
          const c = a.candidates.find((x) => x.action_id === cm.action_id);
          return (
            <div key={cm.action_id}>
              {cleanLabel(c?.label ?? "")}: {signedPp(cm.diff_p_goal, s.lang)} [{signedPp(cm.diff_ci95_low, s.lang)}, {signedPp(cm.diff_ci95_high, s.lang)}] →{" "}
              <span className="font-semibold text-slate-200">{L.verdict[cm.verdict]}</span>
              {cm.secondary_note && <span> · {cm.secondary_note}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Evidence({ a, d }: { a: CounterfactualAnalysis; d: DecisionPoint }) {
  const s = useApp();
  const L = t(s.lang);
  const [open, setOpen] = useState(s.mode === "analyst");
  // Analysts see the evidence by default; other modes keep it one click away.
  useEffect(() => setOpen(s.mode === "analyst"), [s.mode]);
  const sim = a.simulation;
  return (
    <section className="rounded-lg border border-line bg-slate-950/40">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="evidence-toggle"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-bold text-slate-200">
        {L.evidence} <span className="text-slate-500">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3 text-[11px] text-slate-300" data-testid="evidence-panel">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            <span className="text-slate-500">Distance to goal</span><span className="font-mono">{d.features.distance_to_goal_m.toFixed(1)} m</span>
            <span className="text-slate-500">Opponents within 5 m</span><span className="font-mono">{d.features.pressure_count_5m}</span>
            <span className="text-slate-500">Nearest defender</span><span className="font-mono">{d.features.nearest_defender_m.toFixed(1)} m</span>
            <span className="text-slate-500">Open teammates (model)</span><span className="font-mono">{d.features.open_teammates}</span>
            {d.features.actual_shot_quality != null && (<><span className="text-slate-500">Shot itself (modeled)</span><span className="font-mono">{pct(d.features.actual_shot_quality, s.lang)}</span></>)}
            {sim && (<>
              <span className="text-slate-500">{L.rollouts}</span><span className="font-mono">{sim.config.rollouts}{sim.partial ? " (partial)" : ""}</span>
              <span className="text-slate-500">{L.horizon}</span><span className="font-mono">{sim.config.horizon_s} s</span>
              <span className="text-slate-500">{L.seed}</span><span className="font-mono">{sim.config.seed}</span>
              <span className="text-slate-500">{L.simulator}</span><span className="font-mono">{sim.simulator_version}</span>
              <span className="text-slate-500">Paired streams (CRN)</span><span className="font-mono">{String(sim.config.common_random_numbers)}</span>
              <span className="text-slate-500">Run time</span><span className="font-mono">{sim.duration_ms?.toFixed(0)} ms</span>
            </>)}
          </div>
          {a.candidates.some((c) => Object.keys(c.features ?? {}).length) && (
            <div>
              <div className="mb-1 font-semibold text-slate-200">Option features (noise-free model estimates)</div>
              {a.candidates.filter((c) => !c.is_actual).map((c) => (
                <div key={c.action_id} className="font-mono text-[10px] text-slate-400">
                  {cleanLabel(c.label)}: {Object.entries(c.features).filter(([k]) => k !== "heuristic_value").map(([k, v]) => `${k.replace(/_/g, " ")} ${Number(v).toFixed(2)}`).join(" · ")}
                </div>
              ))}
            </div>
          )}
          {a.verification && (
            <div>
              <div className="mb-1 font-semibold text-slate-200">{L.checks} ({a.verification.checks.filter((c) => c.passed).length}/{a.verification.checks.length})</div>
              <ul className="space-y-0.5">
                {a.verification.checks.map((c) => (
                  <li key={c.check_id} className="flex gap-1.5">
                    <span className={c.passed ? "text-emerald-400" : c.severity === "error" ? "text-red-400" : "text-amber-400"}>{c.passed ? "✓" : c.severity === "error" ? "✗" : "!"}</span>
                    <span>{c.name}<span className="text-slate-500"> · {c.details}</span></span>
                  </li>
                ))}
              </ul>
              {a.verification.agent_assessment && <p className="mt-1 text-slate-400">Verification Agent: {a.verification.agent_assessment}</p>}
            </div>
          )}
          <p className="text-[10px] text-slate-500">
            {s.lang === "en"
              ? "Every number shown is a computed field (traceable in the evidence table). Intervals are Monte Carlo error only; the football model itself is synthetic and uncalibrated."
              : "Elk getal is een berekend veld (herleidbaar in de bewijstabel). Intervallen tonen alleen de Monte-Carlo-fout; het voetbalmodel is synthetisch en ongekalibreerd."}
          </p>
        </div>
      )}
    </section>
  );
}

function BroadcasterView({ a, overlays }: { a: CounterfactualAnalysis; overlays: Overlay[] }) {
  const s = useApp();
  const L = t(s.lang);
  const [copied, setCopied] = useState(false);
  const ov = overlays.find((o) => o.analysis_id === a.analysis_id && o.viewer_mode === "broadcaster" && o.language === s.lang);
  const n = narrativeFor(a, "broadcaster", s.lang);
  if (!ov && !n) return null;
  const json = JSON.stringify(ov ?? n, null, 2);
  return (
    <div className="space-y-2" data-testid="broadcaster-view">
      {n && (
        <div className="overflow-hidden rounded-lg">
          <div className="flex">
            <div className="flex items-center bg-blue-600 px-2 text-[10px] font-black tracking-widest text-white">PARALLEL</div>
            <div className="flex-1 bg-slate-950 px-3 py-2">
              <div className="text-sm font-extrabold uppercase text-white">{n.headline}</div>
              <div className="text-xs text-blue-100" data-testid="caption">{n.caption}</div>
            </div>
          </div>
        </div>
      )}
      {ov && (
        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div className="rounded bg-slate-900 p-1.5"><div className="font-mono text-white">{clock(ov.match_time_ms)}</div><div className="text-slate-500">start</div></div>
          <div className="rounded bg-slate-900 p-1.5"><div className="font-mono text-white">{(ov.duration_ms / 1000).toFixed(0)} s</div><div className="text-slate-500">{L.duration}</div></div>
          <div className="rounded bg-slate-900 p-1.5"><div className="font-mono text-white">{ov.priority}</div><div className="text-slate-500">{L.priority}</div></div>
        </div>
      )}
      {ov && <div className="text-[11px] text-slate-400">{L.expires}: {ov.expires.on_event_types.join(", ")} · max {(ov.expires.max_age_ms ?? 0) / 1000}s · {ov.verification_status}</div>}
      <div className="rounded-lg border border-line bg-slate-950">
        <div className="flex items-center justify-between border-b border-line px-2 py-1 text-[11px] text-slate-400">
          {L.overlayJson}
          <button type="button" className="rounded bg-slate-800 px-2 py-0.5 text-slate-200 hover:bg-slate-700"
            onClick={() => { void navigator.clipboard?.writeText(json); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
            {copied ? L.copied : L.copy}
          </button>
        </div>
        <pre className="max-h-48 overflow-auto p-2 text-[10px] leading-snug text-emerald-200" data-testid="overlay-json">{json}</pre>
      </div>
    </div>
  );
}

export default function AnalysisPanel() {
  const s = useApp();
  const L = t(s.lang);
  const d = selectedDecision(s);
  const a = selectedAnalysis(s);
  if (!d) {
    return (
      <div className="rounded-xl border border-line bg-panel p-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">{L.parallelAnalysis}</h2>
        <p className="mt-2 text-sm text-slate-400">{L.noDecision}</p>
        <p className="mt-3 text-[11px] text-slate-500">{L.keyboard}</p>
      </div>
    );
  }
  const res = new Map((a?.simulation?.results ?? []).map((r) => [r.action_id, r]));
  const comps = new Map((a?.simulation?.comparisons ?? []).map((c) => [c.action_id, c]));
  const n = a ? narrativeFor(a, s.mode, s.lang) : undefined;
  const running = a && (a.status === "pending" || a.status === "running");
  const overall = a?.simulation?.overall_verdict;
  return (
    <div className="space-y-3">
      <section className="space-y-3 rounded-xl border border-line bg-panel p-4" aria-label={L.parallelAnalysis} data-testid="analysis-panel">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">{L.parallelAnalysis}</h2>
          {s.recovery && (
            <button type="button" onClick={() => useApp.setState({ recovery: null, recoveryFault: null })} className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-200 hover:bg-slate-700">
              ← {s.lang === "en" ? "main analysis" : "hoofdanalyse"}
            </button>
          )}
        </div>
        <DecisionHeader d={d} />
        {!a && !s.analysisErrors[d.decision_point_id] && (
          <button type="button" onClick={() => void actions.analyze(d.decision_point_id)} className="w-full rounded-lg bg-blue-600 py-2 text-sm font-bold text-white hover:bg-blue-500">{L.analyse}</button>
        )}
        {s.analysisErrors[d.decision_point_id] && <p className="text-sm text-red-300">{s.analysisErrors[d.decision_point_id]}</p>}
        {a && <StatusBadges a={a} />}
        {a && (running || s.mode !== "casual") && <AgentPipeline a={a} />}
        {running && <p className="text-sm text-amber-200" aria-live="polite">{L.analysing}…</p>}
        {a?.status === "unavailable" && <p className="rounded-lg bg-slate-800 p-2 text-sm text-slate-200">{L.unavailable}: {a.unavailable_reason}</p>}
        {a?.simulation && a.status !== "pending" && a.candidates.length > 0 && (
          <>
            {overall && (
              <div className={`rounded-lg px-3 py-2 text-sm font-semibold ${overall === "more_promising" ? "bg-blue-600/15 text-blue-200" : "bg-slate-800 text-slate-200"}`} data-testid="verdict">
                {L.verdict[overall]}
              </div>
            )}
            {s.mode === "casual" && <CasualCards a={a} res={res} comps={comps} />}
            {s.mode === "analyst" && (
              <>
                <ComparisonChart candidates={a.candidates} results={a.simulation.results} selected={s.selectedActionId} lang={s.lang} />
                <AnalystTable a={a} res={res} comps={comps} />
              </>
            )}
            {s.mode === "broadcaster" && (
              <>
                <CasualCards a={a} res={res} comps={comps} />
                <BroadcasterView a={a} overlays={s.overlays} />
              </>
            )}
          </>
        )}
        {n && s.mode !== "broadcaster" && (
          <article className="rounded-lg border border-line bg-slate-950/50 p-3" data-testid="narrative">
            <h3 className="text-sm font-bold text-white">{n.headline}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-200">{n.body}</p>
            {s.mode === "analyst" && n.bullets.length > 0 && (
              <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[11px] text-slate-300">
                {n.bullets.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            )}
            <div className="mt-2 text-[10px] text-slate-500">
              {n.is_live_model_output ? `Written by ${n.generated_by} (Microsoft Foundry), verified against the evidence table.` : `Generated by ${n.generated_by}; verified against the evidence table.`}
            </div>
          </article>
        )}
        {a && a.status === "verified" && <Evidence a={a} d={d} />}
        <button type="button" data-testid="explore-multiverse"
          onClick={() => { actions.setView("multiverse"); void mv.open(d.decision_point_id, d.match_id); }}
          className="w-full rounded-lg border border-blue-400/50 bg-blue-600/10 py-2 text-sm font-bold text-blue-100 hover:bg-blue-600/25">
          {s.lang === "en" ? "Explore this decision in the Multiverse →" : "Verken deze beslissing in het Multiverse →"}
        </button>
      </section>
      <WorkflowInspector />
      {a && !running && <RecoveryPanel />}
    </div>
  );
}


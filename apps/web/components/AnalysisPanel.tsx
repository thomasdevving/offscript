"use client";

import type { ActionResult, CounterfactualAnalysis, DecisionPoint, Language, Narrative, Overlay,
  PairwiseComparison } from "@offscript/contracts";
import { useEffect, useState } from "react";
import { clock, cleanLabel, pct, signedPp } from "@/lib/format";
import { eventLabel, t, triggerLabel } from "@/lib/i18n";
import { mv } from "@/lib/mvStore";
import { actions, selectedAnalysis, selectedDecision, useApp } from "@/lib/store";
import RecoveryPanel from "./RecoveryPanel";
import AgentActivity from "./AgentActivity";
import WorkflowInspector, { AgentPipeline } from "./WorkflowInspector";

function narrativeFor(a: CounterfactualAnalysis, mode: string, lang: Language): Narrative | undefined {
  return a.narratives.find((n) => n.audience === mode && n.language === lang);
}

function StatusBadges({ a }: { a: CounterfactualAnalysis }) {
  const s = useApp();
  const L = t(s.lang);
  const v = a.verification?.status;
  return (
    <div className="flex flex-wrap gap-1.5">
      {a.status === "verified" && <span className="chip bg-emerald-500/15 text-emerald-300" data-testid="verified-badge">✓ {L.verified}{v === "verified_with_warnings" ? " (warnings)" : ""}</span>}
      {a.status === "unavailable" && <span className="chip">{L.unavailable}</span>}
      {a.cached && s.mode === "analyst" && <span className="chip">{L.cached}</span>}
      {a.model.degraded && <span className="chip bg-amber-500/15 text-amber-300">{L.degraded}</span>}
      {s.mode === "analyst" && <span className="chip">
        {a.model.agent_mode === "foundry" ? `Foundry · ${a.model.deployment} · ${a.model.live_model_calls} live calls` : L.policy}
      </span>}
      {a.fault_injection.length > 0 && <span className="chip bg-red-500/15 text-red-300">fault: {a.fault_injection.join(", ")}</span>}
    </div>
  );
}

function DecisionHeader({ d }: { d: DecisionPoint }) {
  const s = useApp();
  const L = t(s.lang);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="num rounded-md bg-sage-500/15 px-1.5 py-0.5 font-mono text-xs font-semibold text-sage-200">{clock(d.match_clock_ms)}</span>
        <h2 className="truncate text-xl font-black tracking-tight text-white">{d.actor_name}</h2>
      </div>
      <div className="mt-1 text-sm text-slate-400">
        {cleanLabel(d.actual_action.label)} → <span className="font-semibold text-amber-300">{eventLabel(d.actual_outcome, s.lang)}</span>
        <span className="text-slate-500"> · {L.observedOutcome.toLowerCase()}</span>
      </div>
      {s.mode === "analyst" && <div className="mt-2 flex flex-wrap gap-1">
        {d.triggers.map((tr) => (
          <span key={tr} className="chip text-sage-200/90">{triggerLabel(tr, s.lang)}</span>
        ))}
      </div>}
    </div>
  );
}

/**
 * "Possible futures": every option is a branch growing from the same frozen moment. Branch length is
 * the modelled P(goal within horizon); analysts also see the 95% interval as a whisker.
 */
function PossibleFutures({ a, res, comps }: { a: CounterfactualAnalysis; res: Map<string, ActionResult>; comps: Map<string, PairwiseComparison> }) {
  const s = useApp();
  const L = t(s.lang);
  const H = a.simulation?.config.horizon_s ?? 10;
  const best = [...a.candidates].filter((c) => !c.is_actual)
    .sort((x, y) => (res.get(y.action_id)?.p_goal.value ?? 0) - (res.get(x.action_id)?.p_goal.value ?? 0))[0];
  const favoured = !!best && comps.get(best.action_id)?.verdict === "more_promising";
  const showCi = s.mode === "analyst";
  const max = Math.max(0.02, ...a.candidates.map((c) => {
    const r = res.get(c.action_id);
    return (showCi ? r?.p_goal.ci95_high : r?.p_goal.value) ?? 0;
  })) * 1.08;
  const ordered = [...a.candidates].sort((x, y) => Number(y.is_actual) - Number(x.is_actual));
  return (
    <div data-testid="casual-cards">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="eyebrow">{L.futures}</h3>
        <span className="text-[10px] text-slate-500" title={L.futuresHint}>{L.goalChance} {H}{L.seconds}</span>
      </div>
      <div className="relative pl-5">
        {/* The frozen decision moment every branch grows from. */}
        <span className="absolute bottom-7 left-[5px] top-7 w-px bg-gradient-to-b from-sage-400/80 via-sage-400/30 to-sage-400/80" aria-hidden />
        <ul className="space-y-1.5">
          {ordered.map((c, i) => {
            const r = res.get(c.action_id);
            const sel = s.selectedActionId === c.action_id;
            const isFav = favoured && best?.action_id === c.action_id;
            const w = r ? Math.max(1.5, (r.p_goal.value / max) * 100) : 0;
            const color = sel ? "#d4ee8f" : c.is_actual ? "#e2e8f0" : isFav ? "#8fca7c" : "#cfe2b4";
            return (
              <li key={c.action_id} className="relative animate-rise" style={{ animationDelay: `${i * 70}ms` }}>
                <svg className="absolute -left-5 top-0 h-full w-5 overflow-visible" aria-hidden>
                  <line x1={5.5} x2={20} y1="50%" y2="50%" stroke={color} strokeWidth={1.5} strokeDasharray={c.is_actual ? "3 2.5" : undefined} />
                  <circle cx={5.5} cy="50%" r={3} fill="#04060b" stroke={color} strokeWidth={1.5} />
                </svg>
                <button type="button" onClick={() => void actions.selectAction(c.action_id)}
                  className={`group w-full rounded-xl px-3 py-2.5 text-left transition ${sel ? "bg-leaf-500/15 ring-1 ring-leaf-400/60"
                    : isFav ? "bg-leaf-500/[0.07] ring-1 ring-leaf-400/25 hover:bg-leaf-500/10" : "bg-white/[0.03] hover:bg-white/[0.06]"}`}
                  data-testid={`option-${c.is_actual ? "actual" : "alt"}`}>
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                        {c.is_actual ? L.actual : L.alternative}{isFav && <span className="text-leaf-300"> · {L.modelFavours}</span>}
                      </div>
                      <div className="truncate text-[15px] font-bold text-white">{cleanLabel(c.label)}</div>
                    </div>
                    <div className="text-right">
                      <div className={`num font-mono text-2xl font-black leading-none ${isFav ? "text-leaf-300" : "text-white"}`}>{r ? pct(r.p_goal.value, s.lang) : "…"}</div>
                      <div className="mt-1 text-[10px] font-semibold text-slate-500 group-hover:text-leaf-300">{L.watch} ▸</div>
                    </div>
                  </div>
                  <div className="relative mt-2 h-1.5 rounded-full bg-white/[0.05]">
                    <span className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
                      style={{ width: `${w}%`, background: c.is_actual ? "repeating-linear-gradient(90deg,#e2e8f0 0 6px,transparent 6px 9px)" : `linear-gradient(90deg, ${color}55, ${color})` }} />
                    {showCi && r && (
                      <span className="absolute -top-[3px] h-3 border-x border-white/70" title="95% interval"
                        style={{ left: `${(r.p_goal.ci95_low / max) * 100}%`, width: `${Math.max(0.5, ((r.p_goal.ci95_high - r.p_goal.ci95_low) / max) * 100)}%` }}>
                        <span className="absolute inset-x-0 top-[5px] h-px bg-white/70" />
                      </span>
                    )}
                  </div>
                  {showCi && <div className="mt-1.5 text-[10px] text-slate-500">
                    {r?.n_rollouts ?? "-"} {L.simulations}
                    {r ? ` · ${L.shotChance.toLowerCase()} ${pct(r.p_shot.value, s.lang, 0)} · ${L.turnover.toLowerCase()} ${pct(r.p_turnover.value, s.lang, 0)}` : ""}
                  </div>}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {showCi && <p className="mt-2 text-[10px] leading-snug text-slate-500">{L.futuresHint}</p>}
    </div>
  );
}

function AnalystTable({ a, res, comps }: { a: CounterfactualAnalysis; res: Map<string, ActionResult>; comps: Map<string, PairwiseComparison> }) {
  const s = useApp();
  const L = t(s.lang);
  return (
    <div className="overflow-x-auto">
      <table className="num w-full text-left text-[11px]" data-testid="analyst-table">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500">
          <tr className="[&>th]:px-1 [&>th]:pb-1 [&>th]:font-semibold"><th className="pr-2">Option</th><th>P(goal) [95%]</th><th>{L.shotChance}</th><th>{L.turnover}</th><th>1st ok</th><th>{L.vsActual}</th></tr>
        </thead>
        <tbody>
          {a.candidates.map((c) => {
            const r = res.get(c.action_id);
            const cm = comps.get(c.action_id);
            if (!r) return null;
            return (
              <tr key={c.action_id} className={`border-t border-white/5 [&>td]:px-1 ${s.selectedActionId === c.action_id ? "bg-leaf-600/10" : ""}`}>
                <td className="py-1.5 pr-2">
                  <button type="button" onClick={() => void actions.selectAction(c.action_id)} className="text-left font-semibold text-white hover:text-leaf-300">
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
      <div className="mt-2 space-y-0.5 text-[10px] text-slate-400">
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
  const sim = a.simulation;
  const kv = "grid grid-cols-[1fr_auto] gap-x-3 gap-y-1";
  return (
    <section aria-label={L.evidence}>
      <h3 className="eyebrow mb-2">{L.evidence}</h3>
      <div className="space-y-4 text-[11px] text-slate-300" data-testid="evidence-panel">
        <div className={kv}>
          <span className="text-slate-500">Distance to goal</span><span className="num font-mono">{d.features.distance_to_goal_m.toFixed(1)} m</span>
          <span className="text-slate-500">Opponents within 5 m</span><span className="num font-mono">{d.features.pressure_count_5m}</span>
          <span className="text-slate-500">Nearest defender</span><span className="num font-mono">{d.features.nearest_defender_m.toFixed(1)} m</span>
          <span className="text-slate-500">Open teammates (model)</span><span className="num font-mono">{d.features.open_teammates}</span>
          {d.features.actual_shot_quality != null && (<><span className="text-slate-500">Shot itself (modeled)</span><span className="num font-mono">{pct(d.features.actual_shot_quality, s.lang)}</span></>)}
          {sim && (<>
            <span className="text-slate-500">{L.rollouts}</span><span className="num font-mono">{sim.config.rollouts}{sim.partial ? " (partial)" : ""}</span>
            <span className="text-slate-500">{L.horizon}</span><span className="num font-mono">{sim.config.horizon_s} s</span>
            <span className="text-slate-500">{L.seed}</span><span className="num font-mono">{sim.config.seed}</span>
            <span className="text-slate-500">{L.simulator}</span><span className="font-mono">{sim.simulator_version}</span>
            <span className="text-slate-500">Paired streams (CRN)</span><span className="font-mono">{String(sim.config.common_random_numbers)}</span>
            <span className="text-slate-500">Run time</span><span className="num font-mono">{sim.duration_ms?.toFixed(0)} ms</span>
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
        <div className="overflow-hidden rounded-xl shadow-lg">
          <div className="flex">
            <div className="flex items-center bg-gradient-to-b from-leaf-500 to-sage-600 px-2.5 text-[10px] font-black tracking-widest text-white">OFFSCRIPT</div>
            <div className="flex-1 bg-slate-950 px-3 py-2">
              <div className="text-sm font-extrabold uppercase text-white">{n.headline}</div>
              <div className="text-xs text-leaf-100" data-testid="caption">{n.caption}</div>
            </div>
          </div>
        </div>
      )}
      {ov && (
        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-white">{clock(ov.match_time_ms)}</div><div className="text-slate-500">start</div></div>
          <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-white">{(ov.duration_ms / 1000).toFixed(0)} s</div><div className="text-slate-500">{L.duration}</div></div>
          <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-white">{ov.priority}</div><div className="text-slate-500">{L.priority}</div></div>
        </div>
      )}
      {ov && <div className="text-[11px] text-slate-400">{L.expires}: {ov.expires.on_event_types.join(", ")} · max {(ov.expires.max_age_ms ?? 0) / 1000}s · {ov.verification_status}</div>}
      <div className="rounded-xl bg-black/40 ring-1 ring-white/5">
        <div className="flex items-center justify-between border-b border-white/5 px-3 py-1.5 text-[11px] text-slate-400">
          {L.overlayJson}
          <button type="button" className="btn px-2 py-0.5"
            onClick={() => { void navigator.clipboard?.writeText(json); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
            {copied ? L.copied : L.copy}
          </button>
        </div>
        <pre className="max-h-48 overflow-auto p-2 text-[10px] leading-snug text-emerald-200" data-testid="overlay-json">{json}</pre>
      </div>
    </div>
  );
}

type RailTab = "story" | "evidence" | "agents";

export default function AnalysisPanel() {
  const s = useApp();
  const L = t(s.lang);
  const d = selectedDecision(s);
  const a = selectedAnalysis(s);
  const [tab, setTab] = useState<RailTab>("story");
  // A recovery demo is about the agents: show their trace as soon as one starts.
  useEffect(() => {
    if (s.recovery) setTab("agents");
  }, [s.recovery]);
  if (!d) {
    return (
      <div className="glass p-5">
        <h2 className="eyebrow">{L.analysisTitle}</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-300">{L.noDecision}</p>
        <p className="mt-4 text-[11px] text-slate-500">{L.keyboard}</p>
      </div>
    );
  }
  const res = new Map((a?.simulation?.results ?? []).map((r) => [r.action_id, r]));
  const comps = new Map((a?.simulation?.comparisons ?? []).map((c) => [c.action_id, c]));
  const n = a ? narrativeFor(a, s.mode, s.lang) : undefined;
  const running = !!a && (a.status === "pending" || a.status === "running");
  const overall = a?.simulation?.overall_verdict;
  const tabs: { id: RailTab; label: string }[] = [
    { id: "story", label: L.story },
    { id: "evidence", label: s.lang === "en" ? "Evidence" : "Bewijs" },
    { id: "agents", label: L.agents },
  ];
  return (
    <div className="space-y-3">
      <section className="glass space-y-4 p-4" aria-label={L.analysisTitle} data-testid="analysis-panel">
        <div className="flex items-center justify-between">
          <h2 className="eyebrow">{L.analysisTitle}</h2>
          {s.recovery && (
            <button type="button" onClick={() => useApp.setState({ recovery: null, recoveryFault: null })} className="btn px-2 py-0.5 text-[11px]">
              ← {s.lang === "en" ? "main analysis" : "hoofdanalyse"}
            </button>
          )}
        </div>
        <DecisionHeader d={d} />
        {!a && !s.analysisErrors[d.decision_point_id] && (
          <button type="button" onClick={() => void actions.analyze(d.decision_point_id)} className="btn btn-primary w-full py-2.5 text-sm">{L.analyse}</button>
        )}
        {s.analysisErrors[d.decision_point_id] && <p className="text-sm text-red-300">{s.analysisErrors[d.decision_point_id]}</p>}
        {a && <StatusBadges a={a} />}
        {a && (running || s.mode !== "casual") && <AgentPipeline a={a} />}
        {running && a && <AgentActivity analysisId={a.analysis_id} />}
        {a?.status === "unavailable" && <p className="rounded-lg bg-white/5 p-2 text-sm text-slate-200">{L.unavailable}: {a.unavailable_reason}</p>}
        {a?.simulation && a.status !== "pending" && a.candidates.length > 0 && (
          <>
            {overall && (
              <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold ${overall === "more_promising" ? "bg-gradient-to-r from-leaf-600/25 to-sage-600/10 text-leaf-100" : "bg-white/[0.04] text-slate-200"}`} data-testid="verdict">
                <span className={`h-2 w-2 rounded-full ${overall === "more_promising" ? "bg-leaf-400 shadow-[0_0_10px] shadow-leaf-400" : "bg-slate-400"}`} />
                {L.verdict[overall]}
              </div>
            )}
            <PossibleFutures a={a} res={res} comps={comps} />
            {s.mode === "analyst" && <AnalystTable a={a} res={res} comps={comps} />}
            {s.mode === "broadcaster" && <BroadcasterView a={a} overlays={s.overlays} />}
          </>
        )}
        <button type="button" data-testid="explore-multiverse"
          onClick={() => { actions.setView("multiverse"); void mv.open(d.decision_point_id, d.match_id); }}
          className="notch w-full bg-gradient-to-r from-leaf-600 to-sage-600 py-2.5 text-sm font-bold tracking-wide text-white transition hover:brightness-110">
          {s.lang === "en" ? "Take the decision yourself in the Multiverse →" : "Neem de beslissing zelf in het Multiverse →"}
        </button>
      </section>
      {a && (
        <section className="glass p-3">
          <div role="tablist" aria-label={L.analysisTitle} className="mb-3 flex gap-0.5 rounded-xl bg-white/[0.03] p-0.5">
            {tabs.map((x) => (
              <button key={x.id} type="button" role="tab" aria-selected={tab === x.id} onClick={() => setTab(x.id)}
                className="tab flex-1" data-testid={`rail-tab-${x.id}`}>{x.label}</button>
            ))}
          </div>
          <div hidden={tab !== "story"} className="px-1">
            {n && s.mode !== "broadcaster" ? (
              <article data-testid="narrative">
                <h3 className="text-base font-bold text-white">{n.headline}</h3>
                <p className="mt-1.5 text-[14px] leading-relaxed text-slate-300">{n.body}</p>
                {s.mode === "analyst" && n.bullets.length > 0 && (
                  <ul className="mt-3 space-y-1 text-[11px] text-slate-400">
                    {n.bullets.map((b, i) => <li key={i} className="flex gap-2"><span className="text-sage-400">▸</span><span>{b}</span></li>)}
                  </ul>
                )}
                {s.mode === "analyst" && <div className="mt-3 text-[10px] text-slate-500">
                  {n.is_live_model_output ? `Written by ${n.generated_by} (Microsoft Foundry), verified against the evidence table.` : `Generated by ${n.generated_by}; verified against the evidence table.`}
                </div>}
              </article>
            ) : (
              <p className="text-sm text-slate-500">{running ? `${L.analysing}…` : s.mode === "broadcaster" ? (s.lang === "en" ? "The broadcast caption is shown above." : "Het omroepbijschrift staat hierboven.") : "-"}</p>
            )}
          </div>
          <div hidden={tab !== "evidence"} className="px-1">
            {a.status === "verified" ? <Evidence a={a} d={d} /> : <p className="text-sm text-slate-500">-</p>}
          </div>
          <div hidden={tab !== "agents"} className="space-y-3">
            <WorkflowInspector />
            {!running && <RecoveryPanel />}
          </div>
        </section>
      )}
    </div>
  );
}

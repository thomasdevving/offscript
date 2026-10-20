"use client";

import type { AgentStep, CounterfactualAnalysis } from "@parallel/contracts";
import { useState } from "react";
import { t } from "@/lib/i18n";
import { actions, selectedAnalysis, useApp } from "@/lib/store";

const AGENTS = [
  ["decision_agent", "Decision", "Decides if the moment deserves analysis"],
  ["strategy_agent", "Strategy", "Proposes feasible alternatives"],
  ["simulation_agent", "Simulation", "Runs Monte Carlo rollouts"],
  ["verification_agent", "Verification", "Checks numbers and claims"],
  ["explanation_agent", "Explanation", "Writes audience narratives"],
] as const;

function statusColor(st?: string): string {
  switch (st) {
    case "completed": return "bg-emerald-400";
    case "running": return "bg-amber-400 animate-pulse";
    case "degraded": return "bg-amber-400";
    case "rejected": return "bg-red-400";
    case "failed": return "bg-red-500";
    default: return "bg-slate-600";
  }
}

/** The agent relay: five nodes on one line; the baton (handoff) moves left to right, loops show as ×n. */
export function AgentPipeline({ a }: { a: CounterfactualAnalysis }) {
  const states = AGENTS.map(([id]) => {
    const steps = a.workflow.steps.filter((s) => s.agent === id);
    return { steps, last: steps[steps.length - 1] };
  });
  const done = states.filter((x) => x.last && x.last.status !== "running").length;
  const progress = Math.max(0, Math.min(1, (done - 1) / (AGENTS.length - 1)));
  return (
    <div className="relative px-2 pt-1" aria-label="Agent pipeline" data-testid="agent-pipeline">
      <div className="absolute left-[10%] right-[10%] top-[13px] h-px bg-white/10" aria-hidden />
      <div className="absolute left-[10%] top-[13px] h-px bg-gradient-to-r from-emerald-400 to-leaf-400 transition-all duration-700"
        style={{ width: `${progress * 80}%` }} aria-hidden />
      <ol className="relative grid grid-cols-5">
        {AGENTS.map(([id, name, role], i) => {
          const { steps, last } = states[i];
          return (
            <li key={id} className="flex flex-col items-center gap-1 text-center" title={last ? `${name}: ${last.status} (${last.model}) - ${role}` : `${name}: waiting - ${role}`}>
              <span className={`relative flex h-[18px] w-[18px] items-center justify-center rounded-full ring-4 ring-ink ${last ? "" : "bg-white/10"}`}>
                <span className={`h-[18px] w-[18px] rounded-full ${statusColor(last?.status)}`} />
                {steps.length > 1 && (
                  <span className="absolute -right-2.5 -top-2 rounded-full bg-amber-400 px-1 text-[8px] font-black text-amber-950">×{steps.length}</span>
                )}
              </span>
              <span className={`text-[10px] font-semibold ${last ? "text-slate-200" : "text-slate-500"}`}>{name}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StepCard({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(false);
  const meta = AGENTS.find((x) => x[0] === step.agent);
  return (
    <li className="rounded-xl bg-white/[0.03]">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left">
        <span className={`h-2 w-2 shrink-0 rounded-full ${statusColor(step.status)}`} />
        <span className="text-xs font-bold text-white">{meta?.[1] ?? step.agent} Agent</span>
        {step.attempt > 1 && <span className="rounded bg-slate-800 px-1 text-[10px] text-amber-300">attempt {step.attempt}</span>}
        <span className="truncate text-[10px] text-slate-400">{step.task}</span>
        <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-500">{step.duration_ms != null ? `${step.duration_ms.toFixed(0)} ms` : "…"}</span>
        <span className={`shrink-0 rounded px-1 text-[9px] font-semibold uppercase ${step.live_model ? "bg-leaf-500/20 text-leaf-200" : "bg-slate-800 text-slate-400"}`}>{step.model}</span>
        <span className="shrink-0 text-[10px] uppercase text-slate-400">{step.status}</span>
      </button>
      {step.handoff_to && (
        <div className="px-2.5 pb-1.5 text-[10px] text-sage-300">→ {step.handoff_to.replace("_agent", "")}: {step.handoff_reason}</div>
      )}
      {open && (
        <div className="space-y-2 border-t border-white/5 px-2.5 py-2 text-[10px]">
          {step.tool_calls.map((tc) => (
            <div key={tc.call_id} className="rounded-lg bg-black/30 p-1.5">
              <div className="flex gap-2 font-mono">
                <span className="text-emerald-300">{tc.tool_name}</span>
                <span className="text-slate-400">({JSON.stringify(tc.arguments)})</span>
                <span className="ml-auto text-slate-500">{tc.duration_ms.toFixed(1)} ms · {tc.status}</span>
              </div>
              <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all text-slate-300">{JSON.stringify(tc.result_summary, null, 1)?.slice(0, 1400)}</pre>
            </div>
          ))}
          {!step.tool_calls.length && <div className="text-slate-500">No tool calls.</div>}
          <div>
            <div className="font-semibold text-slate-300">Structured output</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all text-slate-400">{JSON.stringify(step.output, null, 1)}</pre>
          </div>
          {step.notes.map((n, i) => <div key={i} className="text-amber-300">• {n}</div>)}
        </div>
      )}
    </li>
  );
}

export default function WorkflowInspector() {
  const s = useApp();
  const L = t(s.lang);
  const a = selectedAnalysis(s);
  if (!a) return null;
  const wf = a.workflow;
  return (
    <section aria-label={L.workflow} data-testid="workflow-inspector">
      <button type="button" onClick={() => actions.toggleInspector()} aria-expanded={s.inspectorOpen}
        className="flex w-full items-center gap-2 px-1 py-1.5 text-left">
        <h2 className="eyebrow">{L.workflow}</h2>
        <span className="chip ml-auto uppercase" data-testid="workflow-status">
          {wf.workflow_status} · {a.status}
        </span>
        <span className="text-slate-500">{s.inspectorOpen ? "−" : "+"}</span>
      </button>
      {s.inspectorOpen && (
        <div className="space-y-2 pt-1">
          {s.recovery && (
            <div className="rounded-lg border border-red-400/30 bg-red-500/10 p-2 text-[11px] text-red-100">
              Controlled fault injection: <b>{s.recoveryFault}</b>. {L.recoveryHint}
            </div>
          )}
          <div className="grid grid-cols-3 gap-2 text-center text-[10px] text-slate-400">
            <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-sm text-white">{wf.steps.length}</div>agent runs</div>
            <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-sm text-white">{wf.steps.reduce((n, x) => n + x.tool_calls.length, 0)}</div>tool calls</div>
            <div className="rounded-lg bg-white/[0.04] p-1.5"><div className="num font-mono text-sm text-white">{wf.retry_count + wf.explanation_retries}</div>retries</div>
          </div>
          <ol className="space-y-1.5" data-testid="workflow-steps">
            {wf.steps.map((st) => <StepCard key={st.step_id} step={st} />)}
          </ol>
          {wf.rejected_candidates.length > 0 && (
            <div className="rounded-lg bg-black/30 p-2 text-[10px] text-slate-300">
              <div className="font-semibold text-red-300">Rejected proposals</div>
              {wf.rejected_candidates.map((r, i) => <div key={i}>• [{r.stage}] {r.reason}</div>)}
            </div>
          )}
          {wf.verification_issues.length > 0 && (
            <div className="rounded-lg bg-black/30 p-2 text-[10px] text-amber-200">
              {wf.verification_issues.slice(0, 6).map((v, i) => <div key={i}>• {v}</div>)}
            </div>
          )}
          <div className="text-[10px] text-slate-500">
            correlation {wf.correlation_id} · state v{wf.state_version} · {wf.handoffs.length} handoffs
          </div>
        </div>
      )}
    </section>
  );
}

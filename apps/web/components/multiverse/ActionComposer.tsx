"use client";

import type { CandidateAction, InteractionMode, MatchStateSnapshot, SampleKind } from "@offscript/contracts";
import { actionDirection } from "@/lib/pitchDirections";
import { mv, useMv, type ComposerType } from "@/lib/mvStore";

const MODES: { v: InteractionMode; label: string; hint: string }[] = [
  { v: "manual", label: "Manual", hint: "You choose every action; agents respond and evaluate but never override you." },
  { v: "assisted", label: "Assisted", hint: "The attacking agent recommends; you accept it or choose another action." },
  { v: "autonomous", label: "Autonomous", hint: "Agents play attack and defence until the depth limit or an outcome." },
];
const SAMPLES: { v: SampleKind; label: string }[] = [
  { v: "representative", label: "Representative" },
  { v: "high_upside", label: "High-upside" },
  { v: "defensive_success", label: "Defensive success" },
  { v: "random", label: "Random sample" },
];

function OptionRow({ action, snapshot, selected, recommended, actual, rank, busy }: {
  action: CandidateAction; snapshot?: MatchStateSnapshot; selected: boolean; recommended?: boolean;
  actual?: boolean; rank?: number; busy: boolean;
}) {
  const direction = snapshot ? actionDirection(action, snapshot) : null;
  const estimate = action.features.completion_estimate ?? action.features.success_estimate;
  return (
    <li>
      <button type="button" onClick={() => mv.chooseCandidate(action.action_id)} disabled={busy}
        onPointerEnter={() => mv.previewCandidate(action.action_id)} onPointerLeave={() => mv.previewCandidate(null)}
        onFocus={() => mv.previewCandidate(action.action_id)} onBlur={() => mv.previewCandidate(null)}
        aria-pressed={selected} data-testid={actual ? "actual-option" : "option"}
        className={`mv-option ${selected ? "is-selected" : ""}`}>
        <span className="mv-option-direction" aria-hidden="true">
          <svg viewBox="0 0 28 28"><g transform={`rotate(${direction?.angle ?? 0} 14 14)`}>
            <path d="M5 14h16m-6-6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </g></svg>
        </span>
        <span className="mv-option-copy">
          <span className="mv-option-title">{rank != null && <span className="mv-option-rank">{rank}</span>} {action.label.replace(" (actual)", "")}</span>
          <span className="mv-option-detail">{actual ? "Observed choice" : direction?.description ?? "Preview direction on the pitch"}
            {estimate != null && ` · ${Math.round(estimate * 100)}% ${action.action_type === "pass" ? "arrives" : "succeeds"}`}
          </span>
          {actual && <span className="mv-option-badge">ACTUAL</span>}
          {recommended && <span className="mv-option-badge">AI RECOMMENDED</span>}
        </span>
        <span className="mv-option-check" aria-hidden="true">{selected ? "✓" : ""}</span>
      </button>
    </li>
  );
}

export default function ActionComposer() {
  const s = useMv();
  const sel = s.selected;
  const node = sel ? s.nodes[sel] : null;
  const opts = sel ? s.options[sel] : null;
  const busy = !!s.job && ["pending", "running"].includes(s.job.status);
  const rec = node?.recommendation_planning_id ? s.plannings[node.recommendation_planning_id] : null;
  const recId = rec?.summary?.most_robust_action_id;
  const recLabel = rec?.attack_proposals.find((a) => a.action.action_id === recId)?.action.label;
  if (!node) return null;
  if (node.status !== "decision" || node.kind === "observed") {
    return (
      <div className="rounded-xl bg-white/[0.03] p-3 text-sm text-slate-300" data-testid="no-decision">
        {node.kind === "observed" ? "This is the canonical synthetic timeline: it cannot be changed. Rewind to the decision to branch." :
          node.status === "terminal" ? `This branch ended: ${node.outcome_label.replace(/_/g, " ")}. Rewind or pick another node.` :
            node.status === "depth_limit" ? "Maximum branch depth reached for this session." : `No decision available (${node.status}).`}
        {node.parent_node_id && (
          <button type="button" onClick={() => void mv.rewind()} className="mt-2 block rounded bg-white/[0.06] px-2 py-1 text-xs font-semibold hover:bg-white/10">
            ⟲ Rewind to decision
          </button>
        )}
      </div>
    );
  }
  const tool = (t: ComposerType, label: string, testId: string) => (
    <button type="button" onClick={() => mv.setComposer(s.composer.type === t ? null : t)} aria-pressed={s.composer.type === t}
      data-testid={testId}
      className={`rounded-md px-2 py-1.5 text-xs font-semibold ${s.composer.type === t ? "bg-leaf-600 text-white" : "bg-white/[0.06] text-slate-200 hover:bg-white/10"}`}>
      {label}
    </button>
  );
  const v = s.composer.validation;
  return (
    <section className="space-y-2" aria-label="Choose an action" data-testid="action-composer">
      <div role="radiogroup" aria-label="Interaction mode" className="flex rounded-lg bg-white/[0.04] p-0.5">
        {MODES.map((m) => (
          <button key={m.v} type="button" role="radio" aria-checked={s.interaction === m.v} title={m.hint}
            onClick={() => mv.setInteraction(m.v)} data-testid={`mode-${m.v}`}
            className={`flex-1 rounded-md px-2 py-1 text-xs font-semibold ${s.interaction === m.v ? "bg-slate-200 text-slate-900" : "text-slate-300"}`}>
            {m.label}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-slate-400">{MODES.find((m) => m.v === s.interaction)?.hint}</p>

      {s.interaction === "autonomous" ? (
        <button type="button" disabled={busy} onClick={() => void mv.autoPlay(3)} data-testid="autoplay"
          className="w-full rounded-lg bg-leaf-600 py-2 text-sm font-bold text-white hover:bg-leaf-500 disabled:opacity-50">
          ▶ Let the agents play it out
        </button>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            {tool("pass", "Pass to player", "tool-pass")}
            {tool("pass_space", "Pass into space", "tool-space")}
            {tool("dribble", "Dribble to point", "tool-dribble")}
            {tool("shoot", "Shoot", "tool-shoot")}
          </div>
          <p className="text-[11px] text-slate-500">
            {s.composer.type === "pass" ? "Click a highlighted teammate on the pitch." :
              s.composer.type === "pass_space" || s.composer.type === "dribble" ? "Click a point on the pitch." :
                "Pick a tool, or one of the generated options below."}
          </p>
          <ul className="mv-options" data-testid="option-list">
            {opts?.actual && (
              <OptionRow action={opts.actual} snapshot={s.states[node.node_id]} actual busy={busy}
                selected={s.composer.candidateId === opts.actual.action_id} />
            )}
            {opts?.options.map((o, i) => (
              <OptionRow key={o.action_id} action={o} snapshot={s.states[node.node_id]} rank={i + 1} busy={busy}
                selected={s.composer.candidateId === o.action_id} recommended={o.action_id === recId} />
            ))}
          </ul>
          {v && (
            <div className={`rounded px-2 py-1 text-xs ${v.ok ? "bg-emerald-500/10 text-emerald-200" : "bg-red-500/10 text-red-200"}`} role="status" data-testid="validation">
              {v.ok ? `✓ ${v.action?.label} is feasible` : `✗ ${v.code}: ${v.message}`}
            </div>
          )}
          <button type="button" disabled={!v?.ok || busy} onClick={() => void mv.submit()} data-testid="submit-action"
            className="notch w-full bg-leaf-600 py-2 text-sm font-bold tracking-wide text-white hover:bg-leaf-500 disabled:opacity-40">
            {busy ? "Agents planning…" : "Simulate this branch"}
          </button>
          {s.interaction === "assisted" && (
            <div className="space-y-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2">
              <button type="button" disabled={busy} onClick={() => void mv.recommend()} data-testid="recommend"
                className="w-full rounded-md bg-emerald-600/80 py-1.5 text-xs font-bold text-white hover:bg-emerald-600 disabled:opacity-50">
                Ask the attacking agent for a recommendation
              </button>
              {recLabel && (
                <div className="flex items-center gap-2 text-xs text-emerald-100">
                  <span>AI recommends <b>{recLabel.replace(" (actual)", "")}</b> (most robust)</span>
                  <button type="button" disabled={busy} onClick={() => void mv.acceptRecommendation()} data-testid="accept-recommendation"
                    className="ml-auto rounded bg-emerald-500 px-2 py-1 font-bold text-emerald-950 disabled:opacity-50">Accept</button>
                </div>
              )}
            </div>
          )}
        </>
      )}
      <label className="flex items-center gap-2 text-[11px] text-slate-400">
        Continuation shown:
        <select value={s.sampleKind} onChange={(e) => mv.setSampleKind(e.target.value as SampleKind)}
          className="rounded border border-white/10 bg-white/[0.04] px-1 py-0.5 text-slate-200" data-testid="sample-kind">
          {SAMPLES.map((x) => <option key={x.v} value={x.v}>{x.label}</option>)}
        </select>
      </label>
      {busy && (
        <div className="flex items-center gap-2 text-xs text-leaf-200" aria-live="polite">
          <span className="h-2 w-2 animate-pulse rounded-full bg-leaf-400" /> {s.job?.progress[s.job.progress.length - 1] ?? "Starting…"}
          <button type="button" onClick={() => void mv.cancel()} className="ml-auto rounded bg-white/[0.06] px-2 py-0.5">Cancel</button>
        </div>
      )}
    </section>
  );
}

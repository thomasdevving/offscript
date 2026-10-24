"use client";

import type { CounterfactualAnalysis, FaultInjection } from "@offscript/contracts";
import { plainCheckIssue } from "@/lib/format";

export interface StressStory {
  broke: string;
  caught: string;
  fixed: string;
  ok: boolean;
}

/**
 * The stress test as a three-step story, built only from the recovered analysis' own trace:
 * what was sabotaged, how the agents caught it, and what was published in the end.
 */
export function stressStory(a: CounterfactualAnalysis, fault: FaultInjection): StressStory {
  const wf = a.workflow;
  const ok = a.status === "verified";
  const result = ok ? `Result: verified${a.model.degraded ? " (degraded)" : ""}; the real analysis was never touched.`
    : `Result: ${a.status}; the real analysis was never touched.`;
  if (fault === "invalid_candidate") {
    const rej = wf.rejected_candidates[0];
    const again = wf.steps.filter((s) => s.agent === "strategy_agent").length > 1;
    return {
      broke: "We slipped an impossible option into the Strategy agent's proposal: a pass to a substitute who is not on the pitch.",
      caught: rej ? `Validation rejected it: ${plainCheckIssue(rej.reason)}.` : "Validation rejected the impossible option.",
      fixed: `${again ? "The Strategy agent proposed again, and the analysis continued with feasible options only. " : ""}${result}`,
      ok,
    };
  }
  if (fault === "contradictory_claim") {
    const issue = wf.verification_issues.find((i) => /unsupported|percentage|number/i.test(i)) ?? wf.verification_issues[0];
    const templated = a.narratives.some((n) => n.generated_by.includes("fallback after rejected"));
    return {
      broke: "We inserted a probability into the story that the simulation never produced.",
      caught: issue ? `The Verification agent checked every number against the evidence and rejected it: ${plainCheckIssue(issue)}.`
        : "The Verification agent checked every number against the evidence and rejected the story.",
      fixed: `${wf.explanation_retries > 0 ? "The Explanation agent rewrote the story. "
        : templated ? "The rejected story was replaced by a verified one; the false number never reached the screen. " : ""}${result}`,
      ok,
    };
  }
  if (fault === "model_unavailable") {
    const failed = wf.steps.filter((s) => s.notes.some((n) => /failed|outage/i.test(n))).length;
    return {
      broke: "We made every call to the AI model fail, as if Microsoft Foundry were down.",
      caught: `Every agent noticed the outage (${failed} of ${wf.steps.length} agent runs).`,
      fixed: `Each agent fell back to the labelled deterministic planner, so every figure is still simulated and verified. ${result}`,
      ok,
    };
  }
  const reruns = wf.steps.filter((s) => s.agent === "simulation_agent").length;
  return {
    broke: "We cut the first simulation run short, so the options had unequal, incomplete samples.",
    caught: "The agents detected the partial result instead of publishing it.",
    fixed: `${reruns > 1 ? `The Simulation agent ran it again (${reruns} runs). ` : ""}${result}`,
    ok,
  };
}

export default function StressTestStory({ a, fault }: { a: CounterfactualAnalysis; fault: FaultInjection }) {
  const running = a.status === "pending" || a.status === "running";
  const st = stressStory(a, fault);
  const steps: [string, string][] = running
    ? [["What we broke", st.broke], ["How it is caught", "The agents are working on the sabotaged copy…"]]
    : [["What we broke", st.broke], ["How it was caught", st.caught], ["Result", st.fixed]];
  return (
    <ol className="space-y-1.5 rounded-xl bg-amber-500/[0.06] p-2.5 ring-1 ring-amber-400/30" data-testid="stress-story">
      {steps.map(([title, text], i) => (
        <li key={title} className="flex gap-2 text-[11px]">
          <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-black ${
            i === 0 ? "bg-amber-400 text-amber-950" : i === 2 && st.ok ? "bg-leaf-400 text-leaf-950" : "bg-white/15 text-white"}`}>{i + 1}</span>
          <span><b className="text-white">{title}.</b> <span className="text-slate-300">{text}</span></span>
        </li>
      ))}
    </ol>
  );
}

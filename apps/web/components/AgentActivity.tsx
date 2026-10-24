"use client";

import { useEffect, useState } from "react";
import { type ProgressItem, useApp } from "@/lib/store";

const NAMES: Record<string, string> = {
  decision_agent: "Decision agent", strategy_agent: "Strategy agent", simulation_agent: "Simulation agent",
  verification_agent: "Verification agent", explanation_agent: "Explanation agent",
  attacking_agent: "Attacking agent", defending_agent: "Defending agent",
};
export const agentName = (a?: string) => (a ? NAMES[a] ?? a.replace(/_/g, " ") : "Agent");

interface Row {
  key: string;
  kind: "agent" | "tool" | "handoff";
  text: string;
  sub?: string;
  done?: boolean;
  failed?: boolean;
}

/** Turns the raw progress stream into a readable running log: one row per agent run, its tool calls and handoffs. */
export function activityRows(items: ProgressItem[]): Row[] {
  const rows: Row[] = [];
  items.forEach((it, i) => {
    if (it.event === "agent_started") {
      rows.push({ key: `a${i}`, kind: "agent", text: agentName(it.agent), sub: it.task + (it.attempt && it.attempt > 1 ? ` (attempt ${it.attempt})` : "") });
    } else if (it.event === "agent_completed") {
      for (let j = rows.length - 1; j >= 0; j--) {
        if (rows[j].kind === "agent" && rows[j].text === agentName(it.agent) && !rows[j].done) {
          rows[j].done = true;
          rows[j].failed = it.status === "failed";
          break;
        }
      }
    } else if (it.event === "tool_call") {
      rows.push({ key: `t${i}`, kind: "tool", text: it.tool ?? "tool", failed: it.status === "error" });
    } else if (it.event === "handoff" && it.to) {
      rows.push({ key: `h${i}`, kind: "handoff", text: agentName(it.to), sub: it.reason });
    }
  });
  return rows;
}

export function useElapsed(since: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!since) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [since]);
  return since ? Math.max(0, Math.round((now - since) / 1000)) : 0;
}

/** Live log while the agents work on an analysis, so a 30-60 s live-model run never looks frozen. */
export default function AgentActivity({ analysisId }: { analysisId: string }) {
  const items = useApp((s) => s.progress[analysisId]) ?? [];
  const live = useApp((s) => s.health?.agent_mode === "foundry");
  const model = useApp((s) => s.health?.foundry_deployment);
  const since = items[0]?.at ?? null;
  const elapsed = useElapsed(since ?? Date.now());
  const rows = activityRows(items).slice(-7);
  return (
    <section className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-leaf-400/20" aria-live="polite" data-testid="agent-activity">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-leaf-400" />
        <span className="font-semibold text-white">Agents at work</span>
        <span className="num ml-auto font-mono text-slate-400">{elapsed} s</span>
      </div>
      <p className="mt-0.5 text-[10px] text-slate-500">
        {live ? `Live model: Microsoft Foundry · ${model ?? ""}. A full run usually takes 30-60 s.` : "Deterministic planner: a few seconds."}
      </p>
      <ol className="mt-2 space-y-1 text-[11px]">
        {rows.map((r, i) => {
          const current = i === rows.length - 1 && r.kind === "agent" && !r.done;
          return (
            <li key={r.key} className={`flex items-start gap-2 animate-rise ${r.kind === "agent" ? "" : "pl-4 text-slate-400"}`}>
              {r.kind === "agent" && (
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${r.failed ? "bg-amber-400" : r.done ? "bg-leaf-400" : "animate-pulse bg-white"}`} />
              )}
              {r.kind === "tool" && <span className="font-mono text-[10px] text-leaf-300">↳ {r.text}</span>}
              {r.kind === "handoff" && <span className="text-[10px]">→ {r.text}{r.sub ? `: ${r.sub}` : ""}</span>}
              {r.kind === "agent" && (
                <span className={current ? "text-white" : "text-slate-300"}>
                  <b>{r.text}</b>{r.sub ? <span className="text-slate-500"> · {r.sub}</span> : null}
                  {r.failed && <span className="text-amber-300"> · fell back to the planner</span>}
                </span>
              )}
            </li>
          );
        })}
        {!rows.length && <li className="text-slate-500">Starting the workflow…</li>}
      </ol>
    </section>
  );
}

"use client";

import { agentName, useElapsed } from "@/components/AgentActivity";
import type { LiveItem } from "@/lib/mvStore";
import { useMv } from "@/lib/mvStore";
import { useApp } from "@/lib/store";

interface Cell { action: string; strategy: string; xg: number; cached: boolean }

/** Folds the live progress stream into rounds, proposals and the response-matrix cells simulated so far. */
export function planningState(live: LiveItem[]) {
  const rounds = new Map<number, { attack: string[]; defence: string[]; revised: boolean }>();
  const cells = new Map<string, Cell>();
  let agent: string | undefined;
  let task: string | undefined;
  for (const it of live) {
    const d = (it.data ?? {}) as Record<string, unknown>;
    if (it.event === "agent_started") {
      agent = d.agent as string;
      task = d.task as string;
    } else if (it.event === "attack_proposals") {
      const r = Number(d.round ?? 1);
      const cur = rounds.get(r) ?? { attack: [], defence: [], revised: false };
      rounds.set(r, { ...cur, attack: (d.actions as string[]) ?? [], revised: !!d.revised });
    } else if (it.event === "defense_proposals") {
      const r = Number(d.round ?? 1);
      const cur = rounds.get(r) ?? { attack: [], defence: [], revised: false };
      rounds.set(r, { ...cur, defence: (d.strategies as string[]) ?? [] });
    } else if (it.event === "cell") {
      const c = { action: String(d.action), strategy: String(d.strategy), xg: Number(d.xg ?? 0), cached: !!d.cached };
      cells.set(`${c.action}|${c.strategy}`, c);
    }
  }
  const actions = [...new Set([...cells.values()].map((c) => c.action))];
  const strategies = [...new Set([...cells.values()].map((c) => c.strategy))];
  return { rounds: [...rounds.entries()].sort((a, b) => a[0] - b[0]), cells, actions, strategies, agent, task };
}

/** What the attacking and defending agents are doing right now, while a Multiverse branch is planned. */
export default function LivePlanning() {
  const live = useMv((s) => s.live);
  const job = useMv((s) => s.job);
  const foundry = useApp((s) => s.health?.agent_mode === "foundry");
  const since = live[0]?.at ?? null;
  const elapsed = useElapsed(since ?? Date.now());
  const st = planningState(live);
  const max = Math.max(0.0001, ...[...st.cells.values()].map((c) => c.xg));
  return (
    <section className="glass space-y-3 p-3" aria-live="polite" data-testid="mv-live">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-leaf-400" />
        <h2 className="eyebrow !text-leaf-300">Agents planning</h2>
        <span className="num ml-auto font-mono text-slate-400">{elapsed} s</span>
      </div>
      <p className="text-[11px] text-slate-300">
        {st.agent ? <><b className="text-white">{agentName(st.agent)}</b>{st.task ? ` · ${st.task}` : ""}</> : job?.progress.at(-1) ?? "Starting…"}
      </p>
      <ol className="space-y-1.5 text-[11px]">
        {st.rounds.map(([r, v]) => (
          <li key={r} className="animate-rise rounded-lg bg-white/[0.03] p-2">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">Round {r}{v.revised ? " · attack revised" : ""}</div>
            <div className="grid grid-cols-2 gap-2">
              <div><span className="font-semibold text-sky-300">Attack</span>{v.attack.map((a) => <div key={a} className="text-slate-200">+ {a}</div>)}</div>
              <div><span className="font-semibold text-orange-300">Defence</span>{v.defence.length ? v.defence.map((d) => <div key={d} className="text-slate-200">+ {d}</div>)
                : <div className="text-slate-500">thinking…</div>}</div>
            </div>
          </li>
        ))}
      </ol>
      {st.cells.size > 0 && (
        <div>
          <div className="mb-1 text-[10px] text-slate-500">Response matrix, filling as each pair is simulated ({st.cells.size} so far)</div>
          <table className="num w-full border-separate border-spacing-0.5 text-[10px]" data-testid="mv-live-matrix">
            <tbody>
              {st.actions.map((a) => (
                <tr key={a}>
                  <td className="max-w-24 truncate pr-1 text-slate-300">{a}</td>
                  {st.strategies.map((s) => {
                    const c = st.cells.get(`${a}|${s}`);
                    const k = c ? Math.min(1, c.xg / max) : 0;
                    return (
                      <td key={s} title={`${a} vs ${s}`} className="animate-pop rounded px-1 py-0.5 text-center font-mono text-white"
                        style={{ background: c ? `rgba(95,156,94,${0.18 + 0.6 * k})` : "rgba(255,255,255,0.04)" }}>
                        {c ? `${(c.xg * 100).toFixed(1)}%` : "·"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[10px] text-slate-500">
        {foundry ? "Live agents on Microsoft Foundry: a branch usually takes about a minute." : "Deterministic planner: a few seconds."} Every number comes from the simulator.
      </p>
    </section>
  );
}

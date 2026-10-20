"use client";

import type { MatchStateSnapshot, TrackingFrame } from "@parallel/contracts";
import { useEffect, useMemo, useRef } from "react";
import { interpolate, type RenderFrame } from "@/lib/frames";
import { clock, pct } from "@/lib/format";
import { mv, useMv } from "@/lib/mvStore";
import { selectedDecision, useApp } from "@/lib/store";
import Pitch, { type Arrow } from "../Pitch";
import ActionComposer from "./ActionComposer";
import AgentBattle, { PlanningSteps } from "./AgentBattle";
import CompareModal from "./CompareModal";
import DecisionTree from "./DecisionTree";

function useRaf(cb: (dt: number) => void, active: boolean) {
  const ref = useRef(cb);
  ref.current = cb;
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      ref.current((now - last) / 1000);
      last = now;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);
}

function snapFrame(s: MatchStateSnapshot): RenderFrame {
  const players: Record<string, [number, number]> = {};
  for (const p of s.players) players[p.player_id] = [p.x, p.y];
  return { t_ms: 0, ball: [s.ball.x, s.ball.y, 0], players, possessor_id: s.ball.possessor_id ?? null };
}

function goalOf(s: MatchStateSnapshot): [number, number] {
  return s.attack_direction[s.possession_team_id] === 1 ? [105, 34] : [0, 34];
}

function Stage() {
  const st = useMv();
  const match = useApp((s) => s.match);
  const node = st.selected ? st.nodes[st.selected] : null;
  const snap = st.selected ? st.states[st.selected] : null;
  const path = st.path;
  useRaf((dt) => {
    const s = useMv.getState();
    if (!s.path || !s.playing) return;
    const nt = Math.min(s.path.duration_ms, s.playT + dt * 1000);
    mv.setPlay({ playT: nt, playing: nt < s.path.duration_ms });
  }, st.playing);
  const frame = useMemo<RenderFrame | null>(() => {
    if (path && path.frames.length > 1) return interpolate(path.frames as unknown as TrackingFrame[], st.playT);
    return snap ? snapFrame(snap) : null;
  }, [path, st.playT, snap]);
  if (!match || !node) return <div className="flex aspect-[111/74] items-center justify-center rounded-xl bg-panel text-slate-400">Loading…</div>;

  const atEnd = !path || st.playT >= path.duration_ms - 1;
  const arrows: Arrow[] = [];
  const carrier = snap?.players.find((p) => p.player_id === snap.ball.possessor_id);
  if (atEnd && snap && carrier && node.status === "decision") {
    const c = st.composer;
    const a = c.validation?.ok ? c.validation.action : null;
    if (a) {
      const to: [number, number] = a.action_type === "shoot" ? goalOf(snap) : [a.target_x ?? carrier.x, a.target_y ?? carrier.y];
      arrows.push({ id: "composer", from: [carrier.x, carrier.y], to, kind: "selected", label: a.label });
    }
    const recP = node.recommendation_planning_id ? st.plannings[node.recommendation_planning_id] : null;
    const rec = recP?.attack_proposals.find((x) => x.action.action_id === recP.summary?.most_robust_action_id)?.action;
    if (rec && rec.action_id !== a?.action_id) {
      const to: [number, number] = rec.action_type === "shoot" ? goalOf(snap) : [rec.target_x ?? carrier.x, rec.target_y ?? carrier.y];
      arrows.push({ id: "rec", from: [carrier.x, carrier.y], to, kind: "recommended", label: `AI: ${rec.label}` });
    }
    const actual = st.options[node.node_id]?.actual;
    if (actual && actual.action_id !== a?.action_id) {
      arrows.push({ id: "actual", from: [carrier.x, carrier.y], to: actual.action_type === "shoot" ? goalOf(snap) : [actual.target_x ?? carrier.x, actual.target_y ?? carrier.y], kind: "actual", label: "Actual" });
    }
  }
  // Defensive response arrows for the step that produced this node (defender -> post at step start).
  if (node.entering_strategy && path && path.boundaries.length) {
    const startT = path.boundaries.length > 1 ? path.boundaries[path.boundaries.length - 2].t_ms : 0;
    const f0 = interpolate(path.frames as unknown as TrackingFrame[], startT);
    if (f0) {
      for (const asg of node.entering_strategy.assignments) {
        const d = f0.players[asg.defender_id];
        if (!d) continue;
        const target = asg.role === "press" ? [f0.ball[0], f0.ball[1]] : asg.target_player_id ? f0.players[asg.target_player_id] : null;
        if (!target) continue;
        const to: [number, number] = asg.role === "cover_lane" ? [f0.ball[0] + (target[0] - f0.ball[0]) * 0.55, f0.ball[1] + (target[1] - f0.ball[1]) * 0.55] : [target[0], target[1]];
        arrows.push({ id: `def-${asg.defender_id}`, from: [d[0], d[1]], to, kind: "defense", label: asg.role.replace("_", " ") });
      }
    }
  }
  const selectable = st.composer.type === "pass" && snap && atEnd
    ? snap.players.filter((p) => p.team_id === snap.possession_team_id && p.player_id !== snap.ball.possessor_id).map((p) => p.player_id) : undefined;
  const marker = st.composer.point ? { x: st.composer.point[0], y: st.composer.point[1], ok: !!st.composer.validation?.ok } : null;
  const simulated = node.kind === "simulated" || (path?.simulated ?? false);
  return (
    <div className="relative">
      <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
        <span className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wider ${node.kind === "observed" ? "border border-white/20 bg-slate-900/80 text-slate-100" : simulated ? "bg-blue-600/90 text-white" : "bg-violet-600/90 text-white"}`} data-testid="mv-banner">
          {node.kind === "observed" ? "Canonical synthetic timeline" : node.kind === "root" ? "Frozen decision state" : `Simulated branch · depth ${node.depth}`}
        </span>
        {node.transition && node.kind !== "observed" && (
          <span className="rounded-md bg-slate-950/80 px-2 py-1 text-xs text-blue-200">{node.transition.sample_kind.replace("_", " ")} sample · rollout #{node.transition.rollout_index} · not a certainty</span>
        )}
      </div>
      <Pitch match={match} frame={frame} arrows={arrows} highlightId={snap?.ball.possessor_id ?? null}
        tint={node.kind === "observed" ? "observed" : simulated ? "simulated" : "snapshot"}
        selectableIds={selectable} onPlayerClick={(id) => void mv.playerClicked(id)}
        onPitchClick={st.composer.type === "dribble" || st.composer.type === "pass_space" ? (x, y) => void mv.pitchClicked(x, y) : undefined}
        marker={marker} ariaLabel="Multiverse pitch" />
    </div>
  );
}

function PlayBar() {
  const st = useMv();
  const path = st.path;
  if (!path || path.duration_ms <= 0) return null;
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2">
      <button type="button" onClick={() => mv.setPlay({ playing: !st.playing, playT: st.playT >= path.duration_ms ? 0 : st.playT })}
        className="h-8 w-8 rounded-md bg-blue-600 text-sm font-bold text-white" aria-label={st.playing ? "Pause" : "Play branch"}>{st.playing ? "❚❚" : "▶"}</button>
      <button type="button" onClick={() => mv.setPlay({ playT: 0, playing: true })} className="h-8 w-8 rounded-md bg-slate-800 text-sm" aria-label="Replay branch from the decision">↺</button>
      <div className="relative flex-1">
        <input type="range" min={0} max={path.duration_ms} step={50} value={st.playT} aria-label="Scrub branch"
          onChange={(e) => mv.setPlay({ playT: Number(e.target.value), playing: false })} className="timeline w-full" />
        {path.boundaries.map((b) => (
          <span key={b.node_id} className="absolute -top-1 h-3 w-0.5 bg-violet-400" style={{ left: `${(b.t_ms / path.duration_ms) * 100}%` }} title={b.label} />
        ))}
      </div>
      <span className="font-mono text-xs text-slate-300">+{(st.playT / 1000).toFixed(1)}s</span>
    </div>
  );
}

export default function MultiverseView() {
  const st = useMv();
  const app = useApp();
  const decision = selectedDecision(app);
  const node = st.selected ? st.nodes[st.selected] : null;
  const planning = node?.planning_id ? st.plannings[node.planning_id] : null;
  const recPlanning = node?.recommendation_planning_id ? st.plannings[node.recommendation_planning_id] : null;
  const shownPlanning = planning ?? recPlanning;
  const narrative = shownPlanning?.narratives.find((n) => n.audience === app.mode && n.language === app.lang);
  const siblings = st.tree?.nodes.filter((n) => n.parent_node_id === node?.parent_node_id && n.node_id !== node?.node_id) ?? [];

  if (!st.session) {
    return (
      <div className="mx-auto max-w-2xl space-y-3 p-6" data-testid="mv-start">
        <h1 className="text-2xl font-black text-white">Football Multiverse</h1>
        <p className="text-sm text-slate-300">Pick a decision from the current match, then explore different futures: choose actions, let attacking and
          defending agents compete, rewind, fork and compare. Every branch is a simulation under an explicit model of a synthetic match.</p>
        <ul className="space-y-1">
          {app.decisions.map((d) => (
            <li key={d.decision_point_id}>
              <button type="button" disabled={st.starting} onClick={() => void mv.open(d.decision_point_id, d.match_id)} data-testid="mv-open-decision"
                className="flex w-full items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2 text-left hover:border-blue-400/60">
                <span className="font-mono text-xs text-blue-300">{clock(d.match_clock_ms)}</span>
                <span className="font-semibold text-white">{d.actor_name}</span>
                <span className="text-xs text-slate-400">{d.actual_action.label.replace(" (actual)", "")} → {d.actual_outcome.replace(/_/g, " ").toLowerCase()}</span>
                {decision?.decision_point_id === d.decision_point_id && <span className="ml-auto text-[10px] text-blue-300">selected</span>}
              </button>
            </li>
          ))}
        </ul>
        {st.error && <p className="text-sm text-red-300">{st.error}</p>}
      </div>
    );
  }

  return (
    <div className="grid flex-1 gap-3 p-3 xl:grid-cols-[340px_minmax(0,1fr)_440px]" data-testid="multiverse-view">
      <aside className="order-3 min-w-0 space-y-3 xl:order-1">
        <section className="rounded-xl border border-line bg-panel p-3">
          <div className="mb-2 flex items-center gap-2">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Multiverse timeline</h2>
            <button type="button" onClick={() => void mv.newSession()} className="ml-auto rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700">New session</button>
            <button type="button" onClick={() => mv.close()} className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700">Close</button>
          </div>
          <DecisionTree />
          <p className="mt-2 text-[10px] text-slate-500">White dashed = canonical synthetic timeline (never changed). Blue = selected. Amber = terminal outcome. % = modelled expected goals vs the defence&apos;s best counter.</p>
        </section>
        {node && (
          <section className="space-y-2 rounded-xl border border-line bg-panel p-3 text-xs">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Branch controls</h2>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" disabled={!node.parent_node_id} onClick={() => void mv.rewind()} data-testid="rewind"
                className="rounded bg-slate-800 px-2 py-1 font-semibold hover:bg-slate-700 disabled:opacity-40">⟲ Rewind to decision</button>
              <button type="button" disabled={!node.parent_node_id} onClick={() => node.parent_node_id && void mv.select(node.parent_node_id)} data-testid="fork"
                className="rounded bg-slate-800 px-2 py-1 font-semibold hover:bg-slate-700 disabled:opacity-40">⑂ Create another branch</button>
              <button type="button" onClick={() => void mv.select(st.session!.root_node_id)} className="rounded bg-slate-800 px-2 py-1 font-semibold hover:bg-slate-700">Root decision</button>
            </div>
            {node.kind !== "root" && (
              <div className="space-y-1">
                <div className="text-slate-400">Compare this branch with:</div>
                <div className="flex flex-wrap gap-1">
                  {[...siblings, ...(st.tree?.nodes.filter((n) => n.kind === "observed" && n.node_id !== node.node_id && !siblings.includes(n)) ?? [])]
                    .slice(0, 6).map((n) => (
                      <button key={n.node_id} type="button" onClick={() => void mv.openCompare(node.node_id, n.node_id, app.lang)} data-testid="compare-with"
                        className="rounded border border-line px-2 py-0.5 hover:border-blue-400">{n.kind === "observed" ? "Actual" : n.label}</button>
                    ))}
                </div>
              </div>
            )}
          </section>
        )}
      </aside>
      <section className="order-1 min-w-0 space-y-3 xl:order-2">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h1 className="text-xl font-black text-white">Football Multiverse</h1>
          <p className="text-sm text-slate-400">{node ? `${clock(node.match_clock_ms)} · ${node.label}${node.outcome_label ? ` → ${node.outcome_label.replace(/_/g, " ")}` : ""}` : ""}</p>
        </div>
        <div className="overflow-hidden rounded-2xl border border-line bg-panel p-2"><Stage /></div>
        <PlayBar />
        {st.error && <p className="rounded bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">{st.error}</p>}
        <p className="text-[11px] text-slate-500">Branches are modelled futures of a synthetic match: each shows one sampled continuation, with probabilities from paired Monte Carlo simulation. Rewinding restores the exact stored state; nothing is re-simulated.</p>
      </section>
      <aside className="order-2 min-w-0 space-y-3 xl:order-3">
        <section className="rounded-xl border border-line bg-panel p-3">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-400">Decision intelligence</h2>
          <ActionComposer />
        </section>
        {shownPlanning && (
          <section className="space-y-3 rounded-xl border border-line bg-panel p-3">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">{planning ? "Attack vs defence (this step)" : "Agent recommendation"}</h2>
            {narrative && (
              <article className="rounded-lg border border-line bg-slate-950/50 p-2" data-testid="mv-narrative">
                <h3 className="text-sm font-bold text-white">{narrative.headline}</h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-200">{app.mode === "broadcaster" ? narrative.caption ?? narrative.body : narrative.body}</p>
                {app.mode === "analyst" && <ul className="mt-1 list-disc pl-4 text-[11px] text-slate-300">{narrative.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
              </article>
            )}
            {app.mode === "casual" && shownPlanning.summary ? (
              <div className="text-xs text-slate-300">Selected option vs the defence&apos;s best answer: <b className="text-white">{pct(shownPlanning.summary.selected_value_vs_counter, app.lang)}</b> modelled goal chance within 10 s (vs {pct(shownPlanning.summary.selected_value_vs_baseline, app.lang)} against a balanced shape).</div>
            ) : (
              <AgentBattle p={shownPlanning} />
            )}
            {app.mode !== "casual" && (
              <details className="rounded-lg border border-line bg-slate-950/40 p-2 text-xs" data-testid="mv-inspector">
                <summary className="cursor-pointer font-semibold text-slate-200">Agent workflow inspector</summary>
                <div className="mt-2"><PlanningSteps p={shownPlanning} /></div>
              </details>
            )}
          </section>
        )}
        {(st.live.length > 0 && st.job && ["pending", "running"].includes(st.job.status)) && (
          <section className="rounded-xl border border-blue-500/30 bg-blue-950/30 p-3 text-[11px] text-blue-100" aria-live="polite" data-testid="mv-live">
            <h2 className="mb-1 font-bold uppercase tracking-widest text-blue-300">Live agent activity</h2>
            <ol className="max-h-48 space-y-0.5 overflow-y-auto">{st.live.slice(-12).map((l, i) => <li key={i}>{l.text}</li>)}</ol>
          </section>
        )}
      </aside>
      <CompareModal />
    </div>
  );
}

"use client";

import type { MatchStateSnapshot, TrackingFrame } from "@offscript/contracts";
import { useEffect, useMemo, useRef } from "react";
import { interpolate, type RenderFrame } from "@/lib/frames";
import { clock, pct } from "@/lib/format";
import { mv, useMv } from "@/lib/mvStore";
import { selectedDecision, useApp } from "@/lib/store";
import { type Arrow } from "../Pitch";
import { OutcomeCard } from "../PitchStage";
import PitchView, { DimToggle } from "../PitchView";
import ActionComposer from "./ActionComposer";
import AgentBattle, { PlanningSteps } from "./AgentBattle";
import CompareModal from "./CompareModal";
import DecisionTree from "./DecisionTree";
import LivePlanning from "./LivePlanning";

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

/** The first sentence of a narrative (decimals such as "1.4%" do not end a sentence). */
export function firstSentence(text: string): string {
  const m = text.match(/^.*?[.!?](?=\s+[A-Z]|$)/s);
  return (m ? m[0] : text).trim();
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
  if (!match || !node) return <div className="flex aspect-[111/74] animate-pulse items-center justify-center rounded-xl bg-white/[0.03] text-sm text-slate-500">Loading…</div>;

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
  const treeNode = st.tree?.nodes.find((n) => n.node_id === node.node_id);
  return (
    <div className="relative">
      <div className="absolute right-3 top-3 z-10 flex max-w-[65%] flex-col items-end gap-1.5">
        <span className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider backdrop-blur ${node.kind === "observed" ? "bg-slate-950/80 text-slate-100 ring-1 ring-white/20" : simulated ? "bg-leaf-600/90 text-white shadow-lg shadow-leaf-900/50" : "bg-sage-600/90 text-white shadow-lg shadow-sage-900/50"}`} data-testid="mv-banner">
          <span className="h-1.5 w-1.5 rounded-full bg-white" />
          {node.kind === "observed" ? "Canonical synthetic timeline" : node.kind === "root" ? "Frozen decision state" : `Simulated branch · depth ${node.depth}`}
        </span>
        {node.transition && node.kind !== "observed" && (
          <span className="rounded-lg bg-slate-950/80 px-2 py-1 text-[11px] text-leaf-200 backdrop-blur">one possible future · not a certainty</span>
        )}
      </div>
      <div className="absolute left-3 top-3 z-10"><DimToggle /></div>
      {/* The defence's answer, named, while its movement arrows are on the pitch. */}
      {node.entering_strategy && !atEnd && (
        <div className="absolute bottom-3 left-3 z-10 max-w-[60%] bg-slate-950/85 px-2 py-1 text-[11px] text-orange-200 ring-1 ring-orange-400/30 backdrop-blur" data-testid="mv-defence">
          Defence: <b className="text-orange-100">{node.entering_strategy.label}</b>
        </div>
      )}
      {simulated && atEnd && node.kind !== "root" && (
        <OutcomeCard action={node.label} outcome={node.outcome_label || treeNode?.outcome || node.status}
          lines={[
            treeNode?.value_vs_counter != null
              ? `${pct(treeNode.value_vs_counter)} modelled goal chance vs ${node.entering_strategy ? `“${node.entering_strategy.label}”` : "the defence's best counter"}` : "",
            "one simulated continuation",
          ]} />
      )}
      <PitchView match={match} frame={frame} arrows={arrows} highlightId={snap?.ball.possessor_id ?? null}
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
    <div className="glass flex items-center gap-3 px-3 py-2">
      <button type="button" onClick={() => mv.setPlay({ playing: !st.playing, playT: st.playT >= path.duration_ms ? 0 : st.playT })}
        className="h-10 w-10 rounded-sm bg-white text-sm font-bold text-slate-950 shadow-lg shadow-leaf-900/40 hover:bg-leaf-100" aria-label={st.playing ? "Pause" : "Play branch"}>{st.playing ? "❚❚" : "▶"}</button>
      <button type="button" onClick={() => mv.setPlay({ playT: 0, playing: true })} className="h-9 w-9 rounded-sm text-sm text-slate-300 hover:bg-white/10" aria-label="Replay branch from the decision">↺</button>
      <div className="relative flex-1">
        <input type="range" min={0} max={path.duration_ms} step={50} value={st.playT} aria-label="Scrub branch"
          onChange={(e) => mv.setPlay({ playT: Number(e.target.value), playing: false })} className="timeline w-full" />
        {path.boundaries.map((b) => (
          <span key={b.node_id} className="absolute top-[3px] h-2.5 w-2.5 -translate-x-1/2 rotate-45 bg-sage-400 ring-2 ring-ink" style={{ left: `${(b.t_ms / path.duration_ms) * 100}%` }} title={b.label} />
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
      <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-10" data-testid="mv-start">
        <div className="eyebrow text-sage-300">Football Multiverse</div>
        <h1 className="text-4xl font-black tracking-tight text-white">Every decision creates <span className="bg-gradient-to-r from-leaf-400 to-sage-400 bg-clip-text text-transparent">another game</span>.</h1>
        <p className="max-w-2xl text-[15px] leading-relaxed text-slate-400">Pick a decision from the current match, then explore different futures: choose actions, let attacking and
          defending agents compete, rewind, fork and compare. Every branch is a simulation under an explicit model of a synthetic match.</p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {app.decisions.map((d) => (
            <li key={d.decision_point_id}>
              <button type="button" disabled={st.starting} onClick={() => void mv.open(d.decision_point_id, d.match_id)} data-testid="mv-open-decision"
                className="glass group flex w-full flex-col gap-1 px-4 py-3 text-left transition hover:bg-white/[0.06] disabled:opacity-50">
                <span className="flex items-center gap-2">
                  <span className="num rounded-md bg-sage-500/15 px-1.5 py-0.5 font-mono text-xs text-sage-200">{clock(d.match_clock_ms)}</span>
                  <span className="font-bold text-white">{d.actor_name}</span>
                  <span className="ml-auto text-xs text-slate-500 group-hover:text-leaf-300">Enter →</span>
                </span>
                <span className="text-xs text-slate-400">{d.actual_action.label.replace(" (actual)", "")} → {d.actual_outcome.replace(/_/g, " ").toLowerCase()}</span>
                {decision?.decision_point_id === d.decision_point_id && <span className="ml-auto text-[10px] text-leaf-300">selected</span>}
              </button>
            </li>
          ))}
        </ul>
        {st.error && <p className="text-sm text-red-300">{st.error}</p>}
      </div>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-[1760px] flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_440px]" data-testid="multiverse-view">
      <section className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-x-3 px-1">
          <h1 className="text-2xl font-black tracking-tight text-white">Football Multiverse</h1>
          <p className="text-sm text-slate-400">{node ? `${clock(node.match_clock_ms)} · ${node.label}${node.outcome_label ? ` → ${node.outcome_label.replace(/_/g, " ").toLowerCase()}` : ""}` : ""}</p>
        </div>
        <div className="mx-auto w-full max-w-[max(520px,calc((100vh-470px)*1.5))] frame overflow-hidden p-2 shadow-2xl shadow-black/60"><Stage /></div>
        <PlayBar />
        {st.error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">{st.error}</p>}
        <section className="glass p-3" aria-label="Multiverse map">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="eyebrow">Multiverse map</h2>
            {app.mode === "analyst" && <span className="hidden text-[10px] text-slate-500 md:inline">dashed white = canonical synthetic timeline (never changed) · amber = branch ended · % = modelled xG vs the defence&apos;s best counter</span>}
            <div className="ml-auto flex gap-1">
              <button type="button" onClick={() => void mv.newSession()} className="btn px-2 py-1 text-[11px]">New session</button>
              <button type="button" onClick={() => mv.close()} className="btn px-2 py-1 text-[11px]">Close</button>
            </div>
          </div>
          <DecisionTree />
          {node && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-white/5 pt-2 text-xs">
              <button type="button" disabled={!node.parent_node_id} onClick={() => void mv.rewind()} data-testid="rewind" className="btn py-1">⟲ Rewind to decision</button>
              <button type="button" disabled={!node.parent_node_id} onClick={() => node.parent_node_id && void mv.select(node.parent_node_id)} data-testid="fork" className="btn py-1">⑂ Create another branch</button>
              <button type="button" onClick={() => void mv.select(st.session!.root_node_id)} className="btn py-1">Root decision</button>
              {node.kind !== "root" && (
                <div className="ml-auto flex flex-wrap items-center gap-1">
                  <span className="text-slate-500">Compare with</span>
                  {[...siblings, ...(st.tree?.nodes.filter((n) => n.kind === "observed" && n.node_id !== node.node_id && !siblings.includes(n)) ?? [])]
                    .slice(0, 6).map((n) => (
                      <button key={n.node_id} type="button" onClick={() => void mv.openCompare(node.node_id, n.node_id, app.lang)} data-testid="compare-with"
                        className="btn border border-white/10 bg-transparent py-1">{n.kind === "observed" ? "Actual" : n.label}</button>
                    ))}
                </div>
              )}
            </div>
          )}
        </section>
        <p className="px-1 text-[11px] text-slate-600">Branches are modelled futures of a synthetic match: each shows one sampled continuation, with probabilities from paired Monte Carlo simulation. Rewinding restores the exact stored state; nothing is re-simulated.</p>
      </section>
      <aside className="min-w-0 space-y-3 lg:sticky lg:top-[62px] lg:max-h-[calc(100vh-78px)] lg:overflow-y-auto lg:pr-1">
        <section className="glass p-3">
          <h2 className="eyebrow mb-3">Your decision</h2>
          <ActionComposer />
        </section>
        {st.job && ["pending", "running"].includes(st.job.status) && <LivePlanning />}
        {shownPlanning && (
          <section className="glass space-y-3 p-3">
            <h2 className="eyebrow">{planning ? "Attack vs defence (this step)" : "Agent recommendation"}</h2>
            {narrative && (
              <article className="rounded-xl bg-white/[0.03] p-2" data-testid="mv-narrative">
                <h3 className="text-sm font-bold text-white">{narrative.headline}</h3>
                {app.mode === "analyst" ? (
                  // Analysts get the findings and the matrix first; the long text stays one click away.
                  <>
                    <p className="mt-1 text-sm leading-relaxed text-slate-200">{firstSentence(narrative.body)}</p>
                    <details className="mt-1 text-[12px] text-slate-300" data-testid="mv-narrative-more">
                      <summary className="cursor-pointer font-semibold text-leaf-300">Read the full analysis</summary>
                      <p className="mt-1 leading-relaxed">{narrative.body}</p>
                      <ul className="mt-1 list-disc pl-4 text-[11px]">{narrative.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
                    </details>
                  </>
                ) : (
                  <p className="mt-1 text-sm leading-relaxed text-slate-200">{app.mode === "broadcaster" ? narrative.caption ?? narrative.body : narrative.body}</p>
                )}
              </article>
            )}
            {app.mode === "casual" && shownPlanning.summary ? (
              <div className="text-xs text-slate-300">Selected option vs the defence&apos;s best answer: <b className="text-white">{pct(shownPlanning.summary.selected_value_vs_counter, app.lang)}</b> modelled goal chance within 10 s (vs {pct(shownPlanning.summary.selected_value_vs_baseline, app.lang)} against a balanced shape).</div>
            ) : (
              <AgentBattle p={shownPlanning} compact={app.mode === "broadcaster"} />
            )}
            {app.mode !== "casual" && (
              <details className="rounded-xl bg-white/[0.03] p-2 text-xs" data-testid="mv-inspector">
                <summary className="cursor-pointer font-semibold text-slate-200">Agent workflow inspector</summary>
                <div className="mt-2"><PlanningSteps p={shownPlanning} /></div>
              </details>
            )}
          </section>
        )}
      </aside>
      <CompareModal />
    </div>
  );
}

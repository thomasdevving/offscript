"""Football Multiverse evaluation.

Compares three ways of answering "what should the player do here?" on every labelled decision of the
synthetic scenarios (internal consistency of the model only - not real-world validity):

  A. Single decision   - rank the generated options by modelled xG within the horizon against the
                         baseline (balanced) defence. This is what the original OFFSCRIPT analysis does.
  B. Branching         - second-order value: realise sampled successor states of the top-2 A options and
                         let the attacker re-decide at the next decision (best next option chosen on one
                         seed, valued on an independent seed to avoid winner's-curse bias).
  C. Adversarial       - the Multiverse planning: attacking and defending agents with a bounded
                         response matrix; maximin (robust) vs mean vs upside choices.

Also measures latency, Monte Carlo cost, cache hit rate, concurrency, memory, determinism, verification
and narrative grounding of the multiverse plannings.

Writes docs/multiverse_evaluation.json and docs/multiverse_evaluation.md.
Usage: python scripts/evaluate_multiverse.py [--quick]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.agents.runner import ChatClientProvider  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models.multiverse import ActionSpec, BranchActionRequest, SessionCreate  # noqa: E402
from app.multiverse.core import CellEvaluator, realize_transition  # noqa: E402
from app.multiverse.service import MultiverseService  # noqa: E402
from app.services.hub import EventHub  # noqa: E402
from app.services.store import Store  # noqa: E402
from app.simulation.candidates import generate_candidates  # noqa: E402

SHOT_OUTCOMES = {"goal", "saved", "off_target", "blocked"}


def pp(x: float) -> str:
    return f"{100 * x:+.2f} pp"


def pc(x: float) -> str:
    return f"{100 * x:.2f}%"


async def run(quick: bool) -> dict:
    n = 40 if quick else 80
    k_succ = 4 if quick else 8
    tmp = Path(tempfile.mkdtemp(prefix="offscript-mv-eval-"))
    settings = Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp, scenarios_dir=ROOT / "scenarios",
                        multiverse_cell_rollouts=n, multiverse_max_cell_rollouts=n, max_concurrent_analyses=4)
    store = Store(settings.scenarios_dir, settings.data_dir)
    store.load()
    svc = MultiverseService(settings, store, EventHub(), ChatClientProvider(settings))
    horizon = settings.simulation_horizon_s

    decisions = []
    for md in store.matches.values():
        for d in md.decisions:
            if d.event_id in md.labelled_decision_event_ids:
                decisions.append((md, d))
    if quick:
        decisions = decisions[:3]

    async def step(sid: str, node: str, **kw):
        job = await svc.start_step(sid, node, BranchActionRequest(**kw))
        return await svc.wait(job.job_id)

    rows = []
    plannings = []
    for md, d in decisions:
        snap = md.snapshots[d.snapshot_id]
        roster = md.roster
        row: dict = {"scenario": md.info.scenario_id, "decision": d.decision_point_id, "clock_ms": d.match_clock_ms,
                     "actual": d.actual_action.label.replace(" (actual)", "")}

        # ---- A: single decision vs the baseline defence ------------------------------------------
        ev = CellEvaluator()
        t0 = time.perf_counter()
        cands = generate_candidates(snap, roster)
        a_vals = {c.action_id: ev.evaluate(snap, roster, c, None, n, snap.seed, horizon) for c in cands}
        a_ms = (time.perf_counter() - t0) * 1000
        ranked = sorted(cands, key=lambda c: -a_vals[c.action_id].cell.xg)
        top_a = ranked[0]
        row["A"] = {"top": top_a.label, "top_xg": a_vals[top_a.action_id].cell.xg, "options": len(cands),
                    "rollouts": n * len(cands), "latency_ms": round(a_ms)}

        # ---- C: adversarial planning (assisted recommendation: agents choose) -------------------
        s = svc.create_session(SessionCreate(decision_point_id=d.decision_point_id, mode="assisted"))
        rec = await step(s.session_id, s.root_node_id, mode="assisted")
        p = s.plannings[rec.planning_id]
        plannings.append(p)
        sm = p.summary
        lab = {a.action.action_id: a.action.label for a in p.attack_proposals}
        robust, upside, mean = sm.most_robust_action_id, sm.highest_upside_action_id, sm.best_expected_action_id
        pa = sm.per_action
        # A's top option against the defence's best counter: plan with it as the user's action.
        forced = await step(s.session_id, s.root_node_id, action=ActionSpec(candidate_id=top_a.action_id), mode="manual")
        pf = s.plannings[forced.planning_id]
        plannings.append(pf)
        top_a_worst = pf.summary.selected_value_vs_counter
        top_a_base = pf.summary.selected_value_vs_baseline
        row["C"] = {
            "robust": lab[robust], "upside": lab[upside], "mean": lab[mean],
            "robust_worst": pa[robust]["worst"], "robust_mean": pa[robust]["mean"],
            "upside_worst": pa[upside]["worst"], "upside_best": pa[upside]["best"],
            "counter": sm.defensive_counter_id, "counter_effect_pp": sm.counter_effect_pp,
            "rounds": len(p.rounds), "actions": len({c.action_id for c in p.matrix}),
            "strategies": len({c.strategy_id for c in p.matrix}), "cells": len(p.matrix),
            "rollouts": sum(c.n_rollouts for c in p.matrix if not c.cached),
            "latency_ms": p.duration_ms, "verified": p.verification_status == "verified",
            "top_a_vs_baseline": top_a_base, "top_a_vs_counter": top_a_worst,
            "top_a_optimism_gap": top_a_base - top_a_worst,
            "robust_differs_from_a": lab[robust] != top_a.label,
            "robust_minus_top_a_worst": pa[robust]["worst"] - top_a_worst,
        }

        # ---- B: branching / second-order value of the top-2 single-decision options -------------
        b_rows = []
        t0 = time.perf_counter()
        b_rollouts = 0
        for c in ranked[:2]:
            cell = a_vals[c.action_id]
            vals = []
            for k in range(k_succ):
                out = realize_transition(snap, roster, c, None, cell, "random", f"eval-{k}", 1000 + k)
                t = out.transition
                if t.terminal_outcome is not None:
                    # the possession ended in the first action: its value is the shot's conditional goal
                    # probability (0 for a turnover)
                    vals.append(cell.summaries[t.rollout_index].shot_goal_prob if t.first_outcome in SHOT_OUTCOMES else 0.0)
                    continue
                child = out.child_snapshot
                nxt = generate_candidates(child, roster)
                pick = CellEvaluator()
                choose = {x.action_id: pick.evaluate(child, roster, x, None, n // 2, child.seed, horizon) for x in nxt}
                best = max(nxt, key=lambda x: choose[x.action_id].cell.xg)
                vals.append(pick.evaluate(child, roster, best, None, n, child.seed + 7919, horizon).cell.xg)
                b_rollouts += len(nxt) * (n // 2) + n
            b_rows.append({"action": c.label, "first_order": cell.cell.xg, "second_order": statistics.fmean(vals),
                           "successors": k_succ})
        flip = len(b_rows) == 2 and b_rows[1]["second_order"] > b_rows[0]["second_order"]
        row["B"] = {"rows": b_rows, "ranking_flips": flip, "rollouts": b_rollouts,
                    "latency_ms": round((time.perf_counter() - t0) * 1000)}
        rows.append(row)
        print(f"{row['scenario']:<20} A:{row['A']['top']:<32} C robust:{row['C']['robust']:<32} B flip:{flip}")

    # ---- performance: cache, determinism, concurrency, memory ---------------------------------------
    md, d = decisions[0]
    svc.evaluator.hits = svc.evaluator.misses = 0
    s2 = svc.create_session(SessionCreate(decision_point_id=d.decision_point_id, mode="assisted"))
    t0 = time.perf_counter()
    rec2 = await step(s2.session_id, s2.root_node_id, mode="assisted")
    cached_ms = (time.perf_counter() - t0) * 1000
    p2 = s2.plannings[rec2.planning_id]
    first = next(p for p in plannings if p.node_id.endswith("~root") and p.snapshot_id == d.snapshot_id)
    same = [(c.action_id, c.strategy_id, c.xg) for c in first.matrix] == [(c.action_id, c.strategy_id, c.xg) for c in p2.matrix]

    fresh = MultiverseService(settings, store, EventHub(), ChatClientProvider(settings))
    s3 = fresh.create_session(SessionCreate(decision_point_id=d.decision_point_id, mode="assisted"))
    j3 = await fresh.start_step(s3.session_id, s3.root_node_id, BranchActionRequest(mode="assisted"))
    p3 = s3.plannings[(await fresh.wait(j3.job_id)).planning_id]
    deterministic = [(c.action_id, c.strategy_id, c.xg) for c in first.matrix] == \
                    [(c.action_id, c.strategy_id, c.xg) for c in p3.matrix]

    async def batch(service: MultiverseService, conc: int) -> float:
        sessions = [service.create_session(SessionCreate(decision_point_id=dd.decision_point_id, mode="assisted"))
                    for _, dd in decisions[:conc]]
        t = time.perf_counter()
        jobs = [await service.start_step(x.session_id, x.root_node_id, BranchActionRequest(mode="assisted")) for x in sessions]
        await asyncio.gather(*(service.wait(j.job_id) for j in jobs))
        return time.perf_counter() - t

    conc = min(4, len(decisions))
    seq_settings = settings.model_copy(update={"max_concurrent_analyses": 1})
    seq_s = await batch(MultiverseService(seq_settings, store, EventHub(), ChatClientProvider(seq_settings)), conc)
    par_s = await batch(MultiverseService(settings, store, EventHub(), ChatClientProvider(settings)), conc)

    tracemalloc.start()
    mem_svc = MultiverseService(settings, store, EventHub(), ChatClientProvider(settings))
    sm4 = mem_svc.create_session(SessionCreate(decision_point_id=d.decision_point_id))
    j4 = await mem_svc.start_step(sm4.session_id, sm4.root_node_id,
                                  BranchActionRequest(action=ActionSpec(action_type="shoot"), mode="manual"))
    await mem_svc.wait(j4.job_id)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    session_bytes = [f.stat().st_size for f in (tmp / "multiverse").glob("*.json")]

    narr = [nn for p in plannings for nn in p.narratives]
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "quick": quick, "rollouts_per_cell": n,
        "successor_samples": k_succ, "decisions": len(rows), "rows": rows,
        "summary": {
            "robust_differs_from_single_decision": sum(r["C"]["robust_differs_from_a"] for r in rows),
            "mean_optimism_gap_top_a": statistics.fmean(r["C"]["top_a_optimism_gap"] for r in rows),
            "mean_robust_minus_top_a_worst": statistics.fmean(r["C"]["robust_minus_top_a_worst"] for r in rows),
            "second_order_ranking_flips": sum(r["B"]["ranking_flips"] for r in rows),
            "mean_value_of_redeciding": statistics.fmean(b["second_order"] - b["first_order"]
                                                         for r in rows for b in r["B"]["rows"]),
            "verified_plannings": sum(p.verification_status == "verified" for p in plannings),
            "plannings": len(plannings),
            "narratives_verified": sum(nn.verification_status == "verified" for nn in narr),
            "narratives": len(narr),
            "live_model_calls": sum(p.live_model_calls for p in plannings),
        },
        "cost": {
            "A_rollouts_mean": statistics.fmean(r["A"]["rollouts"] for r in rows),
            "B_rollouts_mean": statistics.fmean(r["B"]["rollouts"] for r in rows),
            "C_rollouts_mean": statistics.fmean(r["C"]["rollouts"] for r in rows),
            "A_latency_ms_mean": statistics.fmean(r["A"]["latency_ms"] for r in rows),
            "B_latency_ms_mean": statistics.fmean(r["B"]["latency_ms"] for r in rows),
            "C_latency_ms_p50": statistics.median(p.duration_ms for p in plannings),
            "C_latency_ms_max": max(p.duration_ms for p in plannings),
            "C_rounds_mean": statistics.fmean(len(p.rounds) for p in plannings),
            "C_cells_mean": statistics.fmean(len(p.matrix) for p in plannings),
        },
        "performance": {
            "repeat_planning_cache_hits": p2.cache_hits, "repeat_planning_cells": len(p2.matrix),
            "repeat_planning_ms": round(cached_ms), "first_planning_ms": first.duration_ms,
            "repeat_identical": same, "fresh_process_identical": deterministic,
            "concurrent_plannings": conc, "sequential_s": round(seq_s, 2), "concurrent_s": round(par_s, 2),
            "peak_python_heap_mb_one_step": round(peak / 1e6, 1),
            "session_json_kb_max": round(max(session_bytes) / 1024, 1) if session_bytes else None,
        },
    }
    return out


def to_markdown(r: dict) -> str:
    s, c, p = r["summary"], r["cost"], r["performance"]
    L = [
        "# Football Multiverse evaluation results",
        "",
        f"Generated {r['generated_at']}{' (quick mode)' if r['quick'] else ''} by `scripts/evaluate_multiverse.py`, "
        f"{r['decisions']} labelled decisions, {r['rollouts_per_cell']} paired simulations per cell, "
        f"{r['successor_samples']} sampled successor states per option for B. Agent mode: deterministic policy planner "
        f"({s['live_model_calls']} live model calls). All values are modelled expected goals within the horizon on "
        "synthetic data: they measure what the model implies, not what would happen in a real match.",
        "",
        "## A vs B vs C per decision",
        "",
        "| Scenario | Actual | A: best vs balanced defence | C: most robust (worst case) | C: highest upside | A's choice vs counter | Optimism gap | B: top-2 flip? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for x in r["rows"]:
        a, b, cc = x["A"], x["B"], x["C"]
        L.append(f"| {x['scenario']} | {x['actual']} | {a['top']} ({pc(a['top_xg'])}) | {cc['robust']} ({pc(cc['robust_worst'])}) | "
                 f"{cc['upside']} ({pc(cc['upside_best'])}) | {pc(cc['top_a_vs_counter'])} | {pp(cc['top_a_optimism_gap'])} | "
                 f"{'yes' if b['ranking_flips'] else 'no'} |")
    L += [
        "",
        "Optimism gap = A's chosen option valued against the balanced defence minus the same option against the "
        "defending agent's best counter (both from the adversarial matrix).",
        "",
        "## Findings",
        "",
        f"- **Robust vs optimistic.** The adversarial planner's most robust option differed from the single-decision "
        f"pick in {s['robust_differs_from_single_decision']}/{r['decisions']} decisions. On average A's pick was worth "
        f"{100 * s['mean_optimism_gap_top_a']:.2f} pp less modelled xG once the defence chose its best counter, so the "
        "single-decision number is optimistic; the maximin choice's worst case differed from A's pick's worst case by "
        f"{pp(s['mean_robust_minus_top_a_worst'])}.",
        f"- **Second-order effects.** Letting the attacker re-decide at the next decision changed the order of A's top two "
        f"options in {s['second_order_ranking_flips']}/{r['decisions']} decisions. Mean value of re-deciding "
        f"(second-order minus first-order value): {pp(s['mean_value_of_redeciding'])}. The successor value uses a "
        "new 10 s horizon from the successor state, so it is a ranking signal, not an additive gain.",
        f"- **Verification and grounding.** {s['verified_plannings']}/{s['plannings']} plannings passed all deterministic "
        f"checks; {s['narratives_verified']}/{s['narratives']} narratives passed the numeric/name grounding verifier.",
        "",
        "### B: first-order vs second-order value of the top-2 single-decision options",
        "",
        "| Scenario | Option | First-order (A) | Second-order (re-decide at next decision) |",
        "|---|---|---|---|",
        *[f"| {x['scenario']} | {b['action']} | {pc(b['first_order'])} | {pc(b['second_order'])} |" for x in r["rows"] for b in x["B"]["rows"]],
        "",
        f"Second-order values average {r['successor_samples']} sampled successor states each, so they are indicative.",
        "",
        "## Cost and latency",
        "",
        "| | A single decision | B branching (top-2) | C adversarial |",
        "|---|---|---|---|",
        f"| Rollouts per decision (mean) | {c['A_rollouts_mean']:.0f} | {c['B_rollouts_mean']:.0f} | {c['C_rollouts_mean']:.0f} |",
        f"| Latency (mean / p50) | {c['A_latency_ms_mean']:.0f} ms | {c['B_latency_ms_mean']:.0f} ms | {c['C_latency_ms_p50']:.0f} ms (max {c['C_latency_ms_max']:.0f}) |",
        "",
        f"C used {c['C_rounds_mean']:.1f} rounds and {c['C_cells_mean']:.1f} matrix cells on average (bounded by 3 rounds).",
        "",
        "## Performance",
        "",
        f"- Repeating a planning on the same frozen state: {p['repeat_planning_cache_hits']}/{p['repeat_planning_cells']} "
        f"cells served from the cache, {p['repeat_planning_ms']} ms vs {p['first_planning_ms']:.0f} ms first time; identical "
        f"matrix: {p['repeat_identical']}.",
        f"- Deterministic replay in a fresh service (empty cache, same seed): identical matrix: {p['fresh_process_identical']}.",
        f"- {p['concurrent_plannings']} plannings: {p['sequential_s']} s with concurrency 1, {p['concurrent_s']} s with "
        "concurrency 4. Simulation is CPU-bound NumPy in one process, so concurrency mainly improves responsiveness, "
        "not throughput; scale out with more replicas.",
        f"- Peak Python heap for one branching step: {p['peak_python_heap_mb_one_step']} MB; largest persisted session "
        f"JSON: {p['session_json_kb_max']} KB.",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    r = asyncio.run(run(args.quick))
    docs = ROOT / "docs"
    (docs / "multiverse_evaluation.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    (docs / "multiverse_evaluation.md").write_text(to_markdown(r), encoding="utf-8")
    print(to_markdown(r))


if __name__ == "__main__":
    main()

"""PARALLEL evaluation harness.

Measures (on synthetic data only - internal consistency, not real-world validity):
  1. decision detection recall against scenario labels + false flags on scripted build-up
  2. candidate validity and rejection of invalid proposals
  3. verification reliability: detection of injected numeric / narrative corruptions, false positives
  4. narrative numerical grounding
  5. workflow recovery for every controlled fault on every labelled decision
  6. reproducibility (same seed -> identical results)
  7. Monte Carlo convergence (interval width vs rollouts)
  8. latency (p50/p95) for ingest, detection, simulation, agents, end-to-end
  9. simulator sanity (shot model by distance, pass completion in procedural play)

Writes docs/evaluation_results.json and docs/evaluation_results.md.
Usage: python scripts/evaluate.py [--quick]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import numpy as np  # noqa: E402

from app.analytics.detector import detect_all  # noqa: E402
from app.config import Settings  # noqa: E402
from app.match_state.engine import MatchStateEngine  # noqa: E402
from app.models.analysis import AnalyzeRequest  # noqa: E402
from app.models.events import EventType  # noqa: E402
from app.models.narrative import Narrative  # noqa: E402
from app.models.simulation import SimulationConfig  # noqa: E402
from app.services import metrics  # noqa: E402
from app.services.analysis_service import AnalysisService  # noqa: E402
from app.services.hub import EventHub  # noqa: E402
from app.services.store import Store  # noqa: E402
from app.simulation.candidates import generate_candidates, validate_candidate  # noqa: E402
from app.simulation.engine import Engine, EngineState, Profile, goalkeeper_target  # noqa: E402
from app.simulation.monte_carlo import evaluate_actions  # noqa: E402
from app.synthetic_data.scenarios import generate, load_scenarios  # noqa: E402
from app.verification.checks import verify_analysis, verify_narrative  # noqa: E402
from app.verification.evidence import build_evidence  # noqa: E402

FAULTS = ["invalid_candidate", "contradictory_claim", "model_unavailable", "simulation_timeout"]


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


async def main(quick: bool) -> dict:
    out: dict = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "quick": quick}
    defs = {d.scenario_id: d for d in load_scenarios(ROOT / "scenarios")}

    # 1. Detection ------------------------------------------------------------------------
    det_rows = []
    for sid, d in defs.items():
        m = generate(d)
        decisions, det = detect_all(m.info.match_id, m.events, m.roster, m.snapshots)
        found = {x.event_id for x in decisions}
        labelled = set(m.decision_event_ids)
        scripted_flagged = len(found & set(m.scripted_event_ids))
        actions = sum(1 for e in m.events if e.event_type in (EventType.PASS_ATTEMPTED, EventType.SHOT_ATTEMPTED,
                                                              EventType.DRIBBLE_ATTEMPTED))
        det_rows.append({"scenario": sid, "labelled": len(labelled), "recalled": len(labelled & found),
                         "detections": len(decisions), "on_ball_actions": actions,
                         "scripted_flagged": scripted_flagged, "suppressed": len(det.suppressed),
                         "minutes": round(m.info.duration_ms / 60000, 2)})
    lab = sum(r["labelled"] for r in det_rows)
    rec = sum(r["recalled"] for r in det_rows)
    out["detection"] = {"rows": det_rows, "recall": rec / lab if lab else None,
                        "scripted_false_flags": sum(r["scripted_flagged"] for r in det_rows)}

    # 2. Candidate validity ----------------------------------------------------------------
    m = generate(defs["shoot_vs_pass"])
    total = valid = 0
    for e in m.events:
        if e.snapshot_id and e.event_type in (EventType.PASS_ATTEMPTED, EventType.SHOT_ATTEMPTED,
                                              EventType.DRIBBLE_ATTEMPTED):
            snap = m.snapshots[e.snapshot_id]
            for c in generate_candidates(snap, m.roster):
                total += 1
                valid += validate_candidate(snap, m.roster, c).ok
    out["candidate_validity"] = {"generated": total, "valid": valid, "rate": valid / total if total else None}

    # Analysis service (policy mode, no cache) ----------------------------------------------
    tmp = ROOT / "apps" / "api" / "data" / "eval"
    settings = Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp, scenarios_dir=ROOT / "scenarios",
                        default_rollouts=200)
    store = Store(settings.scenarios_dir, settings.data_dir)
    store.load()
    svc = AnalysisService(settings, store, EventHub())
    labelled = []
    for md in store.matches.values():
        for dp in md.decisions:
            if dp.event_id in md.labelled_decision_event_ids:
                labelled.append(dp)
    metrics.reset()

    # 5. Recovery + baseline analyses ---------------------------------------------------------
    base_analyses = {}
    recovery_rows = []
    for dp in labelled:
        t0 = time.perf_counter()
        a = await svc.wait((await svc.start(dp.decision_point_id, AnalyzeRequest())).analysis_id)
        base_analyses[dp.decision_point_id] = a
        metrics.record("eval.analysis_wall", (time.perf_counter() - t0) * 1000)
        for f in FAULTS if not quick else FAULTS[:2]:
            r = await svc.wait((await svc.start(dp.decision_point_id, AnalyzeRequest(fault_injection=[f]))).analysis_id)
            recovery_rows.append({"decision": dp.decision_point_id, "fault": f, "final_status": r.status,
                                  "agent_runs": len(r.workflow.steps), "baseline_runs": len(a.workflow.steps),
                                  "retries": r.workflow.retry_count + r.workflow.explanation_retries,
                                  "degraded": r.model.degraded})
    out["baseline_analyses"] = [{"decision": k, "status": a.status, "verdict": a.simulation.overall_verdict if a.simulation
                                 else None, "options": [c.label for c in a.candidates]} for k, a in base_analyses.items()]
    ok = sum(1 for r in recovery_rows if r["final_status"] == "verified")
    out["recovery"] = {"rows": recovery_rows, "recovered": ok, "total": len(recovery_rows)}

    # 3. Verification reliability ---------------------------------------------------------------
    rng = random.Random(7)
    numeric_trials = numeric_caught = 0
    narrative_trials = narrative_caught = clean_trials = clean_flagged = 0
    for dpid, a in base_analyses.items():
        if a.status != "verified":
            continue
        dp = store.decisions[dpid]
        md = store.matches[dp.match_id]
        snap = md.snapshots[dp.snapshot_id]
        for _ in range(10 if not quick else 3):
            bad = a.model_copy(deep=True)
            r = rng.choice(bad.simulation.results)
            kind = rng.choice(["value", "ci", "count", "diff"])
            if kind == "value":
                r.p_goal = r.p_goal.model_copy(update={"value": min(1.0, r.p_goal.value + rng.choice([0.01, 0.05, 0.2]))})
            elif kind == "ci":
                r.p_turnover = r.p_turnover.model_copy(update={"ci95_high": max(0.0, r.p_turnover.ci95_high - 0.05)})
            elif kind == "count":
                r.outcome_counts["goal"] = r.outcome_counts.get("goal", 0) + 1
            elif bad.simulation.comparisons:
                c = bad.simulation.comparisons[0]
                c.diff_p_goal = c.diff_p_goal + 0.05
            numeric_trials += 1
            rec_ = verify_analysis(bad, dp, snap, md.roster, reproduce=False)
            numeric_caught += rec_.status == "rejected"
        evidence = build_evidence(a, dp, md.roster)
        allowed = {dp.actor_id} | {c.target_player_id for c in a.candidates if c.target_player_id}
        actor = md.snapshots[dp.snapshot_id].player(dp.actor_id)
        allowed |= {p.player_id for p in md.snapshots[dp.snapshot_id].players
                    if math.hypot(p.x - actor.x, p.y - actor.y) < 12}
        for n in a.narratives:
            clean_trials += 1
            clean_flagged += bool(verify_narrative(n, evidence, md.roster, allowed))
            for corruption in ("number", "certainty", "name"):
                body = n.body
                if corruption == "number":
                    body = body + (" The model gives it 37.9%." if n.language == "en" else " Het model geeft 37,9%.")
                elif corruption == "certainty":
                    body = body + (" He would have scored." if n.language == "en" else " Hij zou hebben gescoord.")
                else:
                    outsider = next(p for p in md.roster.values() if p.player_id not in allowed)
                    body = body + f" {outsider.name}."
                narrative_trials += 1
                narrative_caught += bool(verify_narrative(n.model_copy(update={"body": body}), evidence, md.roster,
                                                          allowed))
    out["verification"] = {
        "numeric_corruptions": numeric_trials, "numeric_detected": numeric_caught,
        "narrative_corruptions": narrative_trials, "narrative_detected": narrative_caught,
        "clean_narratives": clean_trials, "clean_false_positives": clean_flagged,
    }
    out["narrative_grounding"] = {"verified_narratives": sum(len(a.narratives) for a in base_analyses.values()),
                                  "all_numbers_grounded": clean_flagged == 0}

    # 6. Reproducibility ----------------------------------------------------------------------
    dp0 = labelled[0]
    a1 = base_analyses[dp0.decision_point_id]
    a2 = await svc.wait((await svc.start(dp0.decision_point_id, AnalyzeRequest(force_refresh=True))).analysis_id)
    same = [r.model_dump() for r in a1.simulation.results] == [r.model_dump() for r in a2.simulation.results]
    t1 = await svc.trajectory(a1.analysis_id, a1.candidates[1].action_id)
    t2 = await svc.trajectory(a2.analysis_id, a2.candidates[1].action_id)
    out["reproducibility"] = {"identical_results": same,
                              "identical_trajectory": [f.model_dump() for f in t1.frames] == [f.model_dump() for f in t2.frames],
                              "regenerated_match_identical": generate(defs["shoot_vs_pass"]).events == m.events}

    # 7. Convergence -------------------------------------------------------------------------
    md = store.matches[dp0.match_id]
    snap = md.snapshots[dp0.snapshot_id]
    actions = a1.candidates[:2]
    conv = []
    for n in ([50, 100, 200, 500] if not quick else [50, 200]):
        t0 = time.perf_counter()
        ev = evaluate_actions(snap, md.roster, actions, SimulationConfig(rollouts=n, seed=snap.seed, time_budget_s=120))
        r = ev.results[1]
        conv.append({"rollouts": n, "p_turnover": r.p_turnover.value,
                     "turnover_ci_width": r.p_turnover.ci95_high - r.p_turnover.ci95_low,
                     "p_goal": r.p_goal.value, "goal_ci_width": r.p_goal.ci95_high - r.p_goal.ci95_low,
                     "seconds_for_2_options": round(time.perf_counter() - t0, 2)})
    out["convergence"] = conv

    # 8. Latency -------------------------------------------------------------------------------
    eng = MatchStateEngine(md.info)
    proc = store.matches["procedural-match-2026"]
    eng2 = MatchStateEngine(proc.info)
    for e in proc.events:
        t0 = time.perf_counter()
        eng2.ingest(e)
        metrics.record("ingest.event_to_state", (time.perf_counter() - t0) * 1000)
    _ = eng
    from app.analytics.detector import DecisionDetector
    det = DecisionDetector(proc.info.match_id, proc.roster, proc.snapshots)
    for e in proc.events:
        t0 = time.perf_counter()
        det.on_event(e)
        metrics.record("detector.on_event", (time.perf_counter() - t0) * 1000)
    out["latency"] = {k: v for k, v in metrics.summary().items()
                      if k.startswith(("ingest", "detector", "simulation", "agent.", "analysis", "eval", "tool.run"))}

    # 9. Simulator sanity --------------------------------------------------------------------
    e = Engine()

    def lone_shot(d: float) -> float:
        profs = [Profile("S", "T", "s", "ST", 9, 0.25, 0.75, 0.7, 0.7), Profile("G", "U", "g", "GK", 7.3, 0.23, 0.6, 0.1, 0.2)]
        pos = np.array([[105 - d, 34.0], list(goalkeeper_target(np.array([105 - d, 34.0])))])
        st = EngineState(profiles=profs, is_att=np.array([True, False]), pos=pos, vel=np.zeros_like(pos),
                         anchors=pos.copy(), ball=pos[0].copy(), ball_ref=pos[0].copy(), carrier=0, t=0, direction=1,
                         att_team="T", def_team="U")
        return e.shot_probability(st, 0, 3000, seed=1)

    passes = sum(1 for x in proc.events if x.event_type == EventType.PASS_ATTEMPTED)
    completed = sum(1 for x in proc.events if x.event_type == EventType.PASS_COMPLETED)
    shots = sum(1 for x in proc.events if x.event_type == EventType.SHOT_ATTEMPTED)
    out["simulator_sanity"] = {
        "unpressured_central_shot_goal_probability": {f"{d} m": round(lone_shot(d), 3) for d in (6, 11, 16, 20, 25, 30)},
        "procedural_pass_completion": round(completed / passes, 3) if passes else None,
        "procedural_shots_per_10_min": shots,
        "procedural_minutes": round(proc.info.duration_ms / 60000, 1),
    }
    return out


def to_markdown(r: dict) -> str:
    L = ["# Evaluation results (generated)", "",
         f"Generated by `scripts/evaluate.py` at {r['generated_at']}. Synthetic data only: these numbers measure internal "
         "consistency and engineering behaviour, **not** real-world predictive validity.", ""]
    d = r["detection"]
    L += ["## 1. Decision detection", "", "| Scenario | Labelled | Recalled | Detections | On-ball actions | Minutes | Scripted actions flagged |",
          "|---|---|---|---|---|---|---|"]
    for row in d["rows"]:
        L.append(f"| {row['scenario']} | {row['labelled']} | {row['recalled']} | {row['detections']} | {row['on_ball_actions']} | "
                 f"{row['minutes']} | {row['scripted_flagged']} |")
    rec_n = sum(x["recalled"] for x in d["rows"])
    lab_n = sum(x["labelled"] for x in d["rows"])
    L += ["", f"Recall on labelled decisions: **{rec_n}/{lab_n} ({pct(d['recall'])})**. "
          f"Scripted build-up actions wrongly flagged: **{d['scripted_false_flags']}**. Unlabelled detections in "
          "free play are not counted as false positives (no ground truth exists for them).", ""]
    cv = r["candidate_validity"]
    L += ["## 2. Candidate validity", "", f"{cv['valid']}/{cv['generated']} generated candidates pass deterministic "
          f"validation ({pct(cv['rate'])}). Injected invalid proposals are covered in section 5.", ""]
    v = r["verification"]
    L += ["## 3. Verification reliability", "",
          f"- Injected numeric corruptions detected: **{v['numeric_detected']}/{v['numeric_corruptions']}**",
          f"- Injected narrative corruptions (unsupported number, certainty language, unrelated player) detected: "
          f"**{v['narrative_detected']}/{v['narrative_corruptions']}**",
          f"- Clean narratives wrongly flagged: **{v['clean_false_positives']}/{v['clean_narratives']}**", ""]
    g = r["narrative_grounding"]
    L += ["## 4. Narrative numerical grounding", "", f"{g['verified_narratives']} published narratives; every number "
          f"traceable to an evidence field: **{g['all_numbers_grounded']}**.", ""]
    rc = r["recovery"]
    L += ["## 5. Workflow recovery", "", f"Recovered to a verified analysis: **{rc['recovered']}/{rc['total']}**", "",
          "| Decision | Fault | Final status | Agent runs (baseline) | Retries | Degraded |", "|---|---|---|---|---|---|"]
    for row in rc["rows"]:
        L.append(f"| {row['decision']} | {row['fault']} | {row['final_status']} | {row['agent_runs']} ({row['baseline_runs']}) | "
                 f"{row['retries']} | {row['degraded']} |")
    rp = r["reproducibility"]
    L += ["", "## 6. Reproducibility", "", f"- Same decision analysed twice: identical simulation results: **{rp['identical_results']}**",
          f"- Representative trajectory replayed from its seed is identical: **{rp['identical_trajectory']}**",
          f"- Regenerating the scenario yields an identical event stream: **{rp['regenerated_match_identical']}**", ""]
    L += ["## 7. Monte Carlo convergence (alternative action, demo decision)", "",
          "| Rollouts | P(turnover) | 95% width | P(goal) | 95% width | Seconds (2 options) |", "|---|---|---|---|---|---|"]
    for c in r["convergence"]:
        L.append(f"| {c['rollouts']} | {pct(c['p_turnover'])} | {pct(c['turnover_ci_width'])} | {pct(c['p_goal'])} | "
                 f"{pct(c['goal_ci_width'])} | {c['seconds_for_2_options']} |")
    L += ["", "## 8. Latency (this machine, policy agents)", "", "| Metric | Count | p50 (ms) | p95 (ms) | max (ms) |",
          "|---|---|---|---|---|"]
    for k, m in r["latency"].items():
        L.append(f"| {k} | {m['count']} | {m['p50_ms']} | {m['p95_ms']} | {m['max_ms']} |")
    s = r["simulator_sanity"]
    L += ["", "## 9. Simulator sanity checks", "",
          "Unpressured central shot, goalkeeper at his modelled position (model output, not a calibrated xG):", "",
          "| Distance | Modeled P(goal) |", "|---|---|"]
    L += [f"| {k} | {pct(v)} |" for k, v in s["unpressured_central_shot_goal_probability"].items()]
    L += ["", f"Procedural play ({s['procedural_minutes']} min): pass completion {pct(s['procedural_pass_completion'])}, "
          f"{s['procedural_shots_per_10_min']} shots.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    res = asyncio.run(main(args.quick))
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "evaluation_results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (ROOT / "docs" / "evaluation_results.md").write_text(to_markdown(res), encoding="utf-8")
    print(to_markdown(res))

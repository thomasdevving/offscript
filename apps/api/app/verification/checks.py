"""Deterministic verification layer.

The Verification Agent can investigate and explain failures, but it cannot override them:
an analysis with any failing `error` check is never published as verified.
"""

from __future__ import annotations

import re

from ..models.analysis import CounterfactualAnalysis
from ..models.common import new_id, utcnow
from ..models.decisions import DecisionPoint
from ..models.match import Player
from ..models.narrative import Narrative
from ..models.simulation import SimulationConfig
from ..models.state import MatchStateSnapshot
from ..models.verification import EvidenceItem, VerificationCheck, VerificationRecord
from ..simulation.candidates import validate_candidate
from ..simulation.monte_carlo import replay_rollout, verdict_for, wilson
from .evidence import build_evidence, evidence_numbers

TOL = 1e-6
CERTAINTY_PHRASES = [
    r"would have scored", r"would have won", r"would definitely", r"definitely", r"guaranteed", r"certainly",
    r"for sure", r"proves? that", r"zou hebben gescoord", r"zou hebben gewonnen", r"zeker weten", r"gegarandeerd",
    r"bewijst dat", r"ongetwijfeld",
]
HEDGE_WORDS = ["model", "simulat", "estimate", "schatting", "simulatie"]


def _check(cid: str, name: str, ok: bool, details: str = "", severity: str = "error") -> VerificationCheck:
    return VerificationCheck(check_id=cid, name=name, passed=bool(ok), severity=severity, details=details)


def verify_analysis(
    analysis: CounterfactualAnalysis,
    decision: DecisionPoint,
    snapshot: MatchStateSnapshot,
    roster: dict[str, Player],
    reproduce: bool = True,
) -> VerificationRecord:
    checks: list[VerificationCheck] = []
    cands = analysis.candidates
    sim = analysis.simulation

    # 1. One frozen state for everything.
    same = all(c.initial_state_id == snapshot.snapshot_id for c in cands) and (
        sim is None or sim.snapshot_id == snapshot.snapshot_id) and analysis.snapshot_id == snapshot.snapshot_id
    checks.append(_check("same_snapshot", "All candidates and the simulation start from the same snapshot", same,
                         f"snapshot={snapshot.snapshot_id}"))
    # 2. No information from after the decision.
    no_future = snapshot.sim_time_ms <= decision.sim_time_ms and snapshot.source_event_id == decision.event_id
    checks.append(_check("no_future_information", "Snapshot was captured at the decision, before its outcome",
                         no_future, f"snapshot t={snapshot.sim_time_ms} ms, decision t={decision.sim_time_ms} ms"))
    # 3. Candidate validity.
    bad = []
    for c in cands:
        v = validate_candidate(snapshot, roster, c)
        if not v.ok:
            bad.append(f"{c.action_id}: {v.code}")
    checks.append(_check("candidates_valid", "Every candidate action is feasible from the snapshot", not bad,
                         "; ".join(bad) or f"{len(cands)} candidates valid"))
    actual = [c for c in cands if c.is_actual]
    checks.append(_check("actual_included", "The observed action is evaluated exactly once", len(actual) == 1,
                         f"{len(actual)} actual action(s)"))
    checks.append(_check("candidate_count", "Two to four options are compared", 2 <= len(cands) <= 4,
                         f"{len(cands)} options"))
    ids = [c.action_id for c in cands]
    checks.append(_check("unique_candidates", "No duplicated options", len(set(ids)) == len(ids)))

    if sim is None or sim.status not in ("completed", "timed_out"):
        checks.append(_check("simulation_completed", "Simulation finished", False,
                             f"status={sim.status if sim else 'missing'}"))
        return _record(analysis, checks, [])

    res = {r.action_id: r for r in sim.results}
    checks.append(_check("results_cover_candidates", "Every candidate has simulation results",
                         set(res) == set(ids), f"results={sorted(res)}"))
    ns = {r.n_rollouts for r in sim.results}
    checks.append(_check("equal_budget", "Every option used the same number of rollouts", len(ns) == 1,
                         f"rollouts={sorted(ns)}"))
    checks.append(_check("same_metric", "All options use one metric and horizon",
                         sim.config.metric == "p_goal_within_horizon",
                         f"metric={sim.config.metric}, horizon={sim.config.horizon_s}s"))
    checks.append(_check("sample_size", "At least 100 rollouts per option", min(ns or {0}) >= 100,
                         f"min rollouts={min(ns or {0})}", severity="warning"))
    checks.append(_check("complete_run", "Simulation ran to its full budget", not sim.partial,
                         "partial result (time budget reached)" if sim.partial else "complete", severity="warning"))

    # 4. Numerical consistency of every reported probability.
    numeric_issues = []
    for r in sim.results:
        counts = r.outcome_counts
        if sum(counts.values()) != r.n_rollouts:
            numeric_issues.append(f"{r.action_id}: outcome counts do not sum to n")
        if counts.get("goal", 0) != r.p_goal.successes:
            numeric_issues.append(f"{r.action_id}: goal count mismatch")
        if counts.get("turnover", 0) != r.p_turnover.successes:
            numeric_issues.append(f"{r.action_id}: turnover count mismatch")
        for name, est in (("p_goal", r.p_goal), ("p_shot", r.p_shot), ("p_turnover", r.p_turnover),
                          ("p_first_action_success", r.p_first_action_success)):
            if not (-TOL <= est.ci95_low <= est.value + TOL and est.value <= est.ci95_high + TOL
                    and est.ci95_high <= 1 + TOL):
                numeric_issues.append(f"{r.action_id}.{name}: interval does not contain estimate")
            w = wilson(est.successes, est.trials)
            if abs(w.value - est.value) > 1e-5 or abs(w.ci95_low - est.ci95_low) > 1e-5 or \
                    abs(w.ci95_high - est.ci95_high) > 1e-5:
                numeric_issues.append(f"{r.action_id}.{name}: does not match recomputed Wilson interval")
            if est.trials != r.n_rollouts:
                numeric_issues.append(f"{r.action_id}.{name}: trials != rollouts")
    checks.append(_check("probabilities_consistent", "Probabilities, counts and Wilson intervals agree",
                         not numeric_issues, "; ".join(numeric_issues[:6]) or "all consistent"))
    cmp_issues = []
    actual_id = actual[0].action_id if actual else None
    for cmp in sim.comparisons:
        if cmp.baseline_action_id != actual_id:
            cmp_issues.append(f"{cmp.action_id}: baseline is not the observed action")
        if not (cmp.diff_ci95_low - TOL <= cmp.diff_p_goal <= cmp.diff_ci95_high + TOL):
            cmp_issues.append(f"{cmp.action_id}: difference outside its interval")
        if verdict_for(cmp.diff_p_goal, cmp.diff_ci95_low, cmp.diff_ci95_high) != cmp.verdict:
            cmp_issues.append(f"{cmp.action_id}: verdict inconsistent with interval")
        if cmp.action_id in res and actual_id in res:
            expected = res[cmp.action_id].p_goal.value - res[actual_id].p_goal.value
            if abs(expected - cmp.diff_p_goal) > 1e-4:
                cmp_issues.append(f"{cmp.action_id}: difference != p_goal(alt) - p_goal(actual)")
    checks.append(_check("comparisons_consistent", "Comparisons use the observed action as baseline and agree with results",
                         not cmp_issues, "; ".join(cmp_issues) or f"{len(sim.comparisons)} comparisons consistent"))
    checks.append(_check("simulator_version", "Simulator version recorded and matches config",
                         sim.simulator_version == sim.config.simulator_version, sim.simulator_version))

    # 5. Reproducibility spot check: re-run the representative rollout of the first option.
    if reproduce and sim.results:
        r0 = sim.results[0]
        c0 = next(c for c in cands if c.action_id == r0.action_id)
        try:
            cfg = SimulationConfig.model_validate(sim.config.model_dump())
            traj = replay_rollout(snapshot, roster, c0, cfg, r0.representative_rollout, sim.simulation_run_id)
            ok = traj.outcome == r0.representative_outcome
            det = f"rollout {r0.representative_rollout} of {c0.label}: recorded={r0.representative_outcome}, replay={traj.outcome}"
        except Exception as exc:  # pragma: no cover - defensive
            ok, det = False, f"replay failed: {exc}"
        checks.append(_check("reproducible", "A recorded rollout reproduces exactly from its seed", ok, det))

    evidence = build_evidence(analysis, decision, roster)
    return _record(analysis, checks, evidence)


def _record(analysis: CounterfactualAnalysis, checks: list[VerificationCheck], evidence: list[EvidenceItem]
            ) -> VerificationRecord:
    errors = [c for c in checks if not c.passed and c.severity == "error"]
    warnings = [c for c in checks if not c.passed and c.severity == "warning"]
    status = "rejected" if errors else ("verified_with_warnings" if warnings else "verified")
    return VerificationRecord(
        verification_id=new_id("ver"),
        analysis_id=analysis.analysis_id,
        status=status,
        checks=checks,
        failures=[f"{c.check_id}: {c.details}" for c in errors],
        accepted_evidence=evidence if not errors else [],
        verified_at=utcnow().isoformat(),
    )


# ----------------------------------------------------------------------------------------
# Narrative verification
# ----------------------------------------------------------------------------------------

_PCT = re.compile(r"(?<![\w.,])([+-]?\d+(?:[.,]\d+)?)\s?%")
_NUM = re.compile(r"(?<![\w.,%])([+-]?\d+(?:[.,]\d+)?)(?![\d%])")


def extract_numbers(text: str) -> tuple[list[float], list[float]]:
    """Return (percentages, other numbers) found in text; accepts '.' and ',' decimals."""
    pcts = [float(m.group(1).replace(",", ".")) for m in _PCT.finditer(text)]
    stripped = _PCT.sub(" ", text)
    others = [float(m.group(1).replace(",", ".")) for m in _NUM.finditer(stripped)]
    return pcts, others


def _close(x: float, pool: list[float], tol: float) -> bool:
    return any(abs(abs(x) - abs(p)) <= tol for p in pool)


def verify_narrative(narrative: Narrative, evidence: list[EvidenceItem], roster: dict[str, Player],
                     allowed_player_ids: set[str]) -> list[str]:
    """Return a list of issues (empty when the narrative is fully grounded)."""
    issues: list[str] = []
    text = " ".join([narrative.headline, narrative.body, " ".join(narrative.bullets), narrative.caption or ""])
    pool = evidence_numbers(evidence)
    pct_pool = [it_value * 100 for it_value in (float(it.value) for it in evidence
                                                if it.unit == "%" and isinstance(it.value, int | float))]
    pp_pool = [float(it.value) for it in evidence if it.unit == "pp"]
    pcts, others = extract_numbers(text)
    for p in pcts:
        if not _close(p, pct_pool + pp_pool, 0.051 if p != round(p) else 0.51):
            issues.append(f"Unsupported percentage {p:g}% (no matching evidence field)")
    for n in others:
        if abs(n) <= 1 and n == round(n):
            continue  # "one", "1 of", ordinal noise
        if not _close(n, pool + pp_pool, 0.051 if n != round(n) else 0.5):
            issues.append(f"Unsupported number {n:g} (no matching evidence field)")
    low = text.lower()
    for phrase in CERTAINTY_PHRASES:
        if re.search(phrase, low):
            issues.append(f"Overclaiming language: '{phrase}'")
    for pid, p in roster.items():
        for nm in {p.name, p.short_name}:
            # Whole-word match: "Quist" must not match inside "Thornquist".
            if len(nm) > 3 and pid not in allowed_player_ids and re.search(rf"(?<![\w-]){re.escape(nm.lower())}(?![\w-])", low):
                issues.append(f"Mentions {p.name}, who is not part of this decision")
    refs = {it.ref for it in evidence}
    unknown = [r for r in narrative.evidence_refs if r not in refs]
    if unknown:
        issues.append(f"Unknown evidence references: {unknown[:4]}")
    if narrative.audience in ("casual", "analyst") and not any(h in low for h in HEDGE_WORDS):
        issues.append("Missing model qualifier (e.g. 'under our simulation model')")
    if narrative.audience == "broadcaster" and narrative.caption and len(narrative.caption) > 120:
        issues.append("Broadcast caption longer than 120 characters")
    return issues

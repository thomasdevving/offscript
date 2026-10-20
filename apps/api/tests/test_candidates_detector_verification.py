import pytest

from app.analytics.detector import DecisionDetector, DetectorConfig, detect_all
from app.models.analysis import CounterfactualAnalysis, ModelInfo
from app.models.decisions import CandidateAction
from app.models.narrative import Narrative
from app.models.simulation import SimulationConfig, SimulationRun
from app.models.workflow import AnalysisWorkflowState
from app.simulation.candidates import actual_action_from_event, generate_candidates, validate_candidate
from app.simulation.monte_carlo import evaluate_actions
from app.synthetic_data.scenarios import generate
from app.verification.checks import extract_numbers, verify_analysis, verify_narrative
from app.verification.evidence import build_evidence


def _cand(snap, **kw):
    base = dict(action_id="x", action_type="pass", actor_id=snap.ball.possessor_id, initial_state_id=snap.snapshot_id)
    base.update(kw)
    return CandidateAction(**base)


def test_validation_rejects_infeasible_actions(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    roster = demo_match.roster
    bench_same_team = next(p for p in snap.off_pitch_player_ids if roster[p].team_id == snap.possession_team_id)
    opponent = next(p.player_id for p in snap.players if p.team_id != snap.possession_team_id)
    teammate = next(p.player_id for p in snap.players
                    if p.team_id == snap.possession_team_id and p.player_id != snap.ball.possessor_id)
    cases = {
        "PLAYER_NOT_ON_PITCH": _cand(snap, target_player_id=bench_same_team),
        "OPPONENT_TARGET": _cand(snap, target_player_id=opponent),
        "SELF_PASS": _cand(snap, target_player_id=snap.ball.possessor_id),
        "UNKNOWN_PLAYER": _cand(snap, target_player_id="Z99"),
        "MISSING_TARGET": _cand(snap),
        "TARGET_OFF_PITCH": _cand(snap, action_type="dribble", target_x=-20, target_y=30),
        "SNAPSHOT_MISMATCH": _cand(snap, target_player_id=teammate, initial_state_id="other"),
        "ACTOR_NOT_IN_POSSESSION": _cand(snap, actor_id=teammate, action_type="shoot"),
    }
    for code, c in cases.items():
        v = validate_candidate(snap, roster, c)
        assert not v.ok and v.code == code, (code, v)
    assert validate_candidate(snap, roster, _cand(snap, target_player_id=teammate)).ok


def test_generator_offers_pass_alternatives_from_the_same_snapshot(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    cands = generate_candidates(snap, demo_match.roster)
    assert any(c.action_type == "pass" for c in cands)
    assert any(c.action_type == "shoot" for c in cands)
    assert all(c.initial_state_id == snap.snapshot_id for c in cands)
    assert all(validate_candidate(snap, demo_match.roster, c).ok for c in cands)


def test_detector_finds_labelled_scenario_decisions(definitions):
    for sid in ("shoot_vs_pass", "risky_through_ball", "defensive_pressure"):
        m = generate(definitions[sid])
        decisions, det = detect_all(m.info.match_id, m.events, m.roster, m.snapshots)
        found = {d.event_id for d in decisions}
        assert set(m.decision_event_ids) <= found, sid
        # Scripted build-up actions are never reported as decisions.
        assert not (found & set(m.scripted_event_ids))


def test_detector_rate_limits(definitions):
    m = generate(definitions["procedural_segment"])
    strict, det = detect_all(m.info.match_id, m.events, m.roster, m.snapshots,
                             DetectorConfig(min_gap_ms=60_000, high_priority=1.1))
    gaps = [b.sim_time_ms - a.sim_time_ms for a, b in zip(strict, strict[1:], strict=False)]
    assert all(g >= 6_000 for g in gaps)
    assert any(s["reason"] == "rate_limited" for s in det.suppressed)


def test_detector_uses_only_pre_decision_snapshot(demo_match):
    det = DecisionDetector(demo_match.info.match_id, demo_match.roster, demo_match.snapshots)
    for e in demo_match.events:
        for dp in det.on_event(e):
            snap = demo_match.snapshots[dp.snapshot_id]
            assert snap.sim_time_ms <= dp.sim_time_ms
            assert snap.source_event_id == dp.event_id


@pytest.fixture(scope="module")
def verified_analysis(demo_match):
    decisions, _ = detect_all(demo_match.info.match_id, demo_match.events, demo_match.roster, demo_match.snapshots)
    dp = next(d for d in decisions if d.event_id in demo_match.decision_event_ids)
    snap = demo_match.snapshots[dp.snapshot_id]
    alts = [c for c in generate_candidates(snap, demo_match.roster) if c.action_type == "pass"][:2]
    cands = [dp.actual_action] + alts
    cfg = SimulationConfig(rollouts=100, seed=snap.seed)
    out = evaluate_actions(snap, demo_match.roster, cands, cfg)
    sim = SimulationRun(simulation_run_id="sim-test", analysis_id="a", snapshot_id=snap.snapshot_id, config=cfg,
                        status="completed", results=out.results, comparisons=out.comparisons, ranking=out.ranking,
                        overall_verdict=out.overall_verdict)
    a = CounterfactualAnalysis(
        analysis_id="a", match_id=dp.match_id, decision_point_id=dp.decision_point_id, snapshot_id=snap.snapshot_id,
        correlation_id="c", created_at="now", candidates=cands, actual_action_id=dp.actual_action.action_id,
        simulation=sim, workflow=AnalysisWorkflowState(analysis_id="a", match_id=dp.match_id,
                                                       snapshot_id=snap.snapshot_id,
                                                       decision_point_id=dp.decision_point_id, correlation_id="c"),
        model=ModelInfo(agent_mode="policy", provider="test"))
    return a, dp, snap


def test_verification_accepts_consistent_analysis(verified_analysis, demo_match):
    a, dp, snap = verified_analysis
    rec = verify_analysis(a, dp, snap, demo_match.roster)
    assert rec.status in ("verified", "verified_with_warnings"), rec.failures
    assert rec.accepted_evidence
    assert any(c.check_id == "reproducible" and c.passed for c in rec.checks)


def test_verification_rejects_tampered_numbers(verified_analysis, demo_match):
    a, dp, snap = verified_analysis
    bad = a.model_copy(deep=True)
    r = bad.simulation.results[1]
    r.p_goal = r.p_goal.model_copy(update={"value": min(1.0, r.p_goal.value + 0.2)})
    rec = verify_analysis(bad, dp, snap, demo_match.roster, reproduce=False)
    assert rec.status == "rejected"
    assert any("probabilities_consistent" in f for f in rec.failures)
    assert not rec.accepted_evidence


def test_verification_rejects_candidate_from_other_snapshot(verified_analysis, demo_match):
    a, dp, snap = verified_analysis
    bad = a.model_copy(deep=True)
    bad.candidates[1] = bad.candidates[1].model_copy(update={"initial_state_id": "elsewhere"})
    rec = verify_analysis(bad, dp, snap, demo_match.roster, reproduce=False)
    assert rec.status == "rejected"
    assert any(f.startswith("same_snapshot") for f in rec.failures)


def _nar(body, audience="casual", language="en", caption=None):
    return Narrative(narrative_id="n", analysis_id="a", audience=audience, language=language, headline="H",
                     body=body, caption=caption, generated_by="test", is_live_model_output=False, created_at="")


def test_narrative_grounding(verified_analysis, demo_match):
    a, dp, snap = verified_analysis
    ev = build_evidence(a, dp, demo_match.roster)
    allowed = {dp.actor_id} | {c.target_player_id for c in a.candidates if c.target_player_id}
    p = a.simulation.results[0].p_goal.value
    good = f"Under our simulation model the shot scored in {p * 100:.1f}% of 100 simulations."
    assert verify_narrative(_nar(good), ev, demo_match.roster, allowed) == []
    nl = f"Volgens ons simulatiemodel scoorde het schot in {p * 100:.1f}% van 100 simulaties.".replace(".", ",", 1)
    nl = nl.replace(f"{p * 100:.1f}".replace(".", ","), f"{p * 100:.1f}".replace(".", ","))
    assert verify_narrative(_nar(nl, language="nl"), ev, demo_match.roster, allowed) == []
    wrong = good.replace(f"{p * 100:.1f}%", f"{p * 100 + 17.3:.1f}%")
    assert any("Unsupported percentage" in i for i in verify_narrative(_nar(wrong), ev, demo_match.roster, allowed))
    over = "Under our simulation model the pass would have scored."
    assert any("Overclaiming" in i for i in verify_narrative(_nar(over), ev, demo_match.roster, allowed))
    outsider = next(p for p in demo_match.roster.values() if p.player_id not in allowed and p.team_id == "NVA")
    foreign = f"Under our simulation model {outsider.name} was the key."
    assert any("not part of this decision" in i for i in
               verify_narrative(_nar(foreign), ev, demo_match.roster, allowed))
    nohedge = "The pass was better."
    assert any("qualifier" in i for i in verify_narrative(_nar(nohedge), ev, demo_match.roster, allowed))


def test_number_extraction_handles_both_decimal_styles():
    pcts, others = extract_numbers("2,0% versus 3.5% after 200 sims and 23 m")
    assert pcts == [2.0, 3.5]
    assert others == [200.0, 23.0]


def test_actual_action_is_rebuilt_from_snapshot(demo_match, demo_decision_snapshot):
    ev, snap = demo_decision_snapshot
    a = actual_action_from_event(snap, demo_match.roster, ev.event_type.value, None, None, None)
    assert a.is_actual and a.initial_state_id == snap.snapshot_id and a.action_type == "shoot"


def test_name_check_uses_whole_words(verified_analysis, demo_match):
    a, dp, snap = verified_analysis
    ev = build_evidence(a, dp, demo_match.roster)
    roster = demo_match.roster
    # Thornquist (A07) is allowed; Quist (H06) is not, but "Quist" is a substring of "Thornquist".
    allowed = {dp.actor_id, "A07"} - {"H06"}
    ok = "Under our simulation model Thornquist closed the lane."
    assert not any("not part" in i for i in verify_narrative(_nar(ok), ev, roster, allowed))
    bad = "Under our simulation model Quist closed the lane."
    assert any("Sander Quist" in i for i in verify_narrative(_nar(bad), ev, roster, allowed))

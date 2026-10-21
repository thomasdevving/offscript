"""Decision Value Added: signs, intervals, aggregation and the minimum-sample rule."""

import math
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.analysis import CounterfactualAnalysis, ModelInfo
from app.models.decisions import CandidateAction, DecisionPoint
from app.models.simulation import ActionResult, PairwiseComparison, SimulationConfig, SimulationRun
from app.models.workflow import AnalysisWorkflowState
from app.services.decision_value import MIN_DECISIONS, Z95, aggregate, decision_value, latest_verified
from app.simulation.monte_carlo import wilson


def _cand(aid: str, actual: bool = False) -> CandidateAction:
    return CandidateAction(action_id=aid, action_type="pass", actor_id="H10", initial_state_id="s", is_actual=actual,
                           label=f"{aid} (actual)" if actual else aid)


def _result(aid: str, goals: int, n: int = 200) -> ActionResult:
    e = wilson(goals, n)
    return ActionResult(action_id=aid, n_rollouts=n, p_goal=e, p_shot=e, p_turnover=e, p_first_action_success=e,
                        mean_progression_m=0.0, outcome_distribution={}, outcome_counts={}, representative_rollout=0,
                        representative_outcome="goal")


def _analysis(goals: dict[str, int], diffs: dict[str, tuple[float, float, float]], status: str = "verified",
              aid: str = "a1", dp: str = "dp1", n: int = 200, created: str = "2026-01-01T00:00:00") -> CounterfactualAnalysis:
    """`goals` lists the chosen action first; `diffs` maps alternative -> (alt - chosen, lo, hi)."""
    ids = list(goals)
    comps = [PairwiseComparison(action_id=k, baseline_action_id=ids[0], diff_p_goal=d, diff_ci95_low=lo,
                                diff_ci95_high=hi, paired=True, verdict="inconclusive") for k, (d, lo, hi) in diffs.items()]
    sim = SimulationRun(simulation_run_id="sim", analysis_id=aid, snapshot_id="s", config=SimulationConfig(rollouts=n),
                        status="completed", results=[_result(k, g, n) for k, g in goals.items()], comparisons=comps)
    return CounterfactualAnalysis(
        analysis_id=aid, match_id="m", decision_point_id=dp, snapshot_id="s", correlation_id="c", status=status,
        created_at=created, candidates=[_cand(k, i == 0) for i, k in enumerate(ids)], actual_action_id=ids[0],
        simulation=sim, workflow=AnalysisWorkflowState(analysis_id=aid, match_id="m", snapshot_id="s",
                                                       decision_point_id=dp, correlation_id="c"),
        model=ModelInfo(agent_mode="policy", provider="deterministic-policy"))


def _decision(dp: str = "dp1", actor: str = "H10", team: str = "HCF") -> DecisionPoint:
    return DecisionPoint.model_construct(decision_point_id=dp, match_clock_ms=60_000, actor_id=actor,
                                         actor_name="Ravi Castellane", team_id=team)


def test_better_alternative_gives_negative_dva_with_mapped_interval():
    a = _analysis({"act": 10, "alt1": 30, "alt2": 14}, {"alt1": (0.1, 0.06, 0.14), "alt2": (0.02, -0.01, 0.05)})
    it = decision_value(a, _decision())
    assert it.best_action_id == "alt1" and it.best_alternative_action_id == "alt1"
    assert it.dva == pytest.approx(-0.1) and it.paired_diff == pytest.approx(-0.1)
    assert (it.ci95_low, it.ci95_high) == (pytest.approx(-0.14), pytest.approx(-0.06))
    assert it.clearly_better_alternative and it.alternatives == 2
    assert it.chosen_p_goal == pytest.approx(0.05) and it.best_p_goal == pytest.approx(0.15)


def test_chosen_action_best_gives_zero_and_interval_capped_at_zero():
    a = _analysis({"act": 30, "alt": 20}, {"alt": (-0.05, -0.09, 0.01)})
    it = decision_value(a, _decision())
    assert it.best_action_id == "act" and it.best_alternative_action_id == "alt"
    assert it.dva == 0.0 and math.copysign(1, it.dva) == 1  # no "-0.0"
    assert it.paired_diff == pytest.approx(0.05)
    # Paired interval of chosen - alt is [-0.01, 0.09]; min(0, .) maps it to [-0.01, 0].
    assert (it.ci95_low, it.ci95_high) == (pytest.approx(-0.01), 0.0)
    assert not it.clearly_better_alternative


def test_overlapping_alternative_keeps_point_estimate_and_zero_upper_bound():
    it = decision_value(_analysis({"act": 20, "alt": 24}, {"alt": (0.02, -0.03, 0.07)}), _decision())
    assert it.dva == pytest.approx(-0.02)
    assert (it.ci95_low, it.ci95_high) == (pytest.approx(-0.07), 0.0)
    assert it.ci95_low <= it.dva <= it.ci95_high <= 0.0
    assert not it.clearly_better_alternative


def test_unverified_or_alternative_free_analyses_do_not_count():
    assert decision_value(_analysis({"act": 1, "alt": 2}, {"alt": (0.005, 0, 0.01)}, status="failed"), _decision()) is None
    assert decision_value(_analysis({"act": 1}, {}), _decision()) is None


def test_aggregate_sum_mean_and_quadrature_interval():
    items = [decision_value(_analysis({"act": 10, "alt": 30}, {"alt": (0.1, 0.06, 0.14)}, dp=f"d{i}"),
                            _decision(f"d{i}")) for i in range(2)]
    items.append(decision_value(_analysis({"act": 30, "alt": 20}, {"alt": (-0.05, -0.09, 0.01)}, dp="d2"),
                                _decision("d2")))
    agg = aggregate(items, "player", "H10", "Ravi Castellane", "HCF")
    assert agg.enough_decisions and agg.n_decisions == 3 and agg.clear_misses == 2
    assert agg.dva_sum == pytest.approx(-0.2) and agg.dva_mean == pytest.approx(-0.2 / 3, abs=1e-6)
    se = math.sqrt(2 * (0.08 / (2 * Z95)) ** 2 + (0.1 / (2 * Z95)) ** 2)
    assert agg.dva_sum_ci95_low == pytest.approx(-0.2 - Z95 * se, abs=1e-6)
    assert agg.dva_sum_ci95_high == pytest.approx(-0.2 + Z95 * se, abs=1e-6)
    assert agg.dva_mean_ci95_low == pytest.approx(agg.dva_sum_ci95_low / 3, abs=1e-6)


def test_aggregate_upper_end_capped_at_zero():
    items = [decision_value(_analysis({"act": 20, "alt": 21}, {"alt": (0.005, -0.03, 0.04)}, dp=f"d{i}"),
                            _decision(f"d{i}")) for i in range(4)]
    agg = aggregate(items, "team", "HCF", "Harbour City FC", "HCF")
    assert agg.dva_sum == pytest.approx(-0.02)
    assert agg.dva_sum_ci95_high == 0.0 and agg.dva_sum_ci95_low < agg.dva_sum


def test_minimum_sample_withholds_numbers():
    items = [decision_value(_analysis({"act": 10, "alt": 30}, {"alt": (0.1, 0.06, 0.14)}, dp=f"d{i}"),
                            _decision(f"d{i}")) for i in range(MIN_DECISIONS - 1)]
    agg = aggregate(items, "player", "H10", "Ravi Castellane")
    assert not agg.enough_decisions and agg.n_decisions == MIN_DECISIONS - 1
    assert agg.dva_sum is None and agg.dva_mean is None and agg.dva_sum_ci95_low is None
    assert agg.clear_misses == MIN_DECISIONS - 1
    assert aggregate([], "match", "m", "m").enough_decisions is False
    assert aggregate(items, "player", "H10", "x", min_decisions=1).dva_sum == pytest.approx(-0.1 * len(items))


def test_latest_verified_prefers_more_rollouts_and_skips_faults():
    small = _analysis({"act": 1, "alt": 2}, {"alt": (0.01, 0, 0.02)}, aid="small", n=100, created="2026-02-01")
    big = _analysis({"act": 1, "alt": 2}, {"alt": (0.005, 0, 0.01)}, aid="big", n=200, created="2026-01-01")
    faulty = _analysis({"act": 1, "alt": 2}, {"alt": (0.005, 0, 0.01)}, aid="faulty", n=500)
    faulty.fault_injection = ["simulation_timeout"]
    other = _analysis({"act": 1, "alt": 2}, {"alt": (0.005, 0, 0.01)}, aid="other", dp="not-detected")
    chosen = latest_verified([small, big, faulty, other], {"dp1"})
    assert list(chosen) == ["dp1"] and chosen["dp1"].analysis_id == "big"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.config import REPO_ROOT, Settings

    s = Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp_path_factory.mktemp("dva"),
                 scenarios_dir=REPO_ROOT / "scenarios", default_rollouts=60)
    with TestClient(create_app(s, preload=["shoot_vs_pass"])) as c:
        yield c


def test_decision_value_endpoint_analyses_on_demand(client):
    mid = next(x["match_id"] for x in client.get("/api/scenarios").json() if x["scenario_id"] == "shoot_vs_pass")
    r = client.get(f"/api/matches/{mid}/decision-value").json()
    assert r["decisions_analysed"] == 0 and r["decisions"] == [] and r["match"]["enough_decisions"] is False
    assert r["decisions_detected"] >= 1 and "Decision Value Added" in r["method"]
    started = client.post(f"/api/matches/{mid}/decision-value/analyze")
    assert started.status_code == 202
    t0 = time.time()
    while time.time() - t0 < 120:
        r = client.get(f"/api/matches/{mid}/decision-value?min_decisions=1").json()
        if r["decisions_pending"] == 0 and r["decisions_analysed"] == r["decisions_detected"]:
            break
        time.sleep(0.3)
    assert r["decisions_analysed"] == r["decisions_detected"]
    for d in r["decisions"]:
        assert d["ci95_low"] <= d["dva"] <= d["ci95_high"] <= 0.0
    assert r["match"]["enough_decisions"] and r["match"]["dva_sum"] == pytest.approx(sum(d["dva"] for d in r["decisions"]))
    assert {p["key"] for p in r["players"]} == {d["player_id"] for d in r["decisions"]}
    # A second call starts nothing new.
    again = client.post(f"/api/matches/{mid}/decision-value/analyze").json()
    assert again["decisions_pending"] == 0
    assert client.get("/api/matches/nope/decision-value").status_code == 404
    assert client.get(f"/api/matches/{mid}/decision-value?min_decisions=0").status_code == 422

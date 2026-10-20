import math

import numpy as np
import pytest

from app.models.simulation import SimulationConfig
from app.simulation.candidates import actual_action_from_event, generate_candidates
from app.simulation.monte_carlo import evaluate_actions, paired_difference, verdict_for, wilson


def test_wilson_interval_known_values():
    w = wilson(10, 100)
    assert w.value == pytest.approx(0.1)
    assert w.ci95_low == pytest.approx(0.0552, abs=5e-4)
    assert w.ci95_high == pytest.approx(0.1744, abs=5e-4)
    z = wilson(0, 200)
    assert z.ci95_low == 0 and 0 < z.ci95_high < 0.02
    assert wilson(0, 0).ci95_high == 1.0


def test_paired_difference_and_verdicts():
    a = np.array([1, 0, 1, 1, 0, 1] * 50, dtype=bool)
    b = np.array([0, 0, 1, 0, 0, 0] * 50, dtype=bool)
    d, lo, hi = paired_difference(a, b)
    assert d == pytest.approx(0.5) and lo > 0
    assert verdict_for(d, lo, hi) == "more_promising"
    assert verdict_for(-0.1, -0.2, -0.01) == "less_promising"
    assert verdict_for(0.0, -0.01, 0.01) == "similar"
    assert verdict_for(0.02, -0.03, 0.07) == "inconclusive"


@pytest.fixture(scope="module")
def setup(demo_match, demo_decision_snapshot):
    ev, snap = demo_decision_snapshot
    actual = actual_action_from_event(snap, demo_match.roster, ev.event_type.value, ev.details.intended_receiver_id,
                                      ev.end_x, ev.end_y)
    alts = [c for c in generate_candidates(snap, demo_match.roster) if c.action_type == "pass"][:2]
    return snap, demo_match.roster, [actual] + alts


def test_evaluation_is_reproducible_and_fair(setup):
    snap, roster, actions = setup
    cfg = SimulationConfig(rollouts=60, seed=snap.seed)
    a = evaluate_actions(snap, roster, actions, cfg)
    b = evaluate_actions(snap, roster, actions, cfg)
    assert [r.model_dump() for r in a.results] == [r.model_dump() for r in b.results]
    assert {r.n_rollouts for r in a.results} == {60}
    assert all(c.baseline_action_id == actions[0].action_id for c in a.comparisons)
    for r in a.results:
        for est in (r.p_goal, r.p_shot, r.p_turnover, r.p_first_action_success):
            assert 0 <= est.ci95_low <= est.value <= est.ci95_high <= 1
        assert sum(r.outcome_counts.values()) == r.n_rollouts
        assert sum(r.outcome_distribution.values()) == pytest.approx(1.0, abs=1e-5)  # values rounded to 6 dp


def test_more_rollouts_narrow_the_interval(setup):
    snap, roster, actions = setup
    small = evaluate_actions(snap, roster, actions[:2], SimulationConfig(rollouts=40, seed=snap.seed))
    big = evaluate_actions(snap, roster, actions[:2], SimulationConfig(rollouts=320, seed=snap.seed))

    def width(out):
        r = out.results[1].p_turnover
        return r.ci95_high - r.ci95_low

    assert width(big) < width(small)
    # Roughly 1/sqrt(n) scaling (factor sqrt(8) ~ 2.8, allow slack).
    assert width(small) / width(big) > 1.8


def test_time_budget_returns_partial_but_fair_result(setup):
    snap, roster, actions = setup
    out = evaluate_actions(snap, roster, actions, SimulationConfig(rollouts=500, seed=snap.seed, time_budget_s=0.2))
    assert out.partial and out.timed_out
    ns = {r.n_rollouts for r in out.results}
    assert len(ns) == 1 and next(iter(ns)) < 500


def test_cancellation(setup):
    import threading

    snap, roster, actions = setup
    ev = threading.Event()
    ev.set()
    out = evaluate_actions(snap, roster, actions, SimulationConfig(rollouts=100, seed=snap.seed), cancel=ev)
    assert out.cancelled and out.completed_rollouts == 0


def test_common_random_numbers_reduce_comparison_variance(setup):
    """Paired (CRN) comparison of an action with itself is exactly zero; independent streams are not."""
    snap, roster, actions = setup
    a = actions[1]
    clone = a.model_copy(update={"action_id": a.action_id + "-clone"})
    crn = evaluate_actions(snap, roster, [a, clone], SimulationConfig(rollouts=80, seed=snap.seed),
                           baseline_action_id=a.action_id)
    ind = evaluate_actions(snap, roster, [a, clone], SimulationConfig(rollouts=80, seed=snap.seed,
                                                                     common_random_numbers=False),
                           baseline_action_id=a.action_id)
    c_crn, c_ind = crn.comparisons[0], ind.comparisons[0]
    assert c_crn.diff_p_turnover == 0 and c_crn.diff_p_turnover_ci95_high == 0
    assert (c_ind.diff_p_turnover_ci95_high - c_ind.diff_p_turnover_ci95_low) > 0


def test_pressure_reduces_pass_success_in_controlled_scenario(setup):
    """Adding a defender into the passing lane lowers the simulated completion rate."""
    snap, roster, actions = setup
    target = actions[1]
    base = evaluate_actions(snap, roster, [actions[0], target], SimulationConfig(rollouts=80, seed=3))
    carrier = snap.player(snap.ball.possessor_id)
    # Move the nearest outfield defender onto the middle of the passing lane.
    mid = ((carrier.x + target.target_x) / 2, (carrier.y + target.target_y) / 2)
    defenders = [p for p in snap.players if p.team_id != snap.possession_team_id]
    d = min(defenders, key=lambda p: math.hypot(p.x - mid[0], p.y - mid[1]) if p.player_id != "A01" else 1e9)
    players = [p.model_copy(update={"x": mid[0], "y": mid[1], "vx": 0.0, "vy": 0.0}) if p.player_id == d.player_id
               else p for p in snap.players]
    pressured = snap.model_copy(update={"players": players})
    out = evaluate_actions(pressured, roster, [actions[0], target], SimulationConfig(rollouts=80, seed=3))
    assert out.results[1].p_first_action_success.value < base.results[1].p_first_action_success.value

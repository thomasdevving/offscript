"""Property tests of the deterministic simulator (internal consistency, not real-world accuracy)."""

import numpy as np
import pytest

from app.simulation import geometry as g
from app.simulation.engine import (
    Engine,
    EngineState,
    Profile,
    RolloutRng,
    goalkeeper_target,
    interception_probability,
)
from app.simulation.rollout import TERMINATION_RULES, resolve_candidate, run_rollout, state_from_snapshot


def make_state(att: list[tuple[float, float]], deff: list[tuple[float, float]], gk=True) -> EngineState:
    profs, pos = [], []
    for i, p in enumerate(att):
        profs.append(Profile(f"A{i}", "T", f"a{i}", "ST" if i else "CM", 9.0, 0.25, 0.8, 0.7, 0.7))
        pos.append(p)
    for i, p in enumerate(deff):
        profs.append(Profile(f"D{i}", "U", f"d{i}", "CB", 8.5, 0.25, 0.6, 0.2, 0.3))
        pos.append(p)
    if gk:
        profs.append(Profile("GK", "U", "gk", "GK", 7.3, 0.23, 0.6, 0.1, 0.2))
        pos.append(tuple(goalkeeper_target(np.array(att[0], dtype=float))))
    pos = np.array(pos, dtype=float)
    is_att = np.array([i < len(att) for i in range(len(profs))])
    return EngineState(profiles=profs, is_att=is_att, pos=pos, vel=np.zeros_like(pos), anchors=pos.copy(),
                       ball=pos[0].copy(), ball_ref=pos[0].copy(), carrier=0, t=0.0, direction=1, att_team="T",
                       def_team="U")


def test_open_pass_is_easier_than_pass_through_a_defender():
    e = Engine()
    open_ = make_state([(50, 34), (65, 34)], [(60, 55)])
    blocked = make_state([(50, 34), (65, 34)], [(57.5, 34.5)])
    assert e.expected_pass(open_, 0, 1)["completion_est"] > 0.9
    assert e.expected_pass(blocked, 0, 1)["completion_est"] < 0.3


def test_more_defenders_reduce_pass_completion_monotonically():
    e = Engine()
    comps = []
    for k in range(4):
        defenders = [(56 + 2 * i, 36.5 + 0.5 * i) for i in range(k)] + [(30, 60)]
        comps.append(e.expected_pass(make_state([(50, 34), (66, 34)], defenders), 0, 1)["completion_est"])
    assert all(a >= b - 1e-9 for a, b in zip(comps, comps[1:], strict=False))
    assert comps[0] > comps[-1]


def test_interception_probability_is_monotone_in_margin():
    m = np.linspace(-1, 1, 21)
    p = interception_probability(m)
    assert np.all(np.diff(p) > 0) and p.min() >= 0 and p.max() <= 0.85 + 1e-9


def test_shot_probability_falls_with_distance_and_blockers():
    e = Engine()
    near = e.shot_probability(make_state([(95, 34)], []), 0, 800)
    far = e.shot_probability(make_state([(80, 34)], []), 0, 800)
    blocked = e.shot_probability(make_state([(80, 34)], [(82.5, 34)]), 0, 800)
    assert 0 <= blocked < far < near <= 1


def test_dribble_success_lower_under_pressure():
    e = Engine()
    free = e.expected_dribble(make_state([(60, 34)], [(40, 10)]), 0, np.array([68.0, 34.0]))
    pressed = e.expected_dribble(make_state([(60, 34)], [(63, 34), (64, 37)]), 0, np.array([68.0, 34.0]))
    assert free["success_est"] > pressed["success_est"]


def _max_speed_violation(frames, vmax: dict[str, float], dt: float = 0.1) -> float:
    worst = 0.0
    for a, b in zip(frames, frames[1:], strict=False):
        step = (b.t_ms - a.t_ms) / 1000
        if step <= 0:
            continue
        for pid, (x, y) in b.players.items():
            ax, ay = a.players[pid]
            speed = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5 / step
            worst = max(worst, speed - vmax[pid])
    return worst


def test_rollouts_respect_speed_bounds_and_pitch(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    base = state_from_snapshot(snap, demo_match.roster)
    vmax = {p.player_id: p.max_speed for p in base.profiles}
    from app.simulation.candidates import generate_candidates
    for cand in generate_candidates(snap, demo_match.roster)[:4]:
        act = resolve_candidate(base, snap, cand)
        for i in range(5):
            summary, frames, _ = run_rollout(base, act, RolloutRng(snap.seed, i), 10.0, record=True)
            assert frames, "a recorded rollout must have frames"
            assert _max_speed_violation(frames, vmax) < 0.15  # positions are rounded to 1 cm
            for f in frames:
                bx, by, _ = f.ball
                assert g.in_bounds(bx, by, margin=1.0)
            assert summary.outcome in ("goal", "saved", "blocked", "off_target", "turnover", "out_of_play", "retained")
            assert summary.t_end <= 10.0 + 1e-9


def test_observed_timeline_has_no_teleports(demo_match):
    vmax = {p.player_id: p.max_speed_mps * 1.0 for p in demo_match.roster.values()}
    assert _max_speed_violation(demo_match.frames, vmax) < 0.15


def test_rollout_is_reproducible_for_fixed_seed(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    base = state_from_snapshot(snap, demo_match.roster)
    from app.simulation.candidates import generate_candidates
    cand = generate_candidates(snap, demo_match.roster)[0]
    act = resolve_candidate(base, snap, cand)
    a = run_rollout(base, act, RolloutRng(snap.seed, 7), 10.0, record=True)
    b = run_rollout(base, act, RolloutRng(snap.seed, 7), 10.0, record=True)
    assert a[0] == b[0]
    assert [f.model_dump() for f in a[1]] == [f.model_dump() for f in b[1]]


def test_rollouts_never_modify_the_base_state(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    base = state_from_snapshot(snap, demo_match.roster)
    before = base.pos.copy(), base.vel.copy(), base.ball.copy()
    from app.simulation.candidates import generate_candidates
    cand = generate_candidates(snap, demo_match.roster)[0]
    run_rollout(base, resolve_candidate(base, snap, cand), RolloutRng(1, 1), 10.0)
    assert np.array_equal(before[0], base.pos) and np.array_equal(before[1], base.vel)
    assert np.array_equal(before[2], base.ball)


def test_defenders_react_differently_to_different_actions(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    base = state_from_snapshot(snap, demo_match.roster)
    from app.simulation.candidates import generate_candidates
    cands = generate_candidates(snap, demo_match.roster)
    passes = [c for c in cands if c.action_type == "pass"][:2]
    frames = []
    for c in passes:
        _, f, _ = run_rollout(base, resolve_candidate(base, snap, c), RolloutRng(snap.seed, 0), 10.0, record=True)
        frames.append(f)
    defenders = [p.player_id for p in snap.players if p.team_id != snap.possession_team_id]
    idx = min(8, len(frames[0]) - 1, len(frames[1]) - 1)
    moved = [abs(frames[0][idx].players[d][0] - frames[1][idx].players[d][0]) +
             abs(frames[0][idx].players[d][1] - frames[1][idx].players[d][1]) for d in defenders]
    assert max(moved) > 0.5, "defenders should respond to where the ball is played"


def test_termination_rules_documented():
    for word in ("goal", "turnover", "horizon", "rebounds"):
        assert word in TERMINATION_RULES


@pytest.mark.parametrize("direction", [1, -1])
def test_snapshot_conversion_handles_both_attack_directions(demo_match, demo_decision_snapshot, direction):
    _, snap = demo_decision_snapshot
    st = state_from_snapshot(snap, demo_match.roster)
    # The decision is in the second half (home attacks -x), but in the attack frame the
    # carrier is always in the attacking half near x=82 (towards x=105).
    assert st.direction == snap.attack_direction[snap.possession_team_id]
    assert st.pos[st.carrier][0] > 70
    assert direction in (1, -1)


def test_batched_and_single_pass_models_agree():
    e = Engine()
    st = make_state([(50, 34), (65, 34), (60, 50)], [(57.5, 36.0), (62, 45), (70, 30)])
    react = st.react.copy()
    ends = np.array([e.lead_point(st, 1), e.lead_point(st, 2)])
    batch = e.pass_batch(st, np.array([1, 2]), ends, react)
    for k, j in enumerate((1, 2)):
        single = e._lane_assessment(st, 0, j, ends[k], react)
        assert single["completion_est"] == pytest.approx(float(batch["completion_est"][k]), rel=1e-9)

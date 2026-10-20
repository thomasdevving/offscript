"""Football Multiverse: defensive strategies, successor states, adversarial planning, branching service."""

import asyncio

import numpy as np
import pytest

from app.agents.runner import ChatClientProvider
from app.models.multiverse import (
    ActionSpec,
    BranchActionRequest,
    DefensiveAssignment,
    DefensiveStrategy,
    SessionCreate,
)
from app.models.simulation import SimulationConfig
from app.multiverse.core import CellEvaluator, realize_transition, select_rollout, snapshot_digest
from app.multiverse.service import MultiverseError, MultiverseService
from app.simulation.candidates import actual_action_from_event, generate_candidates
from app.simulation.defense import BASELINE, build_runtime, generate_defensive_options, validate_strategy
from app.simulation.monte_carlo import evaluate_actions

# ------------------------------------------------------------------------------------ defence

def _strat(*assignments, style="press"):
    return DefensiveStrategy(strategy_id="x", style=style, label="x", assignments=list(assignments))


def test_defensive_validation(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    r = demo_match.roster
    att = snap.possession_team_id
    defender = min((p for p in snap.players if p.team_id != att and r[p.player_id].role != "GK"),
                   key=lambda p: (p.x - snap.ball.x) ** 2 + (p.y - snap.ball.y) ** 2).player_id
    gk = next(p.player_id for p in snap.players if p.team_id != att and r[p.player_id].role == "GK")
    attacker = next(p.player_id for p in snap.players if p.team_id == att)
    far = max((p for p in snap.players if p.team_id != att and r[p.player_id].role != "GK"),
              key=lambda p: (p.x - snap.ball.x) ** 2 + (p.y - snap.ball.y) ** 2).player_id
    cases = {
        "GOALKEEPER_ASSIGNMENT": _strat(DefensiveAssignment(defender_id=gk, role="press")),
        "NOT_A_DEFENDER": _strat(DefensiveAssignment(defender_id=attacker, role="press")),
        "DEFENDER_NOT_ON_PITCH": _strat(DefensiveAssignment(defender_id="A12", role="press")),
        "DUPLICATE_DEFENDER": _strat(DefensiveAssignment(defender_id=defender, role="press"),
                                     DefensiveAssignment(defender_id=defender, role="press")),
        "TARGET_NOT_ATTACKER": _strat(DefensiveAssignment(defender_id=defender, role="track_runner",
                                                          target_player_id=far), style="track_runner"),
        "DEFENDER_CANNOT_REACH": _strat(DefensiveAssignment(defender_id=far, role="press")),
    }
    for code, s in cases.items():
        ok, got, _ = validate_strategy(s, snap, r)
        assert not ok and got == code, (code, got)
    opts = generate_defensive_options(snap, r, [("H07", 90.0, 20.0)])
    assert opts[0].strategy_id == BASELINE.strategy_id
    assert all(validate_strategy(o, snap, r)[0] for o in opts)
    assert {"press", "cover_lane", "track_runner", "protect_central", "contain"} <= {o.style for o in opts}


def test_baseline_defence_matches_original_engine(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    cands = generate_candidates(snap, demo_match.roster)[:2]
    cfg = SimulationConfig(rollouts=40, seed=snap.seed)
    plain = evaluate_actions(snap, demo_match.roster, cands, cfg)
    base = evaluate_actions(snap, demo_match.roster, cands, cfg, defense=build_runtime(BASELINE, snap))
    assert [r.model_dump() for r in plain.results] == [r.model_dump() for r in base.results]


def test_covering_a_lane_makes_that_pass_harder(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    target = next(c for c in generate_candidates(snap, demo_match.roster) if c.target_player_id == "H07"
                  and "-pass-" in c.action_id)
    opts = {o.strategy_id: o for o in generate_defensive_options(snap, demo_match.roster,
                                                                [("H07", target.target_x, target.target_y)])}
    cfg = SimulationConfig(rollouts=160, seed=snap.seed)
    base = evaluate_actions(snap, demo_match.roster, [target], cfg)
    cover = evaluate_actions(snap, demo_match.roster, [target], cfg, defense=build_runtime(opts["def-cover-H07"], snap))
    assert cover.results[0].p_first_action_success.value < base.results[0].p_first_action_success.value


def test_conditional_shot_estimator_agrees_with_binary_goals(demo_match, demo_decision_snapshot):
    ev, snap = demo_decision_snapshot
    actual = actual_action_from_event(snap, demo_match.roster, ev.event_type.value, None, None, None)
    ce = CellEvaluator()
    r = ce.evaluate(snap, demo_match.roster, actual, None, 300, snap.seed, 10.0)
    assert abs(r.cell.xg - r.cell.p_goal.value) < 0.03
    assert (r.cell.xg_ci95_high - r.cell.xg_ci95_low) < (r.cell.p_goal.ci95_high - r.cell.p_goal.ci95_low)
    again = ce.evaluate(snap, demo_match.roster, actual, None, 300, snap.seed, 10.0)
    assert again.cell.cached and again.cell.xg == r.cell.xg and ce.hits == 1


def test_transition_is_deterministic_and_never_mutates_parent(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    digest = snapshot_digest(snap)
    action = next(c for c in generate_candidates(snap, demo_match.roster) if c.action_type == "pass")
    cell = CellEvaluator().evaluate(snap, demo_match.roster, action, None, 60, snap.seed, 10.0)
    a = realize_transition(snap, demo_match.roster, action, None, cell, "representative", "child-a", 1)
    b = realize_transition(snap, demo_match.roster, action, None, cell, "representative", "child-b", 1)
    assert snapshot_digest(snap) == digest
    assert a.transition.rollout_index == b.transition.rollout_index
    assert [f.model_dump() for f in a.transition.frames] == [f.model_dump() for f in b.transition.frames]
    assert a.child_snapshot.model_dump(exclude={"snapshot_id"}) == b.child_snapshot.model_dump(exclude={"snapshot_id"})
    cs = a.child_snapshot
    assert cs.sim_time_ms > snap.sim_time_ms and cs.match_clock_ms > snap.match_clock_ms
    if a.transition.terminal_outcome is None:
        assert cs.possession_team_id == snap.possession_team_id and cs.ball.possessor_id is not None
        if a.transition.first_outcome == "completed":
            assert cs.ball.possessor_id == action.target_player_id
    else:
        assert cs.possession_team_id != snap.possession_team_id or cs.ball.possessor_id is None


def test_rollout_selection_kinds(demo_match, demo_decision_snapshot):
    _, snap = demo_decision_snapshot
    action = next(c for c in generate_candidates(snap, demo_match.roster) if c.action_type == "pass")
    cell = CellEvaluator().evaluate(snap, demo_match.roster, action, None, 80, snap.seed, 10.0)
    sm = cell.summaries
    idx, _, kind = select_rollout(sm, "representative", 1)
    modal = max({s.first_outcome for s in sm}, key=lambda o: sum(x.first_outcome == o for x in sm))
    assert sm[idx].first_outcome == modal and kind == "representative"
    up, _, _ = select_rollout(sm, "high_upside", 1)
    assert sm[up].shot_goal_prob == max(s.shot_goal_prob for s in sm)
    r1, _, _ = select_rollout(sm, "random", 5)
    r2, _, _ = select_rollout(sm, "random", 5)
    assert r1 == r2


# ------------------------------------------------------------------------------------ service

@pytest.fixture
def mv(settings, store, hub):
    settings.multiverse_cell_rollouts = 30
    settings.multiverse_max_cell_rollouts = 30
    return MultiverseService(settings, store, hub, ChatClientProvider(settings))


def _decision(store):
    md = store.matches["demo-match-073"]
    return next(d for d in md.decisions if d.event_id in md.labelled_decision_event_ids)


async def _step(mv, sid, node, **kw):
    job = await mv.start_step(sid, node, BranchActionRequest(**kw))
    return await mv.wait(job.job_id)


async def test_session_branching_rewind_fork_compare(mv, store):
    dp = _decision(store)
    s = mv.create_session(SessionCreate(decision_point_id=dp.decision_point_id))
    root = s.nodes[s.root_node_id]
    root_snap_digest = snapshot_digest(s.snapshots[root.snapshot_id])
    observed = s.nodes[f"{s.session_id}~observed"]
    assert observed.kind == "observed" and observed.transition.frames
    events_before = list(store.matches[dp.match_id].events)

    j1 = await _step(mv, s.session_id, root.node_id, action=ActionSpec(action_type="pass", target_player_id="H07"))
    assert j1.status == "completed", j1.error
    c1 = s.nodes[j1.child_node_id]
    p1 = s.plannings[j1.planning_id]
    assert c1.entering_action_source == "user" and c1.entering_action.target_player_id == "H07"
    assert p1.summary.selected_action_id == c1.entering_action.action_id
    assert p1.verification_status == "verified" and all(c["passed"] for c in p1.verification_checks
                                                        if c["severity"] == "error")
    assert 1 <= len(p1.rounds) <= p1.max_rounds
    agents = [st.agent for st in p1.steps]
    assert {"attacking_agent", "defending_agent", "simulation_agent", "verification_agent", "explanation_agent"} <= set(agents)
    assert len({(c.action_id, c.strategy_id) for c in p1.matrix}) == len(p1.matrix)
    assert {c.n_rollouts for c in p1.matrix} == {30}
    assert len(p1.narratives) == 6 and all(n.verification_status == "verified" for n in p1.narratives)

    # idempotent: the same request returns the same child
    again = await mv.start_step(s.session_id, root.node_id,
                                BranchActionRequest(action=ActionSpec(action_type="pass", target_player_id="H07")))
    assert again.child_node_id == c1.node_id and again.status == "completed"

    # second decision from the new state (if it is a decision)
    if c1.status == "decision":
        j2 = await _step(mv, s.session_id, c1.node_id, action=ActionSpec(action_type="shoot"))
        assert j2.status == "completed"
        c2 = s.nodes[j2.child_node_id]
        assert c2.parent_node_id == c1.node_id and c2.depth == 2

    # rewind + fork: a sibling from the root leaves the first branch untouched
    c1_dump = c1.model_dump(exclude={"children"})
    j3 = await _step(mv, s.session_id, root.node_id, action=ActionSpec(candidate_id=next(
        o.action_id for o in generate_candidates(s.snapshots[root.snapshot_id], store.matches[dp.match_id].roster)
        if o.action_type == "dribble")))
    assert j3.status == "completed"
    c3 = s.nodes[j3.child_node_id]
    assert c3.node_id != c1.node_id and c3.parent_node_id == root.node_id
    assert s.nodes[c1.node_id].model_dump(exclude={"children"}) == c1_dump
    assert snapshot_digest(s.snapshots[root.snapshot_id]) == root_snap_digest
    assert store.matches[dp.match_id].events == events_before

    cmp = mv.compare(c1.node_id, c3.node_id)
    assert cmp.common_ancestor == root.node_id and cmp.steps_a and cmp.steps_b
    cmp2 = mv.compare(c1.node_id, observed.node_id)
    assert cmp2.metrics_b["kind"] == "observed"

    tree = mv.tree(s)
    assert {n["node_id"] for n in tree["nodes"]} == set(s.nodes)
    path = mv.path_frames(s, c1.node_id)
    assert path["frames"][0]["t_ms"] == 0 and path["duration_ms"] > 0

    # persistence: a fresh service restores the session from disk
    fresh = MultiverseService(mv.settings, store, mv.hub, mv.provider)
    restored = fresh.get(s.session_id)
    assert set(restored.nodes) == set(s.nodes)
    assert fresh.path_frames(restored, c1.node_id) == path


async def test_invalid_actions_are_rejected_not_rewritten(mv, store):
    dp = _decision(store)
    s = mv.create_session(SessionCreate(decision_point_id=dp.decision_point_id))
    root = s.nodes[s.root_node_id]
    bad = {
        "TARGET_UNAVAILABLE": ActionSpec(action_type="pass", target_player_id="H14"),
        "OPPONENT_TARGET": ActionSpec(action_type="pass", target_player_id="A05"),
        "TARGET_OFF_PITCH": ActionSpec(action_type="pass", target_x=-10, target_y=30),
        "DRIBBLE_LENGTH": ActionSpec(action_type="dribble", target_x=root.match_clock_ms * 0 + 5, target_y=60),
        "UNKNOWN_CANDIDATE": ActionSpec(action_type="pass", candidate_id="nope"),
    }
    for code, spec in bad.items():
        v = mv.validate_action(s, root, spec)
        assert not v.ok and v.code == code, (code, v)
    with pytest.raises(MultiverseError) as e:
        await mv.start_step(s.session_id, root.node_id, BranchActionRequest(action=bad["OPPONENT_TARGET"]))
    assert e.value.code == "OPPONENT_TARGET"
    with pytest.raises(MultiverseError) as e:
        await mv.start_step(s.session_id, root.node_id, BranchActionRequest(mode="manual"))
    assert e.value.code == "ACTION_REQUIRED"
    with pytest.raises(MultiverseError) as e:
        await mv.start_step(s.session_id, f"{s.session_id}~observed",
                            BranchActionRequest(action=ActionSpec(action_type="shoot")))
    assert e.value.code == "OBSERVED_NODE"
    assert len(s.nodes) == 2


async def test_assisted_autonomous_and_limits(mv, store):
    mv.settings.multiverse_max_depth = 2
    dp = _decision(store)
    s = mv.create_session(SessionCreate(decision_point_id=dp.decision_point_id, mode="assisted"))
    root = s.nodes[s.root_node_id]
    rec = await _step(mv, s.session_id, root.node_id, mode="assisted")
    assert rec.status == "completed" and rec.child_node_id is None
    plan = mv.recommendation(s, root)
    assert plan is not None and plan.summary is not None and plan.summary.most_robust_action_id
    assert len(s.nodes) == 2  # recommendation never creates a branch

    job = await mv.auto_play(s.session_id, root.node_id, 3, "representative")
    job = await mv.wait(job.job_id)
    assert job.status == "completed"
    leaf = s.nodes[job.child_node_id]
    assert leaf.depth <= 2 and leaf.entering_action_source == "attacking_agent"
    assert leaf.status in ("terminal", "depth_limit", "decision")
    if leaf.status == "depth_limit":
        with pytest.raises(MultiverseError) as e:
            await mv.start_step(s.session_id, leaf.node_id, BranchActionRequest(action=ActionSpec(action_type="shoot")))
        assert e.value.code in ("NO_DECISION", "DEPTH_LIMIT")


async def test_cancellation_stops_job_and_keeps_tree_consistent(mv, store):
    dp = _decision(store)
    s = mv.create_session(SessionCreate(decision_point_id=dp.decision_point_id))
    job = await mv.start_step(s.session_id, s.root_node_id, BranchActionRequest(action=ActionSpec(action_type="shoot")))
    assert mv.cancel(job.job_id)
    job = await mv.wait(job.job_id)
    assert job.status in ("cancelled", "completed", "failed")
    for n in s.nodes.values():
        if n.parent_node_id:
            assert n.parent_node_id in s.nodes


async def test_verification_rejects_tampered_matrix(mv, store):
    """A planning whose matrix is altered after simulation fails deterministic verification."""
    from app.multiverse import workflow as mw
    from app.multiverse.verify import verify_planning

    captured = {}
    original = mw.verify_planning

    def spy(ctx):
        captured["ctx"] = ctx
        return original(ctx)

    mw.verify_planning = spy
    try:
        dp = _decision(store)
        s = mv.create_session(SessionCreate(decision_point_id=dp.decision_point_id))
        await _step(mv, s.session_id, s.root_node_id, action=ActionSpec(action_type="shoot"))
    finally:
        mw.verify_planning = original
    ctx = captured["ctx"]
    key = next(iter(ctx.cells))
    cell = ctx.cells[key].cell
    ctx.cells[key].cell = cell.model_copy(update={"xg": min(1.0, cell.xg + 0.2)})
    checks = verify_planning(ctx)
    failed = {c["check_id"] for c in checks if not c["passed"]}
    assert "values_consistent" in failed or "summary_consistent" in failed
    ctx.attack_set.append(ctx.attack_set[0] + "-ghost")
    ctx.generated[ctx.attack_set[-1]] = ctx.action(ctx.attack_set[0]).model_copy(
        update={"action_id": ctx.attack_set[-1], "target_player_id": "H14", "action_type": "pass"})
    failed = {c["check_id"] for c in verify_planning(ctx) if not c["passed"]}
    assert {"actions_valid", "matrix_complete"} <= failed


async def test_speed_bounds_hold_under_defensive_strategies(demo_match, demo_decision_snapshot):
    from app.simulation.engine import RolloutRng
    from app.simulation.rollout import resolve_candidate, run_rollout, state_from_snapshot

    _, snap = demo_decision_snapshot
    base = state_from_snapshot(snap, demo_match.roster)
    vmax = {p.player_id: p.max_speed for p in base.profiles}
    act = resolve_candidate(base, snap, generate_candidates(snap, demo_match.roster)[0])
    for strat in generate_defensive_options(snap, demo_match.roster, [("H07", 90.0, 20.0)]):
        _, frames, _ = run_rollout(base, act, RolloutRng(snap.seed, 3), 10.0, record=True,
                                   defense=build_runtime(strat, snap))
        for a, b in zip(frames, frames[1:], strict=False):
            dt = (b.t_ms - a.t_ms) / 1000
            for pid, (x, y) in b.players.items():
                ax, ay = a.players[pid]
                assert np.hypot(x - ax, y - ay) / dt <= vmax[pid] + 0.15, (strat.strategy_id, pid)
    await asyncio.sleep(0)

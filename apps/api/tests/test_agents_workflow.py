"""Multi-agent workflow tests (deterministic policy client + mocked failing providers; no network)."""

import pytest

from app.agents.policy_client import FailingChatClient, PolicyDecision
from app.models.analysis import AnalyzeRequest
from app.orchestration import workflow as wf
from app.services.analysis_service import AnalysisService

pytestmark = pytest.mark.asyncio


def _labelled_decision(store):
    md = store.matches["demo-match-073"]
    return next(d for d in md.decisions if d.event_id in md.labelled_decision_event_ids)


async def _run(settings, store, hub, faults=None, provider=None):
    svc = AnalysisService(settings, store, hub, provider)
    dp = _labelled_decision(store)
    a = await svc.start(dp.decision_point_id, AnalyzeRequest(fault_injection=faults or []))
    return await svc.wait(a.analysis_id), svc


def agents_of(a):
    return [s.agent for s in a.workflow.steps]


async def test_full_workflow_is_verified_with_distinct_agents_and_tools(settings, store, hub):
    a, svc = await _run(settings, store, hub)
    assert a.status == "verified", a.workflow.errors
    assert agents_of(a)[:5] == ["decision_agent", "strategy_agent", "simulation_agent", "verification_agent",
                                "explanation_agent"]
    tools = {tc.tool_name for s in a.workflow.steps for tc in s.tool_calls}
    assert {"get_decision_context", "generate_candidate_actions", "run_simulation", "run_verification_checks",
            "get_verified_evidence", "verify_narratives"} <= tools
    # Every candidate starts from the decision snapshot; the actual action is included once.
    assert {c.initial_state_id for c in a.candidates} == {a.snapshot_id}
    assert sum(c.is_actual for c in a.candidates) == 1 and 2 <= len(a.candidates) <= 4
    # Every narrative verified, both languages, three viewer modes.
    assert {(n.audience, n.language) for n in a.narratives} == {(m, lang) for m in ("casual", "analyst", "broadcaster")
                                                                for lang in ("en", "nl")}
    assert all(n.verification_status == "verified" and not n.is_live_model_output for n in a.narratives)
    assert a.model.agent_mode == "policy" and a.model.live_model_calls == 0
    assert a.workflow.handoffs and a.workflow.state_version > 0
    assert len(svc.overlays(a.analysis_id)) == 6


async def test_recovery_invalid_candidate(settings, store, hub):
    a, _ = await _run(settings, store, hub, ["invalid_candidate"])
    assert a.status == "verified"
    rej = a.workflow.rejected_candidates
    assert rej and "PLAYER_NOT_ON_PITCH" in rej[0].reason
    strategy_steps = [s for s in a.workflow.steps if s.agent == "strategy_agent"]
    assert len(strategy_steps) == 2 and strategy_steps[0].status == "rejected"
    assert all(c.target_player_id not in a.workflow.rejected_candidates[0].proposal.values()
               for c in a.candidates if c.target_player_id)


async def test_recovery_contradictory_claim(settings, store, hub):
    a, _ = await _run(settings, store, hub, ["contradictory_claim"])
    assert a.status == "verified"
    expl = [s for s in a.workflow.steps if s.agent == "explanation_agent"]
    assert len(expl) == 2
    assert any("unsupported claims" in (h.reason or "") for h in a.workflow.handoffs)
    assert all("[Injected]" not in n.body for n in a.narratives)


async def test_recovery_model_unavailable(settings, store, hub):
    a, _ = await _run(settings, store, hub, ["model_unavailable"])
    assert a.status == "verified"
    assert a.model.degraded and a.model.live_model_calls == 0
    assert all(s.model == "policy" and s.status == "degraded" for s in a.workflow.steps)
    assert all(not n.is_live_model_output for n in a.narratives)


async def test_recovery_simulation_timeout(settings, store, hub):
    a, _ = await _run(settings, store, hub, ["simulation_timeout"])
    sim_calls = [tc for s in a.workflow.steps for tc in s.tool_calls if tc.tool_name == "run_simulation"]
    assert len(sim_calls) == 2
    assert sim_calls[0].result_summary["partial"] is True
    assert a.status == "verified" and not a.simulation.partial


async def test_live_provider_failure_falls_back_without_pretending(settings, store, hub):
    class BrokenProvider(wf.ChatClientProvider):
        mode = "foundry"

        def live_client(self):
            return FailingChatClient()

    provider = BrokenProvider(settings)
    provider.mode = "foundry"
    a, _ = await _run(settings, store, hub, provider=provider)
    assert a.status == "verified"
    assert a.model.degraded and a.model.policy_fallbacks >= 5 and a.model.live_model_calls == 0
    assert all("failed" in " ".join(s.notes) for s in a.workflow.steps)


async def test_retries_are_bounded_when_strategy_keeps_failing(settings, store, hub, monkeypatch):
    def always_invalid(turn):
        if "generate_candidate_actions" not in turn.results:
            return PolicyDecision(tool_calls=[("generate_candidate_actions", {})])
        return PolicyDecision(final={"proposals": [{"candidate_id": "does-not-exist"}]})

    monkeypatch.setattr(wf, "strategy_policy", always_invalid)
    a, _ = await _run(settings, store, hub)
    assert a.status == "unavailable"
    n_strategy = sum(1 for s in a.workflow.steps if s.agent == "strategy_agent")
    assert n_strategy == settings.max_strategy_revisions + 1
    assert a.unavailable_reason


async def test_verification_agent_cannot_override_deterministic_failure(settings, store, hub, monkeypatch):
    original = wf.verify_analysis

    def broken(*args, **kwargs):
        rec = original(*args, **kwargs)
        rec.checks[0].passed = False
        rec.status = "rejected"
        rec.failures = ["same_snapshot: forced failure"]
        rec.accepted_evidence = []
        return rec

    def lenient_agent(turn):
        if "run_verification_checks" not in turn.results and "verify_narratives" not in turn.results:
            return PolicyDecision(tool_calls=[("run_verification_checks", {})])
        return PolicyDecision(final={"status": "verified", "route": "explain", "issues": [], "assessment": "looks ok"})

    monkeypatch.setattr(wf, "verify_analysis", broken)
    monkeypatch.setattr(wf, "verification_policy", lenient_agent)
    a, _ = await _run(settings, store, hub)
    assert a.status == "unavailable"
    v_step = next(s for s in a.workflow.steps if s.agent == "verification_agent")
    assert any("overridden" in n for n in v_step.notes)
    assert not a.narratives


async def test_cached_replay_is_labelled(settings, store, hub):
    settings.use_analysis_cache = True
    svc = AnalysisService(settings, store, hub)
    dp = _labelled_decision(store)
    first = await svc.wait((await svc.start(dp.decision_point_id, AnalyzeRequest())).analysis_id)
    assert first.status == "verified" and not first.cached
    svc2 = AnalysisService(settings, store, hub)
    store.analysis_by_cache_key.clear()
    again = await svc2.start(dp.decision_point_id, AnalyzeRequest())
    assert again.cached and again.status == "verified"
    assert [r.model_dump() for r in again.simulation.results] == [r.model_dump() for r in first.simulation.results]


async def test_trajectory_matches_recorded_outcome(settings, store, hub):
    a, svc = await _run(settings, store, hub)
    for r in a.simulation.results:
        t = await svc.trajectory(a.analysis_id, r.action_id)
        assert t.outcome == r.representative_outcome
        assert t.kind == "simulated" and t.frames
        assert t.rollout_index == r.representative_rollout


async def test_every_detected_decision_gets_grounded_narratives_first_time(settings, hub):
    """Regression: deterministic templates must pass narrative verification on the first attempt."""
    from app.services.store import Store

    store = Store(settings.scenarios_dir, settings.data_dir)
    store.load(only=["shoot_vs_pass", "risky_through_ball", "counterattack", "defensive_pressure"])
    settings.default_rollouts = 60
    svc = AnalysisService(settings, store, hub)
    checked = 0
    for md in store.matches.values():
        for dp in md.decisions:
            a = await svc.wait((await svc.start(dp.decision_point_id, AnalyzeRequest())).analysis_id)
            assert a.status == "verified", (dp.decision_point_id, a.workflow.errors)
            assert a.workflow.explanation_retries == 0, (dp.decision_point_id, a.workflow.verification_issues)
            assert sum(1 for s in a.workflow.steps if s.agent == "explanation_agent") == 1
            assert not any("/" in i for i in a.workflow.verification_issues), a.workflow.verification_issues
            assert len(a.narratives) == 6, dp.decision_point_id
            checked += 1
    assert checked >= 4


async def test_live_explanation_writes_english_and_dutch_comes_from_verified_templates(settings, store, hub, monkeypatch):
    """With a live model the Explanation agent only writes English; Dutch is built from the same evidence."""
    from app.agents.runner import AgentRunner

    original = AgentRunner.run

    async def run(self, agent, task, instructions, tools, prompt, schema, policy, attempt=1, **kw):
        out, step = await original(self, agent, task, instructions, tools, prompt, schema, policy, attempt, **kw)
        if agent == "explanation_agent":
            assert '"languages": ["en"]' in prompt  # the live model is only asked for English
            out = out.model_copy(update={"narratives": [n for n in out.narratives if n.language == "en"]})
            step.live_model = True
            step.model = "foundry:test"
        return out, step

    monkeypatch.setattr(AgentRunner, "run", run)
    a, _ = await _run(settings, store, hub)
    assert a.status == "verified", a.workflow.errors
    langs = {(n.audience, n.language): n for n in a.narratives}
    assert set(langs) == {(m, lang) for m in ("casual", "analyst", "broadcaster") for lang in ("en", "nl")}
    assert all(n.verification_status == "verified" for n in a.narratives)
    assert all(langs[(m, "en")].generated_by == "foundry:test" for m in ("casual", "analyst", "broadcaster"))
    assert all("from verified evidence" in langs[(m, "nl")].generated_by for m in ("casual", "analyst", "broadcaster"))

import random

from app.match_state.engine import MatchStateEngine
from app.models.events import EventType


def test_replay_is_deterministic(demo_match):
    a = MatchStateEngine(demo_match.info).replay(demo_match.events)
    b = MatchStateEngine(demo_match.info).replay(demo_match.events)
    assert a == b
    assert a.last_seq == len(demo_match.events)


def test_duplicates_are_ignored_and_out_of_order_events_buffered(demo_match):
    events = demo_match.events
    reference = MatchStateEngine(demo_match.info).replay(events)
    eng = MatchStateEngine(demo_match.info)
    shuffled = list(events[:40])
    random.Random(1).shuffle(shuffled)
    for e in shuffled + events[:40] + events[40:]:
        eng.ingest(e)
    v = eng.view()
    assert v.last_seq == reference.last_seq
    assert v.team_stats == reference.team_stats
    assert v.score == reference.score
    assert v.duplicates_ignored >= 40
    assert v.reordered_events > 0


def test_pass_statistics_match_events(demo_match):
    v = MatchStateEngine(demo_match.info).replay(demo_match.events)
    for team_id, ts in v.team_stats.items():
        attempted = sum(1 for e in demo_match.events if e.event_type == EventType.PASS_ATTEMPTED and e.team_id == team_id)
        completed = sum(1 for e in demo_match.events if e.event_type == EventType.PASS_COMPLETED and e.team_id == team_id)
        assert ts.passes_attempted == attempted
        assert ts.passes_completed == completed
        if attempted:
            assert ts.pass_accuracy == round(completed / attempted, 4)
    shares = [ts.possession_share for ts in v.team_stats.values() if ts.possession_share is not None]
    assert abs(sum(shares) - 1.0) < 1e-3


def test_partial_replay_uses_only_past_events(demo_match):
    t = 3000
    v = MatchStateEngine(demo_match.info).replay(demo_match.events, until_ms=t)
    assert v.sim_time_ms <= t
    assert all(e.sim_time_ms <= t for e in demo_match.events[: v.last_seq])

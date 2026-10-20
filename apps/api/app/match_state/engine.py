"""Match state engine: consumes the event stream and maintains consistent match state.

* Idempotent: duplicated events (same event_id) are ignored.
* Ordered: events arriving out of order are buffered until the gap in `seq` is filled,
  so replaying the same stream always yields the same state (deterministic replay).
* Observed vs modeled: counters come from observed synthetic events; fields that come from
  a model (pass difficulty, modeled shot quality) are kept in clearly named separate fields.
"""

from __future__ import annotations

import heapq
from collections import deque

from ..models.events import EventType, MatchEvent
from ..models.match import MatchInfo
from ..models.stats import MatchStateView, PlayerStats, TeamStats


class MatchStateEngine:
    def __init__(self, info: MatchInfo, recent: int = 30):
        self.info = info
        self.match_id = info.match_id
        self.roster = {p.player_id: p for p in info.players}
        self.reset(recent)

    def reset(self, recent: int = 30) -> None:
        self.last_seq = 0
        self.seen: set[str] = set()
        self.pending: list[tuple[int, str, MatchEvent]] = []
        self.sim_time_ms = 0
        self.match_clock_ms = self.info.start_clock_ms
        self.score = dict(self.info.initial_score)
        self.possession_team_id: str | None = None
        self.possession_since_ms = 0
        self.possession_ms: dict[str, int] = {self.info.home.team_id: 0, self.info.away.team_id: 0}
        self.ball: tuple[float, float] | None = None
        self.positions: dict[str, tuple[float, float]] = {}
        self.recent: deque[MatchEvent] = deque(maxlen=recent)
        self.team = {t: TeamStats(team_id=t) for t in (self.info.home.team_id, self.info.away.team_id)}
        self.players: dict[str, PlayerStats] = {}
        self._pass_lengths: dict[str, list[float]] = {t: [] for t in self.team}
        self._pass_difficulty: dict[str, list[float]] = {t: [] for t in self.team}
        self._last_pass_by: str | None = None
        self.duplicates_ignored = 0
        self.reordered = 0
        self.decisions_detected = 0

    # ------------------------------------------------------------------ ingestion
    def ingest(self, event: MatchEvent) -> list[MatchEvent]:
        """Accept one event; returns the events actually applied (in order)."""
        if event.match_id != self.match_id:
            raise ValueError(f"event {event.event_id} belongs to {event.match_id}")
        if event.event_id in self.seen or event.seq <= self.last_seq:
            self.duplicates_ignored += 1
            return []
        self.seen.add(event.event_id)
        if event.seq != self.last_seq + 1:
            self.reordered += 1
            heapq.heappush(self.pending, (event.seq, event.event_id, event))
            return []
        applied = [event]
        self._apply(event)
        while self.pending and self.pending[0][0] == self.last_seq + 1:
            _, _, nxt = heapq.heappop(self.pending)
            self._apply(nxt)
            applied.append(nxt)
        return applied

    def _p(self, pid: str) -> PlayerStats:
        if pid not in self.players:
            p = self.roster[pid]
            self.players[pid] = PlayerStats(player_id=pid, name=p.name, team_id=p.team_id)
        return self.players[pid]

    def _set_possession(self, team_id: str | None, t_ms: int) -> None:
        if self.possession_team_id is not None:
            self.possession_ms[self.possession_team_id] += max(0, t_ms - self.possession_since_ms)
        self.possession_team_id = team_id
        self.possession_since_ms = t_ms

    def _apply(self, e: MatchEvent) -> None:
        self.last_seq = e.seq
        self.sim_time_ms = e.sim_time_ms
        self.match_clock_ms = e.match_clock_ms
        et = e.event_type
        if et == EventType.PLAYER_POSITION_UPDATED:
            if e.details.positions:
                self.positions = dict(e.details.positions)
            return
        if et == EventType.BALL_POSITION_UPDATED:
            if e.x is not None and e.y is not None:
                self.ball = (e.x, e.y)
            return
        self.recent.append(e)
        if e.x is not None and e.y is not None:
            self.ball = (e.x, e.y)
        team = e.team_id
        actor = e.player_ids[0] if e.player_ids else None
        if actor and actor in self.roster:
            self._p(actor).involvement += 1
            if self.possession_team_id is None and team is not None and et in (
                EventType.PASS_ATTEMPTED, EventType.DRIBBLE_ATTEMPTED, EventType.SHOT_ATTEMPTED
            ):
                self._set_possession(team, e.sim_time_ms)
        ts = self.team.get(team) if team else None
        d = e.details
        if et == EventType.PASS_ATTEMPTED and ts and actor:
            ts.passes_attempted += 1
            self._p(actor).passes_attempted += 1
            self._last_pass_by = actor
            if d.pass_length_m is not None:
                self._pass_lengths[team].append(d.pass_length_m)
            if d.pass_difficulty is not None:
                self._pass_difficulty[team].append(d.pass_difficulty)
            if d.ball_speed_mps is not None:
                ts.max_ball_speed_mps = max(ts.max_ball_speed_mps or 0.0, d.ball_speed_mps)
        elif et == EventType.PASS_COMPLETED and ts and actor:
            ts.passes_completed += 1
            self._p(actor).passes_completed += 1
        elif et == EventType.SHOT_ATTEMPTED and ts and actor:
            ts.shots += 1
            p = self._p(actor)
            p.shots += 1
            if d.modeled_scoring_probability is not None:
                ts.total_modeled_shot_quality += d.modeled_scoring_probability
                p.modeled_shot_quality += d.modeled_scoring_probability
            if d.shot_speed_mps is not None:
                ts.max_ball_speed_mps = max(ts.max_ball_speed_mps or 0.0, d.shot_speed_mps)
            if self._last_pass_by and self._last_pass_by != actor and self.roster[self._last_pass_by].team_id == team:
                self._p(self._last_pass_by).key_passes += 1
        elif et == EventType.SHOT_SAVED and len(e.player_ids) > 1:
            shooter_team = self.roster[e.player_ids[1]].team_id
            self.team[shooter_team].shots_on_target += 1
        elif et == EventType.GOAL and ts and actor:
            ts.goals += 1
            ts.shots_on_target += 1
            self._p(actor).goals += 1
            if d.score_home is not None and d.score_away is not None:
                self.score = {self.info.home.team_id: d.score_home, self.info.away.team_id: d.score_away}
        elif et == EventType.INTERCEPTION and ts and actor:
            ts.interceptions += 1
            self._p(actor).interceptions += 1
        elif et == EventType.TACKLE and ts and actor:
            ts.tackles += 1
            self._p(actor).tackles += 1
        elif et == EventType.DRIBBLE_ATTEMPTED and ts:
            ts.dribbles_attempted += 1
        elif et == EventType.DRIBBLE_COMPLETED and ts and actor:
            ts.dribbles_completed += 1
            self._p(actor).dribbles_completed += 1
        elif et == EventType.PRESSURE_APPLIED and ts:
            ts.pressure_events += 1
        elif et == EventType.POSSESSION_CHANGED and team:
            self.team[team].possession_changes_won += 1
            if d.lost_by_id and d.lost_by_id in self.roster:
                self._p(d.lost_by_id).turnovers += 1
            self._set_possession(team, e.sim_time_ms)
            self._last_pass_by = None
        elif et == EventType.RESTART and team:
            self._set_possession(team, e.sim_time_ms)
        elif et == EventType.MATCH_ENDED:
            self._set_possession(None, e.sim_time_ms)

    # ------------------------------------------------------------------ views
    def view(self) -> MatchStateView:
        teams = {}
        poss = dict(self.possession_ms)
        if self.possession_team_id is not None:
            poss[self.possession_team_id] += max(0, self.sim_time_ms - self.possession_since_ms)
        total = sum(poss.values())
        for t, ts in self.team.items():
            c = ts.model_copy()
            c.pass_accuracy = round(ts.passes_completed / ts.passes_attempted, 4) if ts.passes_attempted else None
            pl = self._pass_lengths[t]
            c.mean_pass_length_m = round(sum(pl) / len(pl), 2) if pl else None
            pdf = self._pass_difficulty[t]
            c.mean_pass_difficulty_model = round(sum(pdf) / len(pdf), 4) if pdf else None
            c.total_modeled_shot_quality = round(ts.total_modeled_shot_quality, 4)
            c.possession_share = round(poss[t] / total, 4) if total else None
            teams[t] = c
        players = sorted(self.players.values(), key=lambda p: -p.involvement)
        return MatchStateView(
            match_id=self.match_id,
            last_seq=self.last_seq,
            sim_time_ms=self.sim_time_ms,
            match_clock_ms=self.match_clock_ms,
            score=dict(self.score),
            possession_team_id=self.possession_team_id,
            ball=self.ball,
            team_stats=teams,
            player_stats=[p.model_copy(update={"modeled_shot_quality": round(p.modeled_shot_quality, 4)})
                          for p in players],
            recent_event_ids=[e.event_id for e in list(self.recent)[-10:]],
            duplicates_ignored=self.duplicates_ignored,
            reordered_events=self.reordered,
            decisions_detected=self.decisions_detected,
        )

    def replay(self, events: list[MatchEvent], until_ms: int | None = None) -> MatchStateView:
        """Deterministically rebuild state from scratch up to `until_ms` (inclusive)."""
        self.reset(self.recent.maxlen or 30)
        for e in events:
            if until_ms is not None and e.sim_time_ms > until_ms:
                break
            self.ingest(e)
        return self.view()

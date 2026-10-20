"""Server-paced live replay of a synthetic match over WebSocket.

Each connection gets its own replay clock. Every tick (100 ms wall time) the session
* streams the tracking frames and events whose timestamps the clock has passed,
* ingests the events into a fresh MatchStateEngine (dedupe/ordering/statistics), and
* runs the streaming DecisionDetector; detected decisions are pushed to the client and,
  when auto-analysis is on, handed to the multi-agent analysis service.

Seeking rebuilds state deterministically by replaying the stream from the start.
"""

from __future__ import annotations

import asyncio
import bisect
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..analytics.detector import DecisionDetector
from ..match_state.engine import MatchStateEngine
from ..models.analysis import AnalyzeRequest
from ..models.decisions import DecisionPoint
from . import metrics
from .analysis_service import AnalysisService
from .store import MatchData

TICK_S = 0.1
Send = Callable[[dict[str, Any]], Awaitable[None]]


class ReplaySession:
    def __init__(self, md: MatchData, send: Send, analyses: AnalysisService, auto_analyze: bool = True):
        self.md = md
        self.send = send
        self.analyses = analyses
        self.auto_analyze = auto_analyze
        self.speed = 1.0
        self.playing = False
        self.t_ms = 0.0
        self.frame_times = [f.t_ms for f in md.frames]
        self.event_times = [e.sim_time_ms for e in md.events]
        self._reset_state(0)
        self.closed = False

    def _reset_state(self, t_ms: float) -> None:
        self.engine = MatchStateEngine(self.md.info)
        self.detector = DecisionDetector(self.md.info.match_id, self.md.roster, self.md.snapshots,
                                         feature_cache=self.md.feature_cache)
        self.next_event = 0
        self.next_frame = bisect.bisect_left(self.frame_times, t_ms)
        self.detected: list[str] = []
        # Rebuild state up to t (deterministic replay) without emitting decisions.
        while self.next_event < len(self.md.events) and self.md.events[self.next_event].sim_time_ms <= t_ms:
            e = self.md.events[self.next_event]
            self.engine.ingest(e)
            for dp in self.detector.on_event(e):
                self.detected.append(dp.decision_point_id)
            self.next_event += 1
        self.t_ms = t_ms

    def _canonical(self, dp: DecisionPoint) -> DecisionPoint:
        """Use the store's decision object (same deterministic id) so analyses attach to it."""
        return self.analyses.store.decisions.get(dp.decision_point_id, dp)

    async def hello(self) -> None:
        info = self.md.info
        await self.send({"type": "hello", "match_id": info.match_id, "duration_ms": info.duration_ms,
                         "frame_hz": info.settings.frame_rate_hz, "start_clock_ms": info.start_clock_ms,
                         "speed": self.speed, "playing": self.playing, "auto_analyze": self.auto_analyze})
        await self._send_state(reset=True)

    async def _send_state(self, reset: bool = False) -> None:
        v = self.engine.view()
        frame = self.md.frames[min(max(self.next_frame - 1, 0), len(self.md.frames) - 1)] if self.md.frames else None
        await self.send({"type": "reset" if reset else "state", "t_ms": int(self.t_ms),
                         "clock_ms": self.md.info.start_clock_ms + int(self.t_ms), "score": v.score,
                         "possession_team_id": v.possession_team_id, "playing": self.playing, "speed": self.speed,
                         "frame": frame.model_dump(mode="json") if frame else None,
                         "recent_events": [e.model_dump(mode="json") for e in list(self.engine.recent)[-12:]],
                         "detected_decisions": self.detected, "stats": v.model_dump(mode="json")})

    async def control(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "play":
            if self.t_ms >= self.md.info.duration_ms:
                self._reset_state(0)
            self.playing = True
        elif kind == "pause":
            self.playing = False
        elif kind == "speed":
            self.speed = float(min(8.0, max(0.25, float(msg.get("value", 1.0)))))
        elif kind == "seek":
            t = float(min(max(0.0, float(msg.get("t_ms", 0))), self.md.info.duration_ms))
            with metrics.timer("live.seek_rebuild"):
                self._reset_state(t)
            await self._send_state(reset=True)
            return
        elif kind == "restart":
            self._reset_state(0)
            self.playing = bool(msg.get("play", True))
            await self._send_state(reset=True)
            return
        elif kind == "auto_analyze":
            self.auto_analyze = bool(msg.get("value", True))
        await self.send({"type": "status", "playing": self.playing, "speed": self.speed, "t_ms": int(self.t_ms),
                         "auto_analyze": self.auto_analyze})

    async def tick(self, dt_s: float) -> None:
        if not self.playing:
            return
        end = self.md.info.duration_ms
        new_t = min(end, self.t_ms + dt_s * 1000 * self.speed)
        f_hi = bisect.bisect_right(self.frame_times, new_t)
        frames = self.md.frames[self.next_frame:f_hi]
        self.next_frame = f_hi
        events = []
        decisions: list[DecisionPoint] = []
        while self.next_event < len(self.md.events) and self.md.events[self.next_event].sim_time_ms <= new_t:
            e = self.md.events[self.next_event]
            t0 = time.perf_counter()
            applied = self.engine.ingest(e)
            metrics.record("ingest.event_to_state", (time.perf_counter() - t0) * 1000)
            for a in applied:
                t1 = time.perf_counter()
                found = self.detector.on_event(a)
                metrics.record("detector.on_event", (time.perf_counter() - t1) * 1000)
                for dp in found:
                    decisions.append(self._canonical(dp))
                    self.detected.append(dp.decision_point_id)
            if e.event_type.value not in ("PLAYER_POSITION_UPDATED",):
                events.append(e.model_dump(mode="json", exclude_none=True))
            self.next_event += 1
        self.t_ms = new_t
        v = self.engine.view()
        await self.send({"type": "tick", "t_ms": int(new_t), "clock_ms": self.md.info.start_clock_ms + int(new_t),
                         "frames": [f.model_dump(mode="json") for f in frames], "events": events, "score": v.score,
                         "possession_team_id": v.possession_team_id})
        for dp in decisions:
            await self.send({"type": "decision_detected", "decision": dp.model_dump(mode="json")})
            if self.auto_analyze:
                # Progress (started/progress/completed) reaches the client through the event hub.
                with contextlib.suppress(KeyError):
                    await self.analyses.start(dp.decision_point_id, AnalyzeRequest())
        if new_t >= end:
            self.playing = False
            await self.send({"type": "ended", "t_ms": int(new_t)})

    async def run(self, inbox: asyncio.Queue, hub_queue: asyncio.Queue) -> None:
        await self.hello()
        last = time.perf_counter()
        while not self.closed:
            try:
                msg = await asyncio.wait_for(inbox.get(), timeout=TICK_S)
                if msg is None:
                    break
                await self.control(msg)
            except TimeoutError:
                pass
            now = time.perf_counter()
            dt, last = now - last, now
            await self.tick(min(dt, 0.5))
            while not hub_queue.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    await self.send(hub_queue.get_nowait())

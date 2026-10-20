"""Tiny pub/sub hub: pushes analysis progress and overlays to WebSocket subscribers of a match."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, match_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs[match_id].add(q)
        return q

    def unsubscribe(self, match_id: str, q: asyncio.Queue) -> None:
        self._subs[match_id].discard(q)

    def publish(self, match_id: str, message: dict[str, Any]) -> None:
        for q in list(self._subs.get(match_id, ())):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:  # slow consumer: drop the oldest message
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    def subscribers(self, match_id: str) -> int:
        return len(self._subs.get(match_id, ()))

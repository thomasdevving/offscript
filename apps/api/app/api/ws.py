"""WebSocket endpoint: live replay stream + analysis progress for one match."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.live import ReplaySession

router = APIRouter()
ALLOWED = {"play", "pause", "seek", "speed", "restart", "auto_analyze"}


@router.websocket("/ws/matches/{match_id}")
async def match_socket(ws: WebSocket, match_id: str) -> None:
    services = ws.app.state.services
    md = services.store.matches.get(match_id)
    await ws.accept()
    if md is None:
        await ws.send_json({"type": "error", "message": f"Unknown match {match_id}"})
        await ws.close(code=4404)
        return
    inbox: asyncio.Queue = asyncio.Queue(maxsize=100)
    hub_q = services.hub.subscribe(match_id)
    auto = ws.query_params.get("auto_analyze", "true").lower() != "false"

    async def send(msg: dict) -> None:
        await ws.send_text(json.dumps(msg, default=str))

    session = ReplaySession(md, send, services.analyses, auto_analyze=auto)
    runner = asyncio.create_task(session.run(inbox, hub_q))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") in ALLOWED:
                with contextlib.suppress(asyncio.QueueFull):
                    inbox.put_nowait(msg)
    except WebSocketDisconnect:
        pass
    finally:
        session.closed = True
        with contextlib.suppress(asyncio.QueueFull):
            inbox.put_nowait(None)
        services.hub.unsubscribe(match_id, hub_q)
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await runner

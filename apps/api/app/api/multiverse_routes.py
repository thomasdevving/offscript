"""Football Multiverse API: sessions, branch nodes, adversarial planning jobs, comparison."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..models.multiverse import (
    ActionSpec,
    ActionValidation,
    AutoPlayRequest,
    BranchActionRequest,
    BranchComparison,
    BranchNode,
    CompareRequest,
    MultiverseJob,
    MultiversePlanning,
    MultiverseSession,
    SessionCreate,
)
from ..models.state import MatchStateSnapshot
from ..multiverse.service import MultiverseError, MultiverseService
from .routes import RateLimiter

router = APIRouter(prefix="/api/multiverse", tags=["multiverse"])
ws_router = APIRouter()
branch_limiter = RateLimiter(limit=30, window_s=60)


def _svc(request: Request) -> MultiverseService:
    return request.app.state.services.multiverse


def _err(exc: MultiverseError) -> HTTPException:
    return HTTPException(exc.status, {"code": exc.code, "message": exc.message})


def _lite(s: MultiverseSession) -> dict:
    return {"session_id": s.session_id, "match_id": s.match_id, "decision_point_id": s.decision_point_id,
            "root_node_id": s.root_node_id, "mode": s.mode, "created_at": s.created_at, "max_depth": s.max_depth,
            "max_children": s.max_children, "max_nodes": s.max_nodes, "simulator_version": s.simulator_version,
            "actual_action": s.actual_action.model_dump(), "node_count": len(s.nodes)}


@router.post("/sessions", status_code=201)
def create_session(request: Request, body: SessionCreate) -> dict:
    try:
        return _lite(_svc(request).create_session(body))
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> dict:
    try:
        return _lite(_svc(request).get(session_id))
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/sessions/{session_id}/tree")
def get_tree(request: Request, session_id: str) -> dict:
    try:
        svc = _svc(request)
        return svc.tree(svc.get(session_id))
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/branches/{node_id}", response_model=BranchNode)
def get_node(request: Request, node_id: str) -> BranchNode:
    try:
        return _svc(request).find_node(node_id)[1]
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/branches/{node_id}/state", response_model=MatchStateSnapshot)
def get_state(request: Request, node_id: str) -> MatchStateSnapshot:
    """Exact frozen state at a node (rewind restores this; nothing is re-simulated)."""
    try:
        s, n = _svc(request).find_node(node_id)
        return s.snapshots[n.snapshot_id]
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/branches/{node_id}/options")
def get_options(request: Request, node_id: str) -> dict:
    from ..simulation.candidates import generate_candidates

    try:
        svc = _svc(request)
        s, n = svc.find_node(node_id)
        if n.status != "decision" or n.kind == "observed":
            return {"node_id": node_id, "options": [], "actual": None}
        md = svc.store.matches[s.match_id]
        snap = s.snapshots[n.snapshot_id]
        cands = generate_candidates(snap, md.roster)[:10]
        return {"node_id": node_id, "options": [c.model_dump() for c in cands],
                "actual": s.actual_action.model_dump() if n.kind == "root" else None,
                "recommendation_planning_id": n.recommendation_planning_id}
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.post("/branches/{node_id}/validate", response_model=ActionValidation)
def validate(request: Request, node_id: str, body: ActionSpec) -> ActionValidation:
    try:
        svc = _svc(request)
        s, n = svc.find_node(node_id)
        return svc.validate_action(s, n, body)
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.post("/branches/{node_id}/actions", response_model=MultiverseJob, status_code=202)
async def branch_action(request: Request, node_id: str, body: BranchActionRequest) -> MultiverseJob:
    """Create a child branch from `node_id` with the given action (manual) or the agents' choice."""
    branch_limiter.check(request)
    try:
        svc = _svc(request)
        s, _ = svc.find_node(node_id)
        return await svc.start_step(s.session_id, node_id, body)
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.post("/branches", response_model=MultiverseJob, status_code=202)
async def create_branch(request: Request, body: dict) -> MultiverseJob:
    """Alias: {"parent_node_id": ..., ...BranchActionRequest}."""
    parent = body.pop("parent_node_id", None)
    if not parent:
        raise HTTPException(422, {"code": "PARENT_REQUIRED", "message": "parent_node_id is required"})
    return await branch_action(request, parent, BranchActionRequest.model_validate(body))


@router.post("/branches/{node_id}/continue", response_model=MultiverseJob, status_code=202)
async def continue_branch(request: Request, node_id: str, body: BranchActionRequest | None = None) -> MultiverseJob:
    """Assisted: ask the agents for a recommendation (no branch). Autonomous: agents choose and branch."""
    branch_limiter.check(request)
    req = body or BranchActionRequest(mode="assisted")
    if req.mode is None:
        req.mode = "assisted"
    if req.action is not None:
        raise HTTPException(422, {"code": "UNEXPECTED_ACTION", "message": "Use /actions to submit a chosen action"})
    try:
        svc = _svc(request)
        s, _ = svc.find_node(node_id)
        return await svc.start_step(s.session_id, node_id, req)
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.post("/branches/{node_id}/auto-play", response_model=MultiverseJob, status_code=202)
async def auto_play(request: Request, node_id: str, body: AutoPlayRequest | None = None) -> MultiverseJob:
    branch_limiter.check(request)
    req = body or AutoPlayRequest()
    try:
        svc = _svc(request)
        s, _ = svc.find_node(node_id)
        return await svc.auto_play(s.session_id, node_id, req.max_steps, req.sample_kind)
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/jobs/{job_id}", response_model=MultiverseJob)
def get_job(request: Request, job_id: str) -> MultiverseJob:
    job = _svc(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404, {"code": "UNKNOWN_JOB", "message": job_id})
    return job


@router.post("/branches/{node_id}/cancel")
def cancel(request: Request, node_id: str) -> dict:
    svc = _svc(request)
    jobs = [j for j in svc.jobs.values() if j.parent_node_id == node_id and j.status in ("pending", "running")]
    return {"cancelled": [j.job_id for j in jobs if svc.cancel(j.job_id)]}


@router.get("/branches/{node_id}/trajectory")
def trajectory(request: Request, node_id: str) -> dict:
    """Frames/events from the root decision to this node (persisted: no model or simulation calls)."""
    try:
        svc = _svc(request)
        s, _ = svc.find_node(node_id)
        return svc.path_frames(s, node_id)
    except MultiverseError as exc:
        raise _err(exc) from exc


def _planning_for(svc: MultiverseService, node_id: str, which: str) -> MultiversePlanning:
    s, n = svc.find_node(node_id)
    pid = n.recommendation_planning_id if which == "recommendation" else n.planning_id
    if not pid or pid not in s.plannings:
        raise HTTPException(404, {"code": "NO_PLANNING", "message": "No planning result for this node"})
    return s.plannings[pid]


@router.get("/branches/{node_id}/analysis", response_model=MultiversePlanning)
def analysis(request: Request, node_id: str, which: str = "entering") -> MultiversePlanning:
    """The adversarial planning that produced this node (`which=recommendation` for assisted mode)."""
    try:
        return _planning_for(_svc(request), node_id, which)
    except MultiverseError as exc:
        raise _err(exc) from exc


@router.get("/branches/{node_id}/agents")
def agents(request: Request, node_id: str, which: str = "entering") -> dict:
    try:
        p = _planning_for(_svc(request), node_id, which)
    except MultiverseError as exc:
        raise _err(exc) from exc
    return {"planning_id": p.planning_id, "steps": [s.model_dump() for s in p.steps],
            "handoffs": [h.model_dump() for h in p.handoffs], "rounds": [r.model_dump() for r in p.rounds],
            "verification": p.verification_checks, "status": p.status, "live_model_calls": p.live_model_calls,
            "degraded": p.degraded}


@router.get("/plannings/{planning_id}", response_model=MultiversePlanning)
def planning(request: Request, planning_id: str) -> MultiversePlanning:
    for s in _svc(request).sessions.values():
        if planning_id in s.plannings:
            return s.plannings[planning_id]
    raise HTTPException(404, {"code": "UNKNOWN_PLANNING", "message": planning_id})


@router.post("/compare", response_model=BranchComparison)
def compare(request: Request, body: CompareRequest) -> BranchComparison:
    try:
        return _svc(request).compare(body.node_a, body.node_b, body.language)
    except MultiverseError as exc:
        raise _err(exc) from exc


@ws_router.websocket("/ws/multiverse/{session_id}")
async def multiverse_socket(ws: WebSocket, session_id: str) -> None:
    services = ws.app.state.services
    await ws.accept()
    try:
        services.multiverse.get(session_id)
    except MultiverseError:
        await ws.send_json({"type": "error", "message": "unknown session"})
        await ws.close(code=4404)
        return
    q = services.hub.subscribe(f"mv:{session_id}")

    async def pump() -> None:
        while True:
            msg = await q.get()
            await ws.send_text(json.dumps(msg, default=str))

    task = asyncio.create_task(pump())
    try:
        await ws.send_json({"type": "hello", "session_id": session_id})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        services.hub.unsubscribe(f"mv:{session_id}", q)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

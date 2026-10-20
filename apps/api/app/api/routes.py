"""REST API (versioned under /api, documented via OpenAPI at /docs)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..analytics.detector import compute_features, triage_score
from ..config import get_settings
from ..models.analysis import AnalyzeRequest, CounterfactualAnalysis, SimulateRequest
from ..models.common import SCHEMA_VERSION, SIMULATOR_VERSION, Language
from ..models.decisions import DecisionPoint
from ..models.events import ACTION_EVENTS, EventType, MatchEvent, TrackingFrame
from ..models.match import MatchInfo, MatchSummary
from ..models.overlay import Overlay
from ..models.recap import Recap
from ..models.simulation import SimulationRun, Trajectory
from ..models.state import MatchStateSnapshot
from ..models.stats import MatchStateView
from ..models.verification import EvidenceItem
from ..models.workflow import AnalysisWorkflowState
from ..services import metrics
from ..services.recap import build_recap
from ..simulation.candidates import actual_action_from_event

router = APIRouter(prefix="/api")


def _svc(request: Request):
    return request.app.state.services


class RateLimiter:
    """Per-client sliding window limiter for expensive endpoints."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "anon"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many analysis requests; please wait a moment.")
        q.append(now)


analyze_limiter = RateLimiter(limit=20, window_s=60)
simulate_limiter = RateLimiter(limit=6, window_s=60)


def _match(request: Request, match_id: str):
    md = _svc(request).store.matches.get(match_id)
    if md is None:
        raise HTTPException(404, f"Unknown match {match_id}")
    return md


def _analysis(request: Request, analysis_id: str) -> CounterfactualAnalysis:
    a = _svc(request).analyses.get(analysis_id)
    if a is None:
        raise HTTPException(404, f"Unknown analysis {analysis_id}")
    return a


# ------------------------------------------------------------------------------- health
@router.get("/health")
def health(request: Request) -> dict:
    s = get_settings()
    svc = _svc(request)
    return {"status": "ok" if svc.ready else "starting", "schema_version": SCHEMA_VERSION,
            "simulator_version": SIMULATOR_VERSION, "agent_mode": svc.analyses.provider.mode,
            "foundry_configured": s.foundry_configured, "foundry_deployment": s.foundry_model if s.foundry_configured
            else None, "foundry_client_error": svc.analyses.provider.init_error,
            "matches": len(svc.store.matches), "environment": s.environment}


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.summary()


diagnostics_limiter = RateLimiter(limit=3, window_s=60)


@router.post("/diagnostics/foundry")
async def foundry_diagnostics(request: Request) -> dict:
    """One tiny structured-output call through Agent Framework's FoundryChatClient (rate limited)."""
    import asyncio

    from agent_framework import Agent
    from pydantic import BaseModel

    diagnostics_limiter.check(request)
    provider = _svc(request).analyses.provider
    s = get_settings()
    if provider.mode != "foundry":
        return {"configured": False, "live": False, "detail": "Foundry not configured; agents use the deterministic policy planner"}
    client = provider.live_client()
    if client is None:
        return {"configured": True, "live": False, "detail": provider.init_error}

    class Ping(BaseModel):
        ok: bool
        model_says: str

    t0 = time.perf_counter()
    try:
        agent = Agent(client=client, name="diagnostics", instructions="Reply with JSON only.")
        resp = await asyncio.wait_for(agent.run('Return {"ok": true, "model_says": "<one word>"}',
                                                options={"response_format": Ping}), s.foundry_timeout_s)
        value = resp.value
        return {"configured": True, "live": True, "deployment": s.foundry_model, "response": value.model_dump()
                if value else resp.text[:200], "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:  # report, never crash
        return {"configured": True, "live": False, "deployment": s.foundry_model,
                "error": f"{type(exc).__name__}: {str(exc)[:300]}", "cause_chain": _cause_chain(exc),
                "checks": await _foundry_connectivity(s.foundry_project_endpoint)}


def _cause_chain(exc: BaseException, limit: int = 6) -> list[str]:
    """The underlying causes of a wrapped exception (SDKs often report only 'Connection error')."""
    out: list[str] = []
    cur = exc.__cause__ or exc.__context__
    while cur is not None and len(out) < limit:
        out.append(f"{type(cur).__name__}: {str(cur)[:240]}")
        cur = cur.__cause__ or cur.__context__
    return out


async def _foundry_connectivity(endpoint: str | None) -> dict:
    """Separates the usual failure points: DNS for the project host, then the managed identity token."""
    import asyncio
    import socket
    from urllib.parse import urlparse

    from azure.identity.aio import DefaultAzureCredential

    out: dict = {}
    host = urlparse(endpoint or "").hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        out["dns"] = f"ok ({infos[0][4][0]})"
    except Exception as exc:
        out["dns"] = f"{type(exc).__name__}: {exc}"
    try:
        async with DefaultAzureCredential(exclude_interactive_browser_credential=True) as cred:
            tok = await asyncio.wait_for(cred.get_token("https://ai.azure.com/.default"), 30)
            out["token"] = f"ok (expires {tok.expires_on})"
    except Exception as exc:
        out["token"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return out


# ------------------------------------------------------------------------------- scenarios / matches
@router.get("/scenarios")
def scenarios(request: Request) -> list[dict]:
    svc = _svc(request)
    out = []
    for d in svc.store.definitions:
        mid = svc.store.scenario_to_match.get(d.scenario_id)
        md = svc.store.matches.get(mid) if mid else None
        out.append({"scenario_id": d.scenario_id, "match_id": d.match_id, "title": d.title,
                    "description": d.description, "mode": d.mode, "seed": d.seed, "start_clock": d.start_clock,
                    "labels": d.labels.model_dump() if d.labels else None,
                    "duration_s": round(md.info.duration_ms / 1000, 1) if md else None,
                    "decision_count": len(md.decisions) if md else None})
    return out


@router.post("/scenarios/{scenario_id}/start")
def start_scenario(request: Request, scenario_id: str) -> dict:
    svc = _svc(request)
    mid = svc.store.scenario_to_match.get(scenario_id)
    if mid is None:
        raise HTTPException(404, f"Unknown scenario {scenario_id}")
    md = svc.store.matches[mid]
    return {"scenario_id": scenario_id, "match_id": mid, "websocket": f"/ws/matches/{mid}",
            "summary": md.summary.model_dump()}


@router.get("/matches", response_model=list[MatchSummary])
def matches(request: Request) -> list[MatchSummary]:
    return [md.summary for md in _svc(request).store.matches.values()]


@router.get("/matches/{match_id}", response_model=MatchInfo)
def match(request: Request, match_id: str) -> MatchInfo:
    return _match(request, match_id).info


@router.get("/matches/{match_id}/state", response_model=MatchStateView)
def match_state(request: Request, match_id: str, t_ms: int | None = Query(default=None, ge=0)) -> MatchStateView:
    from ..match_state.engine import MatchStateEngine

    md = _match(request, match_id)
    with metrics.timer("api.state_replay"):
        return MatchStateEngine(md.info).replay(md.events, until_ms=t_ms)


@router.get("/matches/{match_id}/events", response_model=list[MatchEvent])
def match_events(request: Request, match_id: str, from_ms: int = Query(0, ge=0), to_ms: int | None = None,
                 include_tracking: bool = False, types: str | None = None) -> list[MatchEvent]:
    md = _match(request, match_id)
    wanted = {EventType(t) for t in types.split(",")} if types else None
    out = []
    for e in md.events:
        if e.sim_time_ms < from_ms or (to_ms is not None and e.sim_time_ms > to_ms):
            continue
        if not include_tracking and e.event_type in (EventType.PLAYER_POSITION_UPDATED,
                                                     EventType.BALL_POSITION_UPDATED):
            continue
        if wanted and e.event_type not in wanted:
            continue
        out.append(e)
    return out


@router.get("/matches/{match_id}/events.jsonl", response_class=PlainTextResponse)
def match_events_jsonl(request: Request, match_id: str) -> str:
    md = _match(request, match_id)
    return "\n".join(e.model_dump_json(exclude_none=True) for e in md.events) + "\n"


@router.get("/matches/{match_id}/frames", response_model=list[TrackingFrame])
def match_frames(request: Request, match_id: str, from_ms: int = Query(0, ge=0), to_ms: int | None = None,
                 step: int = Query(1, ge=1, le=20)) -> list[TrackingFrame]:
    md = _match(request, match_id)
    fr = [f for f in md.frames if f.t_ms >= from_ms and (to_ms is None or f.t_ms <= to_ms)]
    return fr[::step]


@router.get("/matches/{match_id}/decisions", response_model=list[DecisionPoint])
def match_decisions(request: Request, match_id: str) -> list[DecisionPoint]:
    md = _match(request, match_id)
    store = _svc(request).store
    manual = [d for d in store.decisions.values() if d.match_id == match_id and d.source == "manual"]
    return sorted(md.decisions + manual, key=lambda d: d.sim_time_ms)


@router.post("/matches/{match_id}/events/{event_id}/decision", response_model=DecisionPoint, status_code=201)
def manual_decision(request: Request, match_id: str, event_id: str) -> DecisionPoint:
    """Turn any on-ball action into a decision point (analyst request), with the same features."""
    md = _match(request, match_id)
    store = _svc(request).store
    e = md.events_by_id.get(event_id)
    if e is None or e.event_type not in ACTION_EVENTS or not e.snapshot_id:
        raise HTTPException(422, "Event is not an on-ball action with a snapshot")
    existing = next((d for d in store.decisions.values() if d.event_id == event_id), None)
    if existing:
        return existing
    snap = md.snapshots[e.snapshot_id]
    feats, triggers, _ = compute_features(snap, md.roster, e)
    nxt = next((x for x in md.events if x.seq > e.seq and x.event_type in (
        EventType.PASS_COMPLETED, EventType.PASS_FAILED, EventType.SHOT_BLOCKED, EventType.SHOT_SAVED,
        EventType.SHOT_MISSED, EventType.GOAL, EventType.DRIBBLE_COMPLETED, EventType.DRIBBLE_FAILED)), None)
    actor = e.player_ids[0]
    dp = DecisionPoint(
        decision_point_id=f"{match_id}-manual-{e.seq:05d}", match_id=match_id, snapshot_id=snap.snapshot_id,
        event_id=e.event_id, actor_id=actor, actor_name=md.roster[actor].name, team_id=md.roster[actor].team_id,
        sim_time_ms=e.sim_time_ms, match_clock_ms=e.match_clock_ms,
        actual_action=actual_action_from_event(snap, md.roster, e.event_type.value, e.details.intended_receiver_id,
                                               e.end_x, e.end_y),
        actual_outcome=nxt.event_type.value if nxt else "UNKNOWN", outcome_event_id=nxt.event_id if nxt else None,
        outcome_time_ms=nxt.sim_time_ms if nxt else None, triggers=triggers, features=feats,
        candidate_score=triage_score(triggers, feats), source="manual")
    store.decisions[dp.decision_point_id] = dp
    return dp


@router.get("/matches/{match_id}/overlays", response_model=list[Overlay])
def match_overlays(request: Request, match_id: str, viewer_mode: str | None = None,
                   language: Language | None = None) -> list[Overlay]:
    md = _match(request, match_id)
    store = _svc(request).store
    out = list(md.event_overlays)
    for aid, ovs in store.analysis_overlays.items():
        a = store.analyses.get(aid)
        if a and a.match_id == match_id and not a.fault_injection:
            out.extend(ovs)
    out = [o for o in out if (viewer_mode is None or o.viewer_mode == viewer_mode)
           and (language is None or o.language == language)]
    return sorted(out, key=lambda o: (o.sim_time_ms, -o.priority))


# ------------------------------------------------------------------------------- decisions / analyses
@router.get("/decisions/{decision_id}", response_model=DecisionPoint)
def decision(request: Request, decision_id: str) -> DecisionPoint:
    dp = _svc(request).store.decisions.get(decision_id)
    if dp is None:
        raise HTTPException(404, f"Unknown decision {decision_id}")
    return dp


@router.get("/decisions/{decision_id}/snapshot", response_model=MatchStateSnapshot)
def decision_snapshot(request: Request, decision_id: str) -> MatchStateSnapshot:
    dp = decision(request, decision_id)
    return _svc(request).store.matches[dp.match_id].snapshots[dp.snapshot_id]


@router.post("/decisions/{decision_id}/analyze", response_model=CounterfactualAnalysis, status_code=202)
async def analyze(request: Request, decision_id: str, body: AnalyzeRequest | None = None) -> CounterfactualAnalysis:
    analyze_limiter.check(request)
    try:
        return await _svc(request).analyses.start(decision_id, body or AnalyzeRequest())
    except KeyError as exc:
        raise HTTPException(404, f"Unknown decision {decision_id}") from exc


@router.get("/analyses/{analysis_id}", response_model=CounterfactualAnalysis)
def analysis(request: Request, analysis_id: str) -> CounterfactualAnalysis:
    return _analysis(request, analysis_id)


@router.post("/analyses/{analysis_id}/cancel")
def cancel(request: Request, analysis_id: str) -> dict:
    _analysis(request, analysis_id)
    return {"cancelled": _svc(request).analyses.cancel(analysis_id)}


@router.get("/analyses/{analysis_id}/results", response_model=SimulationRun)
def results(request: Request, analysis_id: str) -> SimulationRun:
    a = _analysis(request, analysis_id)
    if a.simulation is None:
        raise HTTPException(409, f"Analysis is {a.status}; no simulation results yet")
    return a.simulation


@router.post("/analyses/{analysis_id}/simulate", response_model=SimulationRun, status_code=202)
async def simulate(request: Request, analysis_id: str, body: SimulateRequest) -> SimulationRun:
    simulate_limiter.check(request)
    _analysis(request, analysis_id)
    try:
        return await _svc(request).analyses.simulate(analysis_id, body)
    except KeyError as exc:
        raise HTTPException(409, "Analysis has no candidates yet") from exc


@router.get("/simulations/{job_id}", response_model=SimulationRun)
def simulation_job(request: Request, job_id: str) -> SimulationRun:
    run = _svc(request).analyses.sim_jobs.get(job_id)
    if run is None:
        raise HTTPException(404, f"Unknown simulation job {job_id}")
    return run


@router.get("/analyses/{analysis_id}/workflow", response_model=AnalysisWorkflowState)
def workflow(request: Request, analysis_id: str) -> AnalysisWorkflowState:
    return _analysis(request, analysis_id).workflow


@router.get("/analyses/{analysis_id}/overlays", response_model=list[Overlay])
def overlays(request: Request, analysis_id: str) -> list[Overlay]:
    _analysis(request, analysis_id)
    return _svc(request).analyses.overlays(analysis_id)


@router.get("/analyses/{analysis_id}/evidence", response_model=list[EvidenceItem])
def evidence(request: Request, analysis_id: str) -> list[EvidenceItem]:
    a = _analysis(request, analysis_id)
    return a.verification.accepted_evidence if a.verification else []


@router.get("/analyses/{analysis_id}/trajectories/{action_id}", response_model=Trajectory)
async def trajectory(request: Request, analysis_id: str, action_id: str,
                     rollout: int | None = Query(default=None, ge=0, le=499)) -> Trajectory:
    try:
        return await _svc(request).analyses.trajectory(analysis_id, action_id, rollout)
    except KeyError as exc:
        raise HTTPException(404, "Unknown analysis or action, or no simulation yet") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ------------------------------------------------------------------------------- recap
@router.post("/matches/{match_id}/recap", response_model=Recap)
def make_recap(request: Request, match_id: str, language: Language = "en") -> Recap:
    md = _match(request, match_id)
    store = _svc(request).store
    analyses = [a for a in store.analyses.values() if a.match_id == match_id and a.status == "verified"
                and not a.fault_injection]
    analyses.sort(key=lambda a: store.decisions[a.decision_point_id].sim_time_ms)
    seen, uniq = set(), []
    for a in analyses:
        if a.decision_point_id not in seen:
            seen.add(a.decision_point_id)
            uniq.append(a)
    rec = build_recap(md, uniq, language)
    store.recaps[(match_id, language)] = rec
    return rec


@router.get("/matches/{match_id}/recap", response_model=Recap)
def get_recap(request: Request, match_id: str, language: Language = "en") -> Recap:
    _match(request, match_id)
    rec = _svc(request).store.recaps.get((match_id, language))
    if rec is None:
        raise HTTPException(404, "No recap generated yet; POST to create one")
    return rec

"""Machine-readable, timestamped broadcast overlay instructions."""

from __future__ import annotations

from ..models.analysis import CounterfactualAnalysis
from ..models.decisions import DecisionPoint
from ..models.events import EventType, MatchEvent
from ..models.match import MatchInfo
from ..models.overlay import Overlay, OverlayDataField, OverlayExpiry
from ..verification.evidence import action_keys, pct

DURATION_MS = {"casual": 8000, "analyst": 12000, "broadcaster": 6000}
PRIORITY = {"high": 75, "medium": 60, "low": 45}
PUBLISH_DELAY_MS = 1500


def analysis_overlays(analysis: CounterfactualAnalysis, decision: DecisionPoint, priority: str = "medium"
                      ) -> list[Overlay]:
    anchor_sim = (decision.outcome_time_ms or decision.sim_time_ms) + PUBLISH_DELAY_MS
    anchor_clock = decision.match_clock_ms + (anchor_sim - decision.sim_time_ms)
    base_priority = PRIORITY.get(priority, 60)
    status = analysis.verification.status if analysis.verification else "rejected"
    out: list[Overlay] = []
    if analysis.status != "verified" or analysis.simulation is None:
        for mode in ("casual", "analyst", "broadcaster"):
            for lang in ("en", "nl"):
                out.append(Overlay(
                    overlay_id=f"ov-{analysis.analysis_id}-{mode}-{lang}", type="analysis_unavailable",
                    match_id=analysis.match_id, decision_point_id=decision.decision_point_id,
                    analysis_id=analysis.analysis_id, viewer_mode=mode, language=lang,
                    match_time_ms=anchor_clock, sim_time_ms=anchor_sim, duration_ms=4000, priority=20,
                    headline="Analysis unavailable" if lang == "en" else "Analyse niet beschikbaar",
                    narrative=("This moment could not be verified; showing match statistics only." if lang == "en"
                               else "Dit moment kon niet worden geverifieerd; alleen wedstrijdstatistieken."),
                    verification_status=status, expires=OverlayExpiry(on_event_types=["GOAL"], max_age_ms=4000),
                    render_hint={"position": "lower_third", "tone": "muted"}))
        return out
    sim = analysis.simulation
    keys = action_keys(analysis)
    res = {r.action_id: r for r in sim.results}
    cand = {c.action_id: c for c in analysis.candidates}
    actual = next(c for c in analysis.candidates if c.is_actual)
    best_id = max((c.action_id for c in analysis.candidates if not c.is_actual), key=lambda a: res[a].p_goal.value)
    for nar in analysis.narratives:
        mode = nar.audience
        fields: list[OverlayDataField] = []
        for aid in ([best_id] if mode == "casual" else [actual.action_id, best_id]):
            r = res[aid]
            k = keys[aid]
            fields.append(OverlayDataField(key=f"{k}_p_goal", label=cand[aid].label.replace(" (actual)", ""),
                                           value=r.p_goal.value, display=pct(r.p_goal.value, nar.language),
                                           source_ref=f"results.{k}.p_goal"))
        if mode != "casual":
            fields.append(OverlayDataField(key="rollouts", label="Simulations per option", value=sim.config.rollouts,
                                           display=str(sim.config.rollouts), source_ref="sim.rollouts"))
        out.append(Overlay(
            overlay_id=f"ov-{analysis.analysis_id}-{mode}-{nar.language}", type="decision_comparison",
            match_id=analysis.match_id, decision_point_id=decision.decision_point_id,
            analysis_id=analysis.analysis_id, viewer_mode=mode, language=nar.language,
            match_time_ms=anchor_clock, sim_time_ms=anchor_sim, duration_ms=DURATION_MS[mode],
            priority=base_priority + (5 if mode == "broadcaster" else 0),
            headline=nar.headline, narrative=nar.body if mode != "broadcaster" else (nar.caption or nar.body),
            caption=nar.caption, data_fields=fields, source_refs=nar.evidence_refs,
            verification_status=status,
            expires=OverlayExpiry(on_event_types=["GOAL", "MATCH_ENDED", "POSSESSION_CHANGED"] if mode == "broadcaster"
                                  else ["GOAL", "MATCH_ENDED"], max_age_ms=DURATION_MS[mode] * 2),
            render_hint={"position": "lower_third" if mode == "broadcaster" else "pitch_card",
                         "accent": "#60A5FA", "best_action_id": best_id}))
    return out


def event_overlays(info: MatchInfo, events: list[MatchEvent]) -> list[Overlay]:
    """Deterministic overlays for major observed events (goals get top priority)."""
    out: list[Overlay] = []
    names = {p.player_id: p.name for p in info.players}
    teams = {info.home.team_id: info.home.name, info.away.team_id: info.away.name}
    for e in events:
        if e.event_type != EventType.GOAL:
            continue
        scorer = names.get(e.player_ids[0], "") if e.player_ids else ""
        score = f"{e.details.score_home}-{e.details.score_away}"
        for mode in ("casual", "analyst", "broadcaster"):
            for lang in ("en", "nl"):
                out.append(Overlay(
                    overlay_id=f"ov-{e.event_id}-{mode}-{lang}", type="goal", match_id=info.match_id,
                    viewer_mode=mode, language=lang, match_time_ms=e.match_clock_ms, sim_time_ms=e.sim_time_ms,
                    duration_ms=7000, priority=100, headline="GOAL" if lang == "en" else "DOELPUNT",
                    narrative=f"{scorer} ({teams.get(e.team_id or '', '')}) {score}",
                    caption=f"{scorer} {score}", source_refs=[e.event_id], verification_status="observed",
                    expires=OverlayExpiry(on_event_types=["MATCH_ENDED"], max_age_ms=7000),
                    render_hint={"position": "full_width", "accent": "#22C55E"}))
    return out

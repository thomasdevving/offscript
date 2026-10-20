from __future__ import annotations

from .common import Contract, Language


class RecapItem(Contract):
    text: str
    match_clock: str | None = None
    event_ids: list[str] = []
    analysis_ids: list[str] = []
    kind: str = "event"


class PlayerPerformance(Contract):
    player_id: str
    name: str
    team_id: str
    metrics: dict[str, float | int]
    summary: str
    event_ids: list[str] = []


class MomentumWindow(Contract):
    start_clock: str
    end_clock: str
    possession_share: dict[str, float]
    final_third_entries: dict[str, int]


class RecapFormat(Contract):
    headline: str
    story: list[str]


class Recap(Contract):
    recap_id: str
    match_id: str
    language: Language
    generated_at: str
    generated_by: str
    final_score: dict[str, int]
    score_line: str
    key_events: list[RecapItem]
    decision_insights: list[RecapItem]
    player_performances: list[PlayerPerformance]
    momentum: list[MomentumWindow]
    casual: RecapFormat
    analyst: RecapFormat
    referenced_event_ids: list[str]
    referenced_analysis_ids: list[str]
    disclaimer: str

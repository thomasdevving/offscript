from __future__ import annotations

from typing import Literal

from .common import SCHEMA_VERSION, Contract, Language, ViewerMode

OverlayType = Literal["decision_comparison", "goal", "match_stat", "analysis_unavailable"]


class OverlayDataField(Contract):
    key: str
    label: str
    value: float | int | str
    display: str
    source_ref: str


class OverlayExpiry(Contract):
    on_event_types: list[str] = []
    max_age_ms: int | None = None


class Overlay(Contract):
    schema_version: str = SCHEMA_VERSION
    overlay_id: str
    type: OverlayType
    match_id: str
    decision_point_id: str | None = None
    analysis_id: str | None = None
    viewer_mode: ViewerMode
    language: Language
    match_time_ms: int
    sim_time_ms: int
    duration_ms: int
    priority: int
    headline: str
    narrative: str
    caption: str | None = None
    data_fields: list[OverlayDataField] = []
    source_refs: list[str] = []
    verification_status: str
    expires: OverlayExpiry
    render_hint: dict[str, str | int | float] = {}

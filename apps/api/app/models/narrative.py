from __future__ import annotations

from typing import Literal

from .common import Contract, Language, ViewerMode


class Narrative(Contract):
    narrative_id: str
    analysis_id: str
    audience: ViewerMode
    language: Language
    headline: str
    body: str
    bullets: list[str] = []
    caption: str | None = None
    evidence_refs: list[str] = []
    verification_status: Literal["verified", "rejected", "pending"] = "pending"
    verification_notes: list[str] = []
    generated_by: str
    is_live_model_output: bool
    created_at: str

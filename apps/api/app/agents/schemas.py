"""Structured outputs each agent must return.

The schemas are deliberately free of length/size keywords so they work with strict JSON-schema
structured outputs; limits (number of proposals, text length) are enforced in code after parsing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DecisionAssessment(BaseModel):
    decision_point_id: str
    analyze: bool
    priority: Literal["high", "medium", "low"]
    importance_justification: str


class Proposal(BaseModel):
    candidate_id: str | None = None
    action_type: Literal["shoot", "pass", "dribble"] | None = None
    target_player_id: str | None = None
    target_x: float | None = None
    target_y: float | None = None
    rationale: str = ""


class StrategyProposal(BaseModel):
    proposals: list[Proposal]
    notes: str = ""


class RevisionRequest(BaseModel):
    candidate_id: str
    reason: str


class SimulationReport(BaseModel):
    simulation_run_id: str | None = None
    rollouts_used: int
    stable: bool
    revision_requests: list[RevisionRequest] = []
    summary: str = ""


class VerificationDecision(BaseModel):
    status: Literal["verified", "rejected"]
    route: Literal["explain", "revise_strategy", "resimulate", "unavailable", "publish"]
    issues: list[str] = []
    assessment: str = ""


class NarrativeDraft(BaseModel):
    audience: Literal["casual", "analyst", "broadcaster"]
    language: Literal["en", "nl"]
    headline: str
    body: str
    bullets: list[str] = []
    caption: str | None = None
    evidence_refs: list[str] = []


class ExplanationBundle(BaseModel):
    narratives: list[NarrativeDraft]

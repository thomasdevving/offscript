from __future__ import annotations

from typing import Literal

from .common import Contract

VerificationStatus = Literal["pending", "verified", "verified_with_warnings", "rejected"]


class EvidenceItem(Contract):
    ref: str
    label: str
    value: float | int | str
    unit: str = ""
    display: str


class VerificationCheck(Contract):
    check_id: str
    name: str
    passed: bool
    severity: Literal["error", "warning"] = "error"
    details: str = ""


class VerificationRecord(Contract):
    verification_id: str
    analysis_id: str
    status: VerificationStatus
    checks: list[VerificationCheck]
    failures: list[str]
    accepted_evidence: list[EvidenceItem]
    verified_at: str
    agent_assessment: str = ""

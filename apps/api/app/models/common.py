from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1.0"
SIMULATOR_VERSION = "parallel-sim-1.0.0"

ViewerMode = Literal["casual", "analyst", "broadcaster"]
Language = Literal["en", "nl"]
JobStatus = Literal["pending", "running", "completed", "failed", "timed_out", "cancelled"]


class Contract(BaseModel):
    """Base for all API contracts: strict field names, JSON-friendly."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FrozenContract(BaseModel):
    """Immutable record (events, snapshots)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_clock(ms: int) -> str:
    total_s = ms // 1000
    return f"{total_s // 60:02d}:{total_s % 60:02d}"

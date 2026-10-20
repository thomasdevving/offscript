from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.config import REPO_ROOT, Settings  # noqa: E402
from app.services.hub import EventHub  # noqa: E402
from app.services.store import Store  # noqa: E402
from app.synthetic_data.scenarios import generate, load_scenarios  # noqa: E402

SCENARIOS = REPO_ROOT / "scenarios"


@pytest.fixture(scope="session")
def definitions():
    return {d.scenario_id: d for d in load_scenarios(SCENARIOS)}


@pytest.fixture(scope="session")
def demo_match(definitions):
    return generate(definitions["shoot_vs_pass"])


@pytest.fixture(scope="session")
def demo_decision_snapshot(demo_match):
    ev = next(e for e in demo_match.events if e.event_id in demo_match.decision_event_ids)
    return ev, demo_match.snapshots[ev.snapshot_id]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(agent_mode="policy", use_analysis_cache=False, data_dir=tmp_path, scenarios_dir=SCENARIOS,
                    default_rollouts=120, simulation_time_budget_s=30)


@pytest.fixture
def store(settings) -> Store:
    s = Store(settings.scenarios_dir, settings.data_dir)
    s.load(only=["shoot_vs_pass", "risky_through_ball"])
    return s


@pytest.fixture
def hub() -> EventHub:
    return EventHub()

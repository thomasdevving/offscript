"""Scenario definitions (JSON files under /scenarios) and deterministic match generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..models.match import MatchSummary
from ..simulation import geometry as g
from .match_generator import GeneratedMatch, MatchGenerator
from .roster import KICKOFF, ROSTER, starters, template_positions


class ScenarioLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_actor: str
    expected_triggers: list[str]
    expected_alternative_types: list[str]
    expected_observed_outcomes: list[str]


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    match_id: str
    title: str
    description: str
    mode: Literal["scenario", "procedural"]
    seed: int
    period: int
    start_clock: str
    score: dict[str, int]
    attacking_team: str
    carrier: str | None
    coordinates: Literal["attack_frame"] = "attack_frame"
    positions: dict[str, tuple[float, float]] | None
    velocities: dict[str, tuple[float, float]] | None
    script: list[dict]  # steps may carry "runs": {player_id: [x, y]} choreography
    continuation_s: float
    frame_hz: int = 10
    labels: ScenarioLabels | None = None

    @property
    def start_clock_ms(self) -> int:
        m, s = self.start_clock.split(":")
        return (int(m) * 60 + int(s)) * 1000

    def validate_positions(self) -> None:
        if self.positions is None:
            return
        on_pitch = {p.player_id for t in ("HCF", "NVA") for p in starters(t)}
        missing = on_pitch - set(self.positions)
        extra = set(self.positions) - on_pitch
        if missing or extra:
            raise ValueError(f"{self.scenario_id}: positions missing {sorted(missing)} extra {sorted(extra)}")
        for pid, (x, y) in self.positions.items():
            if not g.in_bounds(x, y):
                raise ValueError(f"{self.scenario_id}: {pid} starts outside the pitch")


def load_scenarios(directory: Path) -> list[ScenarioDefinition]:
    out = []
    for path in sorted(directory.glob("*/scenario.json")):
        defn = ScenarioDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        defn.validate_positions()
        out.append(defn)
    order = ["shoot_vs_pass", "risky_through_ball", "counterattack", "defensive_pressure", "procedural_segment"]
    out.sort(key=lambda d: order.index(d.scenario_id) if d.scenario_id in order else 99)
    return out


def generate(defn: ScenarioDefinition) -> GeneratedMatch:
    positions = defn.positions
    carrier = defn.carrier
    if positions is None:
        # Procedural mode starts from a kick-off by the attacking team.
        positions = {}
        for team in ("HCF", "NVA"):
            tpl = template_positions(starters(team), KICKOFF)
            for pid, (x, y) in tpl.items():
                positions[pid] = (x, y) if team == defn.attacking_team else (g.PITCH_LENGTH - x, g.PITCH_WIDTH - y)
        carrier = next(p.player_id for p in starters(defn.attacking_team) if p.role == "ST")
        positions[carrier] = (52.0, 34.0)
    gen = MatchGenerator(
        match_id=defn.match_id,
        title=defn.title,
        seed=defn.seed,
        period=defn.period,
        start_clock_ms=defn.start_clock_ms,
        score=defn.score,
        attacking_team=defn.attacking_team,
        positions_attack_frame=positions,
        velocities_attack_frame=defn.velocities,
        carrier_id=carrier,
        frame_hz=defn.frame_hz,
        scenario_id=defn.scenario_id,
        description=defn.description,
        mode=defn.mode,
    )
    return gen.run(defn.script, defn.continuation_s)


def summary_of(match: GeneratedMatch, decision_count: int) -> MatchSummary:
    info = match.info
    return MatchSummary(
        match_id=info.match_id,
        title=info.title,
        scenario_id=info.scenario_id,
        home=info.home.name,
        away=info.away.name,
        period=info.period,
        start_clock=f"{info.start_clock_ms // 60000:02d}:{(info.start_clock_ms // 1000) % 60:02d}",
        duration_s=round(info.duration_ms / 1000, 1),
        mode=info.settings.mode,
        description=info.description,
        decision_count=decision_count,
    )


__all__ = ["ScenarioDefinition", "load_scenarios", "generate", "summary_of", "ROSTER"]

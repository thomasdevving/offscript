"""In-memory store for generated matches, decisions, analyses and recaps.

Matches are generated deterministically from the scenario definitions at start-up (a few
seconds), so the store needs no external database for the demo; generated artefacts and
verified analyses can be written to disk for inspection and replay.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..analytics.detector import DecisionDetector
from ..models.analysis import CounterfactualAnalysis
from ..models.decisions import DecisionPoint
from ..models.events import MatchEvent, TrackingFrame
from ..models.match import MatchInfo, MatchSummary, Player
from ..models.overlay import Overlay
from ..models.recap import Recap
from ..models.state import MatchStateSnapshot
from ..synthetic_data.scenarios import ScenarioDefinition, generate, load_scenarios, summary_of
from . import metrics
from .overlays import event_overlays

log = logging.getLogger("offscript.store")


@dataclass
class MatchData:
    definition: ScenarioDefinition
    info: MatchInfo
    events: list[MatchEvent]
    frames: list[TrackingFrame]
    snapshots: dict[str, MatchStateSnapshot]
    roster: dict[str, Player]
    decisions: list[DecisionPoint]
    suppressed: list[dict]
    labelled_decision_event_ids: list[str]
    scripted_event_ids: list[str]
    event_overlays: list[Overlay]
    events_by_id: dict[str, MatchEvent] = field(default_factory=dict)
    feature_cache: dict[str, tuple] = field(default_factory=dict)

    @property
    def summary(self) -> MatchSummary:
        return summary_of(self.info, len(self.decisions))


class Store:
    def __init__(self, scenarios_dir: Path, data_dir: Path):
        self.scenarios_dir = scenarios_dir
        self.data_dir = data_dir
        self.matches: dict[str, MatchData] = {}
        self.scenario_to_match: dict[str, str] = {}
        self.decisions: dict[str, DecisionPoint] = {}
        self.analyses: dict[str, CounterfactualAnalysis] = {}
        self.analysis_overlays: dict[str, list[Overlay]] = {}
        self.analysis_by_cache_key: dict[str, str] = {}
        self.recaps: dict[tuple[str, str], Recap] = {}
        self.lock = threading.RLock()
        self.definitions: list[ScenarioDefinition] = []

    def load(self, only: list[str] | None = None) -> None:
        self.definitions = load_scenarios(self.scenarios_dir)
        for d in self.definitions:
            if only and d.scenario_id not in only:
                continue
            self.add_generated(d)

    def add_generated(self, d: ScenarioDefinition) -> MatchData:
        with metrics.timer("startup.generate_match"):
            gm = generate(d)
        cache: dict[str, tuple] = {}
        det = DecisionDetector(gm.info.match_id, gm.roster, gm.snapshots, feature_cache=cache)
        for e in gm.events:
            with metrics.timer("detector.on_event"):
                det.on_event(e)
        md = MatchData(definition=d, info=gm.info, events=gm.events, frames=gm.frames, snapshots=gm.snapshots,
                       roster=gm.roster, decisions=det.decisions, suppressed=det.suppressed,
                       labelled_decision_event_ids=gm.decision_event_ids, scripted_event_ids=gm.scripted_event_ids,
                       event_overlays=event_overlays(gm.info, gm.events),
                       events_by_id={e.event_id: e for e in gm.events}, feature_cache=cache)
        with self.lock:
            self.matches[md.info.match_id] = md
            self.scenario_to_match[d.scenario_id] = md.info.match_id
            for dp in md.decisions:
                self.decisions[dp.decision_point_id] = dp
        log.info("generated %s: %d events, %d frames, %d decisions", md.info.match_id, len(md.events),
                 len(md.frames), len(md.decisions))
        return md

    def match_for_decision(self, decision_id: str) -> MatchData | None:
        dp = self.decisions.get(decision_id)
        return self.matches.get(dp.match_id) if dp else None

    # ---------------------------------------------------------------- persistence
    def export_match(self, match_id: str) -> Path:
        """Write the event stream as JSONL plus metadata for inspection/reproduction."""
        md = self.matches[match_id]
        out = self.data_dir / "generated" / md.definition.scenario_id
        out.mkdir(parents=True, exist_ok=True)
        with (out / "events.jsonl").open("w", encoding="utf-8") as f:
            for e in md.events:
                f.write(e.model_dump_json(exclude_none=True) + "\n")
        (out / "match.json").write_text(md.info.model_dump_json(indent=2), encoding="utf-8")
        (out / "decisions.json").write_text(json.dumps([d.model_dump(mode="json") for d in md.decisions], indent=2),
                                            encoding="utf-8")
        return out

    def cache_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self.data_dir / "cache" / "analyses" / f"{h}.json"

    def save_cached(self, key: str, analysis: CounterfactualAnalysis) -> None:
        p = self.cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(analysis.model_dump_json(), encoding="utf-8")

    def load_cached(self, key: str) -> CounterfactualAnalysis | None:
        p = self.cache_path(key)
        if not p.exists():
            return None
        try:
            return CounterfactualAnalysis.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:  # stale schema -> ignore cache entry
            return None

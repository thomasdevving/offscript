"""Warm the analysis cache for every labelled scenario decision (optional, before recording a demo).

Cached analyses are real outputs of the same workflow, stored under apps/api/data/cache and
served with `cached=true` (shown as "Replayed from cache" in the UI). Cache keys include the
agent mode and model deployment, so policy-mode results are never shown as Foundry results.

Usage: python scripts/precompute_demo.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.models.analysis import AnalyzeRequest  # noqa: E402
from app.services.analysis_service import AnalysisService  # noqa: E402
from app.services.hub import EventHub  # noqa: E402
from app.services.store import Store  # noqa: E402


async def main() -> None:
    settings = get_settings()
    store = Store(settings.scenarios_dir, settings.data_dir)
    store.load()
    svc = AnalysisService(settings, store, EventHub())
    for md in store.matches.values():
        for dp in md.decisions:
            a = await svc.start(dp.decision_point_id, AnalyzeRequest())
            a = await svc.wait(a.analysis_id)
            print(f"{dp.decision_point_id:32s} {a.status:12s} cached={a.cached} mode={a.model.agent_mode}")
        store.export_match(md.info.match_id)


if __name__ == "__main__":
    asyncio.run(main())

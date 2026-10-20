"""Optional live integration test against a real Microsoft Foundry deployment.

Skipped unless FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL are set and credentials are
available (az login / managed identity). Run with:  pytest -m foundry
"""

import os

import pytest

from app.models.analysis import AnalyzeRequest
from app.services.analysis_service import AnalysisService

pytestmark = [pytest.mark.foundry, pytest.mark.asyncio]


@pytest.mark.skipif(not (os.getenv("FOUNDRY_PROJECT_ENDPOINT") and os.getenv("FOUNDRY_MODEL")),
                    reason="Foundry not configured")
async def test_live_foundry_workflow(settings, store, hub):
    settings.agent_mode = "foundry"
    settings.foundry_project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    settings.foundry_model = os.environ["FOUNDRY_MODEL"]
    svc = AnalysisService(settings, store, hub)
    md = store.matches["demo-match-073"]
    dp = next(d for d in md.decisions if d.event_id in md.labelled_decision_event_ids)
    a = await svc.wait((await svc.start(dp.decision_point_id, AnalyzeRequest())).analysis_id)
    assert a.status == "verified", a.workflow.errors
    assert a.model.live_model_calls > 0, [s.notes for s in a.workflow.steps]
    live_steps = [s for s in a.workflow.steps if s.live_model]
    assert live_steps and all(s.model.startswith("foundry:") for s in live_steps)
    # Live narratives must still pass deterministic grounding (or be replaced by labelled templates).
    assert all(n.verification_status == "verified" for n in a.narratives)

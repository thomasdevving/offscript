"""A live agent whose async tool is cancelled by the time budget must leave a clean, copyable trace.

Regression: on the live deployment the Multiverse Simulation Agent's response-matrix tool ran past the
25 s live budget; the cancelled tool's unfinished coroutine was recorded as its result, and the final
`deepcopy` of the planning crashed with "cannot pickle 'coroutine' object".
"""

import asyncio
import copy

from agent_framework import tool
from pydantic import BaseModel

from app.agents.policy_client import PolicyChatClient, PolicyDecision, PolicyTurn
from app.agents.runner import AgentRunner, ChatClientProvider
from app.models.multiverse import MultiversePlanning


class Out(BaseModel):
    ok: bool


@tool(name="slow_tool", description="A tool that takes longer than the agent's live budget.")
async def slow_tool() -> dict:
    await asyncio.sleep(5)
    return {"done": True}


def calls_slow_tool(turn: PolicyTurn) -> PolicyDecision:
    if "slow_tool" not in turn.results:
        return PolicyDecision(tool_calls=[("slow_tool", {})])
    return PolicyDecision(final={"ok": True})


def answers_directly(turn: PolicyTurn) -> PolicyDecision:
    return PolicyDecision(final={"ok": True})


class FakeLiveProvider(ChatClientProvider):
    """Stands in for Foundry: the 'live' client calls the slow tool."""

    def __init__(self, settings):
        super().__init__(settings)
        self.mode = "foundry"

    def live_client(self):
        return PolicyChatClient(policy=calls_slow_tool, function_invocation_configuration=self.function_config())


async def test_cancelled_live_tool_call_leaves_a_copyable_trace(settings):
    planning = MultiversePlanning(planning_id="p", node_id="n", snapshot_id="s", correlation_id="c", mode="manual")
    runner = AgentRunner(settings, FakeLiveProvider(settings), planning)

    out, step = await runner.run("simulation_agent", "matrix", "instructions", [slow_tool], "prompt", Out,
                                 answers_directly, live_timeout_s=0.3)

    assert out.ok and step.status == "degraded" and step.model == "policy"  # labelled fallback took over
    cancelled = [tc for tc in step.tool_calls if tc.tool_name == "slow_tool"]
    assert cancelled and cancelled[0].status == "error" and "cancelled" in cancelled[0].result_summary
    copy.deepcopy(planning)  # used to raise TypeError: cannot pickle 'coroutine' object
    planning.model_dump_json()

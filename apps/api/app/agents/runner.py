"""Runs one specialised agent (Microsoft Agent Framework `Agent`) with tools, tracing and fallback.

Order of attempts for every agent call:
1. (fault injection only) a client that simulates a provider outage,
2. the live Microsoft Foundry deployment (FoundryChatClient) when configured,
3. the deterministic policy client (always available, always labelled `policy`).

Every tool call is recorded by Agent Framework function middleware into the workflow trace.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from agent_framework import Agent, FunctionInvocationContext, function_middleware
from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..models.common import new_id, utcnow
from ..models.workflow import AgentName, AgentStep, AnalysisWorkflowState, ToolCallRecord
from .policy_client import FailingChatClient, PolicyChatClient, PolicyFn

log = logging.getLogger("offscript.agents")
T = TypeVar("T", bound=BaseModel)
Publish = Callable[[str, dict[str, Any]], Awaitable[None] | None]


class AgentFailure(RuntimeError):
    pass


def _summarize(value: Any, limit: int = 1800) -> Any:
    if value is None:
        return None
    # A tool cancelled mid-run (e.g. the agent's time budget ran out) leaves its unfinished coroutine
    # as the result: never store it (the trace must stay copyable and JSON-serialisable).
    if asyncio.iscoroutine(value):
        value.close()
        return {"cancelled": "the tool call did not finish (agent time budget)"}
    if inspect.isawaitable(value):
        return {"cancelled": "the tool call did not finish (agent time budget)"}
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if hasattr(value, "text") and not isinstance(value, dict | list | str):
        value = getattr(value, "text", str(value))
    if isinstance(value, list) and value and hasattr(value[0], "text"):
        value = "".join(getattr(c, "text", "") or "" for c in value)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return value[:limit]
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        return str(value)[:limit]
    if len(text) <= limit:
        return value
    return text[:limit] + "...(truncated)"


class ChatClientProvider:
    """Creates the Foundry client lazily; keeps credentials server-side."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._foundry = None
        self.mode = settings.effective_agent_mode
        self.init_error: str | None = None

    @property
    def deployment(self) -> str | None:
        return self.settings.foundry_model

    def function_config(self) -> dict[str, Any]:
        return {"max_function_calls": self.settings.agent_max_tool_calls, "max_iterations": 6,
                "max_consecutive_errors_per_request": 2}

    def live_client(self):
        if self.mode != "foundry":
            return None
        if self._foundry is None and self.init_error is None:
            try:
                from azure.identity import DefaultAzureCredential

                credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
                if self.settings.foundry_openai_endpoint:
                    from agent_framework.openai import OpenAIChatClient

                    self._foundry = OpenAIChatClient(
                        model=self.settings.foundry_model,
                        azure_endpoint=self.settings.foundry_openai_endpoint,
                        credential=credential,
                        function_invocation_configuration=self.function_config(),
                    )
                else:
                    from agent_framework.foundry import FoundryChatClient

                    self._foundry = FoundryChatClient(
                        project_endpoint=self.settings.foundry_project_endpoint,
                        model=self.settings.foundry_model,
                        credential=credential,
                        function_invocation_configuration=self.function_config(),
                    )
            except Exception as exc:  # configuration errors -> degrade to policy
                self.init_error = f"{type(exc).__name__}: {exc}"
                log.warning("Foundry client unavailable: %s", self.init_error)
        return self._foundry

    def policy_client(self, policy: PolicyFn) -> PolicyChatClient:
        return PolicyChatClient(policy=policy, function_invocation_configuration=self.function_config())

    @property
    def live_label(self) -> str:
        return f"foundry:{self.settings.foundry_model}"


def _extract_json(text: str) -> Any:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


class AgentRunner:
    def __init__(self, settings: Settings, provider: ChatClientProvider, state: AnalysisWorkflowState,
                 publish: Publish | None = None, simulate_outage: bool = False):
        self.settings = settings
        self.provider = provider
        self.state = state
        self.publish = publish
        self.simulate_outage = simulate_outage
        self.live_calls = 0
        self.policy_fallbacks = 0

    async def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.publish is None:
            return
        r = self.publish(kind, payload)
        if asyncio.iscoroutine(r):
            await r

    def _recorder(self, step: AgentStep):
        runner = self

        @function_middleware
        async def record_tool_call(context: FunctionInvocationContext, call_next) -> None:
            t0 = time.perf_counter()
            started = utcnow().isoformat()
            status = "ok"
            try:
                await call_next()
            except (Exception, asyncio.CancelledError):
                status = "error"
                raise
            finally:
                args = context.arguments
                if isinstance(args, BaseModel):
                    args = args.model_dump(mode="json")
                args = dict(args or {}) if isinstance(args, dict) else {"value": str(args)}
                # Keep the recorded arguments plain JSON whatever the client passed in.
                args = json.loads(json.dumps(args, default=str))
                rec = ToolCallRecord(
                    call_id=new_id("tool"), tool_name=context.function.name,
                    arguments=args,
                    result_summary=_summarize(context.result), status=status,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2), started_at=started,
                )
                step.tool_calls.append(rec)
                await runner._emit("tool_call", {"step_id": step.step_id, "agent": step.agent,
                                                 "tool": rec.tool_name, "status": rec.status})
        return record_tool_call

    async def run(
        self,
        agent: AgentName,
        task: str,
        instructions: str,
        tools: list,
        prompt: str,
        output_model: type[T],
        policy: PolicyFn,
        attempt: int = 1,
        live_timeout_s: float | None = None,
    ) -> tuple[T, AgentStep]:
        """Run one agent step: live model first (if configured), then the labelled policy planner.

        `live_timeout_s` overrides the live time budget for agents whose tools themselves take long
        (e.g. a Monte Carlo response matrix); the budget covers model calls and tool execution."""
        step = AgentStep(step_id=new_id("step"), agent=agent, task=task, attempt=attempt,
                         started_at=utcnow().isoformat(), model="pending")
        self.state.steps.append(step)
        await self._emit("agent_started", {"step_id": step.step_id, "agent": agent, "task": task, "attempt": attempt})
        t0 = time.perf_counter()
        attempts: list[tuple[str, Any, str, bool]] = []
        if self.simulate_outage:
            attempts.append(("fault", FailingChatClient(), "simulated-outage", False))
        live = None if self.simulate_outage else self.provider.live_client()
        if live is not None:
            attempts.append(("live", live, self.provider.live_label, True))
        elif self.provider.mode == "foundry" and self.provider.init_error:
            step.notes.append(f"Foundry client could not be created: {self.provider.init_error}")
        attempts.append(("policy", self.provider.policy_client(policy), "policy", False))
        failures = 0
        for kind, client, label, is_live in attempts:
            step.model = label
            step.live_model = is_live
            try:
                long_output = agent == "explanation_agent"
                max_tokens = (self.settings.foundry_explanation_max_output_tokens if long_output
                              else self.settings.foundry_max_output_tokens)
                ag = Agent(client=client, name=agent, instructions=instructions, tools=tools,
                           middleware=[self._recorder(step)],
                           default_options={"max_tokens": max_tokens} if is_live else None)
                live_timeout = live_timeout_s or (self.settings.foundry_explanation_timeout_s if long_output
                                                  else self.settings.foundry_timeout_s)
                timeout = live_timeout if is_live else max(60.0, self.settings.simulation_time_budget_s * 3)
                resp = await asyncio.wait_for(ag.run(prompt, options={"response_format": output_model}), timeout)
                try:
                    value = resp.value
                except (ValidationError, ValueError):
                    value = None
                if value is None:
                    value = output_model.model_validate(_extract_json(resp.text))
                if is_live:
                    self.live_calls += 1
                step.status = "degraded" if failures else "completed"
                step.output = value.model_dump(mode="json")
                step.finished_at = utcnow().isoformat()
                step.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                self.state.updated_at = step.finished_at
                self.state.state_version += 1
                await self._emit("agent_completed", {"step_id": step.step_id, "agent": agent, "status": step.status,
                                                     "model": step.model, "duration_ms": step.duration_ms})
                return value, step
            except Exception as exc:
                failures += 1
                msg = f"{label} failed: {type(exc).__name__}: {str(exc)[:240]}"
                step.notes.append(msg)
                log.warning("[%s] %s %s", self.state.correlation_id, agent, msg)
                if kind in ("fault", "live"):
                    self.state.degraded = True
                    self.policy_fallbacks += 1
                    step.notes.append("Falling back to the deterministic policy planner; no live model output is used "
                                      "for this step.")
                continue
        step.status = "failed"
        step.error = "; ".join(step.notes)[-500:]
        step.finished_at = utcnow().isoformat()
        step.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        await self._emit("agent_completed", {"step_id": step.step_id, "agent": agent, "status": "failed"})
        raise AgentFailure(step.error)

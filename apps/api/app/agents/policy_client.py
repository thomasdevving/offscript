"""Deterministic policy chat client for Microsoft Agent Framework.

When no Microsoft Foundry deployment is configured (local development, CI, or a provider
outage) every agent still runs through the *same* Agent Framework `Agent`, tool-invocation
loop, middleware and structured-output parsing - but the "model" is a transparent,
rule-based planner written in Python. It requests real tool calls and produces structured
JSON exactly like an LLM would. Its output is always labelled `policy` (never presented as
a live model result).
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from agent_framework.observability import ChatTelemetryLayer


@dataclass
class PolicyTurn:
    prompt: str
    results: dict[str, list[Any]]
    call_order: list[str]
    tool_names: list[str]


@dataclass
class PolicyDecision:
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    final: dict[str, Any] | None = None


PolicyFn = Callable[[PolicyTurn], PolicyDecision]


def _parse(result: Any) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (ValueError, TypeError):
            return result
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        txt = "".join(getattr(c, "text", "") or "" for c in result)
        return _parse(txt)
    return result


class _PolicyBase(BaseChatClient):
    OTEL_PROVIDER_NAME = "parallel.policy"

    def __init__(self, policy: PolicyFn, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy = policy

    def _inner_get_response(self, *, messages, stream, options, **kwargs):  # type: ignore[override]
        if stream:
            raise NotImplementedError("The policy client is used without streaming")
        return self._respond(messages, options)

    async def _respond(self, messages, options) -> ChatResponse:
        names: dict[str, str] = {}
        results: dict[str, list[Any]] = defaultdict(list)
        order: list[str] = []
        prompt = ""
        for m in messages:
            if m.role == "user" and m.text:
                prompt = m.text
            for c in m.contents:
                if c.type == "function_call":
                    names[c.call_id] = c.name
                elif c.type == "function_result":
                    name = names.get(c.call_id, "unknown")
                    results[name].append(_parse(c.result))
                    order.append(name)
        tools = [getattr(t, "name", str(t)) for t in (options.get("tools") or [])]
        decision = self.policy(PolicyTurn(prompt=prompt, results=dict(results), call_order=order, tool_names=tools))
        if decision.tool_calls:
            contents = [
                Content.from_function_call(f"call_{uuid.uuid4().hex[:10]}", name, arguments=args)
                for name, args in decision.tool_calls
            ]
            return ChatResponse(messages=[Message(role="assistant", contents=contents)])
        return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(decision.final or {})])])


class PolicyChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, _PolicyBase):
    """Policy client with the standard Agent Framework layers (function invocation, middleware, telemetry)."""


class ProviderOutageError(RuntimeError):
    pass


class _FailingBase(BaseChatClient):
    """Simulates a Foundry outage for the controlled 'model unavailable' fault-injection scenario."""

    OTEL_PROVIDER_NAME = "parallel.fault"

    def _inner_get_response(self, *, messages, stream, options, **kwargs):  # type: ignore[override]
        async def _fail() -> ChatResponse:
            raise ProviderOutageError("Simulated model provider outage (controlled fault injection)")
        return _fail()


class FailingChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, _FailingBase):
    pass

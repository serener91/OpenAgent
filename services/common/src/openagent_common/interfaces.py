"""Protocol definitions for OpenAgent dependencies.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §5
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from .schemas import AgentEvent, GuardrailDecision, Result, Task


@runtime_checkable
class BaseAgent(Protocol):
    """The universal agent interface. Every production and testbed agent
    implementation satisfies this Protocol."""

    name: str

    async def run(self, task: Task) -> Result:
        ...

    # Declared plain `def` (not `async def`) so an async-generator body —
    # `async def run_streamed(...): ... yield ...` — satisfies the Protocol.
    # Called without `await`; iterated with `async for`. Matches umbrella §5.1
    # and the concrete forms in agent-core-{sdk,manual}.md.
    def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]:
        ...


@runtime_checkable
class Guardrail(Protocol):
    """A pluggable check that runs at one of the orchestrator/agent/gateway
    lifecycle points. See 2026-04-23-guardrails.md for scope."""

    name: str
    kind: str  # "input" | "tool" | "output"

    async def check(self, payload: dict) -> GuardrailDecision:
        ...


@runtime_checkable
class LLMClient(Protocol):
    """OpenAI-compatible chat completion client (points at vLLM in prod)."""

    model_name: str

    async def chat_completion(
        self, messages: list[dict], **kwargs: Any
    ) -> dict:
        ...


@runtime_checkable
class MCPClient(Protocol):
    """Client for the central MCP Gateway."""

    async def call_tool(self, name: str, arguments: dict) -> dict:
        ...

    async def list_tools(self) -> list[dict]:
        ...


@runtime_checkable
class SessionStore(Protocol):
    """Redis-backed session persistence interface."""

    async def load(self, session_id: str) -> dict | None:
        ...

    async def save(
        self, session_id: str, data: dict, ttl_seconds: int = 86400
    ) -> None:
        ...

    async def delete(self, session_id: str) -> None:
        ...

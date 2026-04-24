"""Tests for openagent_common.interfaces Protocols.

Protocols can't be "unit tested" directly. Instead we verify each Protocol
can be satisfied by a minimal fake at runtime via @runtime_checkable.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from openagent_common.interfaces import (
    BaseAgent,
    Guardrail,
    LLMClient,
    MCPClient,
    SessionStore,
)
from openagent_common.schemas import (
    AgentEvent,
    GuardrailDecision,
    Result,
    Task,
)


class FakeAgent:
    name = "fake"

    async def run(self, task: Task) -> Result:
        return Result(task_id=task.task_id, status="completed", content="ok")

    async def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(kind="done")


class FakeGuardrail:
    name = "fake_input"
    kind = "input"

    async def check(self, payload: dict) -> GuardrailDecision:
        return GuardrailDecision(verdict="allowed", name=self.name)


class FakeLLMClient:
    model_name = "fake-model"

    async def chat_completion(
        self, messages: list[dict], **kwargs: object
    ) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}


class FakeMCPClient:
    async def call_tool(self, name: str, arguments: dict) -> dict:
        return {"ok": True}

    async def list_tools(self) -> list[dict]:
        return []


class FakeSessionStore:
    async def load(self, session_id: str) -> dict | None:
        return None

    async def save(
        self, session_id: str, data: dict, ttl_seconds: int = 86400
    ) -> None:
        return None

    async def delete(self, session_id: str) -> None:
        return None


def test_fake_agent_conforms_to_baseagent() -> None:
    assert isinstance(FakeAgent(), BaseAgent)


def test_fake_guardrail_conforms_to_guardrail() -> None:
    assert isinstance(FakeGuardrail(), Guardrail)


def test_fake_llm_client_conforms() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)


def test_fake_mcp_client_conforms() -> None:
    assert isinstance(FakeMCPClient(), MCPClient)


def test_fake_session_store_conforms() -> None:
    assert isinstance(FakeSessionStore(), SessionStore)


@pytest.mark.asyncio
async def test_fake_agent_run_returns_result() -> None:
    agent = FakeAgent()
    task = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
    result = await agent.run(task)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_fake_agent_run_streamed_yields_events() -> None:
    agent = FakeAgent()
    task = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
    # run_streamed is called without `await` — it returns an async iterator
    # directly (either from an async-generator body like FakeAgent's, or from
    # a plain `def` that constructs one). The Protocol is typed accordingly.
    stream = agent.run_streamed(task)
    assert hasattr(stream, "__aiter__"), "run_streamed must return an async iterator, not a coroutine"
    events = [e async for e in stream]
    assert len(events) == 1
    assert events[0].kind == "done"

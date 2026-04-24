"""Core Pydantic models shared across OpenAgent services.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §5.1
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentEventKind = Literal[
    "thinking",
    "tool_call",
    "tool_result",
    "partial_content",
    "dispatched",
    "done",
    "error",
]

ResultStatus = Literal["completed", "failed"]

GuardrailVerdict = Literal["allowed", "flagged", "blocked"]


class Task(BaseModel):
    """A unit of work dispatched to an agent."""

    task_id: str
    session_id: str
    user_id: str
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A single tool invocation within an agent run."""

    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentEvent(BaseModel):
    """One event emitted by an agent during streaming execution."""

    kind: AgentEventKind
    data: dict[str, Any] = Field(default_factory=dict)


class Result(BaseModel):
    """The terminal output of an agent run."""

    task_id: str
    status: ResultStatus
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error: str | None = None
    tokens: dict[str, int] = Field(default_factory=dict)


class GuardrailDecision(BaseModel):
    """Decision emitted by a Guardrail.check() call."""

    verdict: GuardrailVerdict
    reason: str = ""
    name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

"""Tests for openagent_common.schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from openagent_common.schemas import (
    AgentEvent,
    GuardrailDecision,
    Result,
    Task,
    ToolCall,
)


class TestTask:
    def test_minimal_fields(self) -> None:
        t = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
        assert t.task_id == "t1"
        assert t.session_id == "s1"
        assert t.user_id == "u1"
        assert t.prompt == "hi"
        assert t.context == {}
        assert t.metadata == {}

    def test_round_trip(self) -> None:
        t = Task(
            task_id="t1",
            session_id="s1",
            user_id="u1",
            prompt="hi",
            context={"history": [1, 2, 3]},
            metadata={"priority": "high"},
        )
        restored = Task.model_validate(t.model_dump())
        assert restored == t

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            Task(session_id="s1", user_id="u1", prompt="hi")  # type: ignore[call-arg]


class TestToolCall:
    def test_result_and_error_nullable(self) -> None:
        tc = ToolCall(name="read_file", arguments={"path": "/tmp/a"})
        assert tc.result is None
        assert tc.error is None

    def test_with_result(self) -> None:
        tc = ToolCall(
            name="read_file",
            arguments={"path": "/tmp/a"},
            result={"bytes": 42},
        )
        assert tc.result == {"bytes": 42}


class TestAgentEvent:
    @pytest.mark.parametrize(
        "kind",
        [
            "thinking",
            "tool_call",
            "tool_result",
            "partial_content",
            "dispatched",
            "done",
            "error",
        ],
    )
    def test_accepts_known_kinds(self, kind: str) -> None:
        e = AgentEvent(kind=kind)
        assert e.kind == kind
        assert e.data == {}

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            AgentEvent(kind="totally_made_up")  # type: ignore[arg-type]


class TestResult:
    def test_completed_result(self) -> None:
        r = Result(task_id="t1", status="completed", content="final answer")
        assert r.status == "completed"
        assert r.tool_calls == []
        assert r.tokens == {}
        assert r.error is None

    def test_failed_result_with_error(self) -> None:
        r = Result(task_id="t1", status="failed", error="boom")
        assert r.status == "failed"
        assert r.content is None

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            Result(task_id="t1", status="maybe")  # type: ignore[arg-type]


class TestGuardrailDecision:
    @pytest.mark.parametrize("verdict", ["allowed", "flagged", "blocked"])
    def test_accepts_known_verdicts(self, verdict: str) -> None:
        d = GuardrailDecision(verdict=verdict)
        assert d.verdict == verdict

    def test_rejects_unknown_verdict(self) -> None:
        with pytest.raises(ValidationError):
            GuardrailDecision(verdict="yes")  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        d = GuardrailDecision(verdict="allowed")
        assert d.reason == ""
        assert d.name == ""
        assert d.metadata == {}

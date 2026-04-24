"""Tests for openagent_common.logging."""

from __future__ import annotations

import json

import pytest
import structlog
from opentelemetry import trace

from openagent_common.logging import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    """Ensure each test starts from a clean structlog config."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def test_json_output_has_core_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", user_id="u1")

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["event"] == "hello"
    assert record["user_id"] == "u1"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_contextvars_bind_persists(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(session_id="sess_1", user_id="u1")
    log = structlog.get_logger("test")
    log.info("hi")

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert record["session_id"] == "sess_1"
    assert record["user_id"] == "u1"
    structlog.contextvars.clear_contextvars()


def test_trace_id_injected_when_inside_span(
    capsys: pytest.CaptureFixture[str],
    otel_exporter,
) -> None:
    configure_logging(level="INFO")
    tracer = trace.get_tracer("test")
    log = structlog.get_logger("test")

    with tracer.start_as_current_span("outer"):
        log.info("in-span")

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert "trace_id" in record
    assert "span_id" in record
    assert len(record["trace_id"]) == 32
    assert len(record["span_id"]) == 16


def test_trace_id_absent_outside_span(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No otel fixture — no active span.
    configure_logging(level="INFO")
    log = structlog.get_logger("test")
    log.info("no-span")
    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert "trace_id" not in record

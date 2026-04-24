"""structlog configuration with OTEL trace-id correlation.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §11.4

Usage (at service startup, AFTER configure_tracing):

    from openagent_common.logging import configure_logging
    configure_logging(level="INFO")
    log = structlog.get_logger("orchestrator")
    log.info("service_started")

Bind contextvars at per-request scope:

    structlog.contextvars.bind_contextvars(session_id=..., user_id=...)
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from opentelemetry import trace


def _add_otel_context(
    logger: object, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor that copies the active OTEL span's IDs into the
    event dict. If no span is active, adds nothing."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    # INVALID_SPAN has trace_id=0 / span_id=0
    if ctx.trace_id != 0:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Install a JSON-emitting structlog config that correlates log records
    to the active OTEL span.

    Safe to call more than once (structlog caches on first use; later calls
    still apply to newly-created loggers)."""
    level_int = getattr(logging, level.upper(), logging.INFO)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_otel_context,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

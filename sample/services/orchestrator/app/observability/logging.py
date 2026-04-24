"""Structured logging setup with trace ID injection."""

import structlog
from opentelemetry import trace


def setup_logging() -> None:
    """Configure structured logging with trace ID injection."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            level=20,  # INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
        processors=[
            structlog.contextvars.merge_contextvars,
            inject_trace_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


def inject_trace_id(logger, method_name, event_dict):
    """Inject trace ID from current span into log context."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        event_dict["trace_id"] = format(span.get_span_context().trace_id, "032x")
        event_dict["span_id"] = format(span.get_span_context().span_id, "016x")
    return event_dict


def get_logger(name: str):
    """Get a structured logger instance."""
    return structlog.get_logger(name)
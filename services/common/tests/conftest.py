"""Shared test fixtures for openagent-common."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
    """Fresh in-memory OTEL exporter bound to a fresh TracerProvider.

    Resets the global tracer provider for the test, so tests that assert
    on emitted spans are isolated.
    """
    exporter = InMemorySpanExporter()
    resource = Resource.create(
        {"service.name": "test", "service.namespace": "openagent"}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter

"""Tests for openagent_common.telemetry."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from openagent_common.telemetry import build_tracer_provider, configure_tracing


def test_build_tracer_provider_sets_resource_attributes() -> None:
    provider = build_tracer_provider("orchestrator")
    assert isinstance(provider, TracerProvider)
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "orchestrator"
    assert attrs["service.namespace"] == "openagent"


def test_build_tracer_provider_honors_custom_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAMESPACE", "openagent-test")
    provider = build_tracer_provider("file_agent")
    assert provider.resource.attributes["service.namespace"] == "openagent-test"


def test_configure_tracing_installs_global_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point at localhost; exporter is lazy, doesn't try to connect at init.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    monkeypatch.setattr(trace, "_TRACER_PROVIDER_SET_ONCE", trace.Once())
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None)
    tracer = configure_tracing("mcp_gateway")
    assert tracer is not None
    provider = trace.get_tracer_provider()
    # The installed provider should carry our service.name
    assert provider.resource.attributes["service.name"] == "mcp_gateway"  # type: ignore[attr-defined]
    # Stop the BatchSpanProcessor's background thread so it doesn't keep
    # retrying to export to localhost:4317 after the test returns.
    provider.shutdown()  # type: ignore[attr-defined]


def test_span_emission_with_in_memory_exporter(otel_exporter) -> None:
    # otel_exporter fixture already installs a provider with service.name=test
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("my-span") as span:
        span.set_attribute("foo", "bar")

    spans = otel_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "my-span"
    assert spans[0].attributes["foo"] == "bar"
    assert spans[0].resource.attributes["service.name"] == "test"

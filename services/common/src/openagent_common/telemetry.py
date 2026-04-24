"""OTEL bootstrap for OpenAgent services.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §11

Usage (at service startup):

    from openagent_common.telemetry import configure_tracing
    tracer = configure_tracing("orchestrator")

The exporter is OTLP/gRPC pointed at the endpoint in
OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4317). Jaeger's
all-in-one image accepts OTLP on that port when COLLECTOR_OTLP_ENABLED=true.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

_DEFAULT_ENDPOINT = "http://localhost:4317"


def build_tracer_provider(
    service_name: str,
    *,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Construct (but do NOT install) a TracerProvider for `service_name`.

    Separated from `configure_tracing` so tests can inspect / inject an
    exporter without mutating the global tracer provider.
    """
    namespace = os.environ.get("OTEL_SERVICE_NAMESPACE", "openagent")
    resource = Resource.create(
        {"service.name": service_name, "service.namespace": namespace}
    )
    provider = TracerProvider(resource=resource)
    if exporter is None:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT
        )
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def configure_tracing(service_name: str) -> trace.Tracer:
    """Install a global TracerProvider for `service_name` and return a
    tracer named after the service. Call once at service startup."""
    provider = build_tracer_provider(service_name)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

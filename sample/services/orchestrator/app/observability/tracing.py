"""OpenTelemetry tracing setup."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings


def setup_tracing() -> None:
    """Configure OpenTelemetry tracing with OTLP exporter."""
    resource = Resource.create(
        {
            "service.name": settings.otel.service_name,
            "service.version": "0.1.0",
        }
    )

    provider = TracerProvider(resource=resource)

    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otel.exporter_otlp_endpoint,
        insecure=settings.otel.exporter_otlp_insecure,
    )

    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)


def instrument_fastapi(app) -> None:
    """Instrument FastAPI application."""
    FastAPIInstrumentor.instrument_app(app)
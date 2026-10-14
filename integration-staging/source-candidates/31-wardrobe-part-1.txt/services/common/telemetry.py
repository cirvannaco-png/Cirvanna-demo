"""OpenTelemetry instrumentation setup for all services."""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import settings

logger = logging.getLogger(__name__)


def setup_telemetry(app=None, service_name: str = "cirvanna") -> None:
    """Configure OTLP tracing and auto-instrument FastAPI, SQLAlchemy, Redis, HTTPX."""
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": settings.service_namespace,
            "deployment.environment": settings.environment,
            "service.version": "3.0.0",
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otlp_endpoint,
        insecure=settings.otlp_insecure,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrumentation
    try:
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        if app is not None:
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="health,metrics,ready",
            )
        logger.info(f"OpenTelemetry configured for {service_name}")
    except Exception as exc:
        logger.warning(f"Telemetry instrumentation partial: {exc}")


def get_tracer(name: str):
    return trace.get_tracer(name)

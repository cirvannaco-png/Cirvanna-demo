"""
Distributed tracing with OpenTelemetry.
"""
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from ...config import TariConfig

def init_tracing(config: TariConfig):
    if not config.ENABLE_DISTRIBUTED_TRACING:
        return
    provider = TracerProvider()
    exporter = JaegerExporter(
        agent_host_name="localhost",
        agent_port=6831,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("xyra.orchestrator")

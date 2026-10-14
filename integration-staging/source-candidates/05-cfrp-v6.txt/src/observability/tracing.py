"""
DistributedTracer – Jaeger tracing.
"""
import opentracing
from jaeger_client import Config

class DistributedTracer:
    def __init__(self, service_name: str):
        config = Config(
            config={
                'sampler': {'type': 'probabilistic', 'param': 0.1},
                'logging': True,
                'local_agent': {'reporting_host': 'jaeger-agent', 'reporting_port': 6831}
            },
            service_name=service_name,
            validate=True
        )
        self.tracer = config.initialize_tracer()

    def start_span(self, operation_name: str, context=None, business_context=None):
        if context:
            span_ctx = self.tracer.extract(opentracing.Format.TEXT_MAP, context)
            span = self.tracer.start_span(operation_name, child_of=span_ctx)
        else:
            span = self.tracer.start_span(operation_name)
        if business_context:
            for k, v in business_context.items():
                span.set_tag(f"business.{k}", v)
        span.set_tag("component", "cfrp")
        span.set_tag("version", "10.0")
        return span

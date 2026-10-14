from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable

# Define metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

active_requests = Gauge(
    'http_requests_active',
    'Active HTTP requests',
    ['service']
)

inference_duration = Histogram(
    'model_inference_duration_seconds',
    'Model inference duration',
    ['model_name', 'service'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)

inference_count = Counter(
    'model_inference_total',
    'Total model inferences',
    ['model_name', 'service', 'status']
)

cache_hits = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['service', 'cache_type']
)

cache_misses = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['service', 'cache_type']
)

error_count = Counter(
    'errors_total',
    'Total errors',
    ['service', 'error_type']
)

confidence_distribution = Histogram(
    'confidence_tier_distribution',
    'Distribution of confidence tiers',
    ['service'],
    buckets=[0.5, 0.7, 0.8, 0.9, 0.95, 0.99]
)

def monitor_request(service_name: str):
    """Decorator to monitor FastAPI endpoints"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get('request')
            method = request.method if request else "unknown"
            endpoint = request.url.path if request else "unknown"
            
            active_requests.labels(service=service_name).inc()
            
            start_time = time.time()
            try:
                response = await func(*args, **kwargs)
                status = response.status_code if hasattr(response, 'status_code') else 200
                return response
            except Exception as e:
                error_count.labels(
                    service=service_name,
                    error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                request_duration.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(duration)
                request_count.labels(
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).inc()
                active_requests.labels(service=service_name).dec()
        
        return wrapper
    return decorator

"""Cirvanna common library.

Shared modules used by all microservices:
- config: environment-driven settings
- domain: core domain models and business logic
- cache: async Redis wrapper
- events: RabbitMQ pub/sub
- telemetry: OpenTelemetry instrumentation
- security: JWT auth, rate limiting primitives
- logging: structured JSON logging
- errors: exception hierarchy
- retry: exponential backoff utilities
"""

__version__ = "3.0.0"

from .config import settings
from .errors import (
    CirvannaError,
    NotFoundError,
    ValidationError,
    ConflictError,
    UpstreamError,
)

__all__ = [
    "settings",
    "CirvannaError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "UpstreamError",
]

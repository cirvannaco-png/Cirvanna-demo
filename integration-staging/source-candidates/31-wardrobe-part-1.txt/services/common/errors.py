"""Exception hierarchy shared across all Cirvanna services."""

from __future__ import annotations

from typing import Any


class CirvannaError(Exception):
    """Base exception for all domain errors."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class NotFoundError(CirvannaError):
    status_code = 404
    error_code = "not_found"


class ValidationError(CirvannaError):
    status_code = 422
    error_code = "validation_error"


class ConflictError(CirvannaError):
    status_code = 409
    error_code = "conflict"


class UpstreamError(CirvannaError):
    status_code = 502
    error_code = "upstream_error"


class ServiceUnavailableError(CirvannaError):
    status_code = 503
    error_code = "service_unavailable"


class RateLimitError(CirvannaError):
    status_code = 429
    error_code = "rate_limit_exceeded"


class CircuitOpenError(CirvannaError):
    status_code = 503
    error_code = "circuit_open"


class AuthenticationError(CirvannaError):
    status_code = 401
    error_code = "authentication_error"


class AuthorizationError(CirvannaError):
    status_code = 403
    error_code = "authorization_error"

"""Shared validation for authenticated internal service clients."""
from __future__ import annotations
from urllib.parse import urlsplit


def validate_internal_service_credentials(
    base_url: str,
    token: str,
    *,
    service_name: str,
    token_name: str,
) -> str:
    """Validate internal URL/token settings and return a normalized base URL."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError(f"{service_name} base URL is required")
    value = base_url.strip().rstrip("/")
    parts = urlsplit(value)
    try:
        _port = parts.port
    except ValueError as exc:
        raise ValueError(f"{service_name} URL contains an invalid port") from exc
    host = (parts.hostname or "").lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or not (parts.scheme == "https" or (parts.scheme == "http" and loopback))
    ):
        raise ValueError(
            f"{service_name} URL must use HTTPS; HTTP is allowed only for loopback development"
        )
    if not isinstance(token, str) or len(token.encode("utf-8")) < 32:
        raise ValueError(f"{token_name} must contain at least 32 bytes")
    return value

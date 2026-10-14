"""JWT authentication, rate limiting primitives, correlation middleware."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings
from .logging_config import set_correlation_id, user_id_var

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def issue_token(user_id: str, *, expires_hours: int | None = None) -> str:
    """Create a signed JWT for a user."""
    hours = expires_hours or settings.jwt_expiry_hours
    payload = {
        "sub": user_id,
        "iat": dt.datetime.now(dt.timezone.utc),
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours),
        "iss": "cirvanna",
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer="cirvanna",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError as exc:
        logger.warning(f"JWT decode failed: {exc}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


async def current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> str:
    """FastAPI dependency returning the authenticated user_id."""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    user_id_var.set(user_id)
    return user_id


# Rate limiter (per-IP default; per-endpoint logic lives in the gateway)
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    default_limits=["1000/hour"],
)


async def correlation_middleware(request: Request, call_next):
    """Attach a correlation ID to every request and echo it back."""
    cid = request.headers.get("X-Correlation-ID") or set_correlation_id()
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response

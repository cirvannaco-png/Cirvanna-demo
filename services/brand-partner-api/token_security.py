"""Brand token primitives; persistence and account-status checks belong to the caller.

No login/refresh route is exposed here: issuing tokens without an authoritative
account repository and revocation store would create a false security boundary.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=8)


def _secret() -> str:
    value = os.getenv("BRAND_JWT_SECRET", "")
    if len(value) < 32 or value == "REPLACE_WITH_ENV_VAR":
        raise RuntimeError("BRAND_JWT_SECRET must be configured with at least 32 characters")
    return value


class BrandPrincipal(BaseModel):
    brand_id: str = Field(min_length=1)
    brand_name: str
    email: str
    permissions: list[str] = Field(default_factory=list)
    role: str = "brand_partner"


def create_access_token(principal: BrandPrincipal, *, ttl: timedelta = ACCESS_TOKEN_TTL) -> str:
    """Call only after DB-backed credential and account-status verification."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": principal.brand_id,
        "brand_id": principal.brand_id,
        "brand_name": principal.brand_name,
        "email": principal.email,
        "permissions": principal.permissions,
        "role": "brand_partner",
        "token_type": "access",
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> BrandPrincipal:
    """Cryptographically verify an access token; caller must re-check live account state."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid brand credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, _secret(), algorithms=[JWT_ALGORITHM],
            options={"require_sub": True, "require_exp": True},
        )
        if payload.get("token_type") != "access" or payload.get("role") != "brand_partner":
            raise unauthorized
        brand_id = payload.get("sub")
        if not isinstance(brand_id, str) or not brand_id or payload.get("brand_id") != brand_id:
            raise unauthorized
        permissions = payload.get("permissions", [])
        if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
            raise unauthorized
        return BrandPrincipal(
            brand_id=brand_id, brand_name=str(payload.get("brand_name", "")),
            email=str(payload.get("email", "")), permissions=permissions,
            role="brand_partner",
        )
    except (JWTError, ValueError, TypeError):
        raise unauthorized from None


def require_permission(principal: BrandPrincipal, permission: str) -> None:
    """Use only with permissions freshly loaded from authoritative account storage."""
    if permission not in principal.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient brand permissions")

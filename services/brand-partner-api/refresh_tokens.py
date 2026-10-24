"""Opaque-by-storage refresh sessions using signed JWTs and server-side token hashes."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt

try:
    from .account_service import BrandAccountError
    from .repository_contract import BrandAccountStatus, BrandAccountRepository, RefreshTokenRepository
    from .token_security import BrandPrincipal, JWT_ALGORITHM, _secret, create_access_token
except ImportError:
    from account_service import BrandAccountError
    from repository_contract import BrandAccountStatus, BrandAccountRepository, RefreshTokenRepository
    from token_security import BrandPrincipal, JWT_ALGORITHM, _secret, create_access_token

REFRESH_TOKEN_TTL = timedelta(days=30)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode_refresh_token(*, brand_id: str, token_id: str, ttl: timedelta) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + ttl
    payload = {
        "sub": brand_id, "jti": token_id, "token_type": "refresh",
        "iat": now, "exp": expires_at,
    }
    token = jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)
    return token, expires_at


async def issue_refresh_token(
    repository: RefreshTokenRepository, principal: BrandPrincipal, *, ttl: timedelta = REFRESH_TOKEN_TTL
) -> str:
    """Persist a hash before returning a refresh token to the caller."""
    if ttl <= timedelta(0) or ttl > timedelta(days=90):
        raise ValueError("Refresh token lifetime must be between 0 and 90 days")
    token_id = str(uuid4())
    token, expires_at = _encode_refresh_token(brand_id=principal.brand_id, token_id=token_id, ttl=ttl)
    await repository.create_refresh_session(
        token_id=token_id, brand_id=principal.brand_id,
        token_hash=_hash_token(token), expires_at=expires_at,
    )
    return token


async def rotate_refresh_token(
    refresh_repository: RefreshTokenRepository,
    account_repository: BrandAccountRepository,
    presented_token: str,
) -> tuple[str, str]:
    """Atomically rotate a refresh token, then issue access using current permissions."""
    # Validate configuration before consuming a one-time token.
    _secret()
    try:
        claims = jwt.decode(
            presented_token, _secret(), algorithms=[JWT_ALGORITHM],
            options={"require_sub": True, "require_exp": True, "require_jti": True},
        )
        if claims.get("token_type") != "refresh":
            raise BrandAccountError("Invalid refresh token")
        brand_id, token_id = claims.get("sub"), claims.get("jti")
        if not isinstance(brand_id, str) or not isinstance(token_id, str):
            raise BrandAccountError("Invalid refresh token")
    except (JWTError, ValueError, TypeError):
        raise BrandAccountError("Invalid refresh token") from None

    account = await account_repository.get_by_id(brand_id)
    if account is None or account.status is not BrandAccountStatus.ACTIVE:
        raise BrandAccountError("Invalid refresh token")

    replacement_id = str(uuid4())
    replacement_token, replacement_expiry = _encode_refresh_token(
        brand_id=brand_id, token_id=replacement_id, ttl=REFRESH_TOKEN_TTL,
    )
    rotated = await refresh_repository.consume_and_rotate(
        token_id=token_id, brand_id=brand_id,
        presented_token_hash=_hash_token(presented_token),
        replacement_token_id=replacement_id,
        replacement_token_hash=_hash_token(replacement_token),
        expires_at=replacement_expiry,
    )
    if not rotated:
        raise BrandAccountError("Invalid refresh token")

    # Reload to ensure the access token reflects current status and permissions.
    account = await account_repository.get_by_id(brand_id)
    if account is None or account.status is not BrandAccountStatus.ACTIVE:
        raise BrandAccountError("Brand account is not active")
    principal = BrandPrincipal(
        brand_id=account.brand_id, brand_name=account.brand_name,
        email=account.email_normalized, permissions=list(account.permissions),
        role="brand_partner",
    )
    return create_access_token(principal), replacement_token

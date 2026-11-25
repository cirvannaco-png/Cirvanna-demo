"""Server-side Supabase Auth lifecycle for the Marketplace BFF.

Browser credentials never leave the HttpOnly session cookie. Supabase access and
refresh tokens are encrypted at rest in auth_private.sessions; PKCE verifiers
are encrypted in auth_private.pending_auth and are single-use.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import asyncpg
import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["authentication"])
COOKIE_NAME = "__Host-cirvanna_session"
OAUTH_STATE_COOKIE = "__Host-cirvanna_oauth_state"
PROVIDERS = {"google": "google", "apple": "apple", "microsoft": "azure", "email": "email"}
ALLOWED_APP_ROLES = {"customer", "merchant", "admin"}
_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()
_jwks_client: jwt.PyJWKClient | None = None


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(503, detail={"code": f"{name}_NOT_CONFIGURED"})
    return value


def _supabase() -> tuple[str, str]:
    base = _required("SUPABASE_URL").rstrip("/")
    key = _required("SUPABASE_PUBLISHABLE_KEY")
    parts = urlsplit(base)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}:
        raise HTTPException(503, detail={"code": "SUPABASE_URL_INVALID"})
    return base, key


def _fernet() -> Fernet:
    raw = _required("AUTH_SESSION_ENCRYPTION_KEY").encode()
    try:
        return Fernet(raw)
    except Exception as exc:
        raise HTTPException(503, detail={"code": "AUTH_SESSION_ENCRYPTION_KEY_INVALID"}) from exc


async def _db() -> asyncpg.Pool:
    global _pool
    dsn = _required("AUTH_SESSION_DATABASE_URL")
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, command_timeout=5, ssl="require")
    return _pool


async def close_auth_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def _decrypt(value: bytes) -> str:
    try:
        return _fernet().decrypt(value).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise HTTPException(503, detail={"code": "AUTH_SESSION_DECRYPTION_FAILED"}) from exc


def _callback_url() -> str:
    callback = _required("AUTH_CALLBACK_URL")
    parts = urlsplit(callback)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path != "/auth/callback"
    ):
        raise HTTPException(503, detail={"code": "AUTH_CALLBACK_URL_INVALID"})
    return callback


def _session_ttl() -> int:
    try:
        ttl = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "2592000"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, detail={"code": "AUTH_SESSION_TTL_INVALID"}) from exc
    if ttl < 3600 or ttl > 7776000:
        raise HTTPException(503, detail={"code": "AUTH_SESSION_TTL_INVALID"})
    return ttl


def _post_login_redirect() -> str:
    target = os.getenv("AUTH_POST_LOGIN_REDIRECT", "/")
    if not target.startswith("/") or target.startswith("//") or chr(92) in target:
        raise HTTPException(503, detail={"code": "AUTH_POST_LOGIN_REDIRECT_INVALID"})
    return target


def _cookie(response: Response, session_id: str, *, max_age: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


async def _create_pending(provider: str, verifier: str, state: str) -> None:
    pool = await _db()
    await pool.execute("DELETE FROM auth_private.pending_auth WHERE expires_at <= now()")
    await pool.execute(
        """DELETE FROM auth_private.sessions
           WHERE expires_at <= now() OR revoked_at < now() - interval '30 days'"""
    )
    await pool.execute(
        """INSERT INTO auth_private.pending_auth(state_hash, provider, verifier_ciphertext, expires_at)
           VALUES($1, $2, $3, now() + interval '10 minutes')""",
        _hash(state), provider, _encrypt(verifier),
    )


async def _pending_provider(state: str) -> str:
    """Read the flow type without consuming state, so browser binding is checked first."""
    pool = await _db()
    provider = await pool.fetchval(
        "SELECT provider FROM auth_private.pending_auth WHERE state_hash=$1 AND expires_at > now()",
        _hash(state),
    )
    if provider is None:
        raise HTTPException(400, detail={"code": "AUTH_STATE_INVALID_OR_EXPIRED"})
    return str(provider)


async def _consume_pending(state: str) -> tuple[str, str]:
    pool = await _db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """DELETE FROM auth_private.pending_auth
                   WHERE state_hash=$1 AND expires_at > now()
                   RETURNING provider, verifier_ciphertext""",
                _hash(state),
            )
    if row is None:
        raise HTTPException(400, detail={"code": "AUTH_STATE_INVALID_OR_EXPIRED"})
    return row["provider"], _decrypt(row["verifier_ciphertext"])


async def _exchange_code(code: str, verifier: str) -> dict[str, Any]:
    base, key = _supabase()
    async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=False) as client:
        response = await client.post(
            base + "/auth/v1/token?grant_type=pkce",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"auth_code": code, "code_verifier": verifier},
        )
    if response.status_code != 200:
        raise HTTPException(401, detail={"code": "AUTH_CODE_EXCHANGE_FAILED"})
    data = response.json()
    if not isinstance(data, dict) or not data.get("access_token") or not data.get("refresh_token"):
        raise HTTPException(502, detail={"code": "AUTH_TOKEN_RESPONSE_INVALID"})
    return data


def _verify_jwt(token: str) -> dict[str, Any]:
    global _jwks_client
    jwks_url = _required("SUPABASE_JWKS_URL")
    issuer = _required("SUPABASE_JWT_ISSUER")
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip()
    supabase_url, _ = _supabase()
    if audience != "authenticated":
        raise HTTPException(503, detail={"code": "SUPABASE_JWT_AUDIENCE_INVALID"})
    if jwks_url != supabase_url + "/auth/v1/.well-known/jwks.json" or issuer != supabase_url + "/auth/v1":
        raise HTTPException(503, detail={"code": "SUPABASE_JWT_TRUST_CONFIG_INVALID"})
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, timeout=5)
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except Exception as exc:
        raise HTTPException(401, detail={"code": "AUTH_ACCESS_TOKEN_INVALID"}) from exc
    role = claims.get("app_role", "customer")
    if not isinstance(role, str) or role not in ALLOWED_APP_ROLES:
        raise HTTPException(403, detail={"code": "AUTH_APP_ROLE_INVALID"})
    return claims


async def _store_session(tokens: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    access = tokens["access_token"]
    claims = await asyncio.to_thread(_verify_jwt, access)
    user_id = claims.get("sub")
    expires_in = tokens.get("expires_in")
    if not isinstance(user_id, str) or not user_id or isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in < 60:
        raise HTTPException(502, detail={"code": "AUTH_TOKEN_CLAIMS_INVALID"})
    session_id = secrets.token_urlsafe(32)
    encrypted = _encrypt(__import__("json").dumps({
        "access_token": access,
        "refresh_token": tokens["refresh_token"],
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + expires_in,
        "user_id": user_id,
        "app_role": claims.get("app_role", "customer"),
    }, separators=(",", ":")))
    pool = await _db()
    session_ttl = _session_ttl()
    await pool.execute(
        """INSERT INTO auth_private.sessions(session_hash, user_id, token_ciphertext, expires_at, updated_at)
           VALUES($1, $2, $3, now() + ($4 * interval '1 second'), now())""",
        _hash(session_id), user_id, encrypted, session_ttl,
    )
    return session_id, session_ttl, {"user_id": user_id, "app_role": claims.get("app_role", "customer")}


async def _load_session(session_id: str) -> tuple[str, dict[str, Any]]:
    pool = await _db()
    row = await pool.fetchrow(
        """SELECT user_id, token_ciphertext, expires_at FROM auth_private.sessions
           WHERE session_hash=$1 AND revoked_at IS NULL AND expires_at > now()""",
        _hash(session_id),
    )
    if row is None:
        raise HTTPException(401, detail={"code": "AUTH_SESSION_INVALID"})
    import json
    try:
        tokens = json.loads(_decrypt(row["token_ciphertext"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, detail={"code": "AUTH_SESSION_INVALID"}) from exc
    return str(row["user_id"]), tokens


async def _rotate(session_id: str) -> tuple[dict[str, Any], int]:
    """Serialize refresh-token rotation per session to prevent concurrent reuse."""
    pool = await _db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT user_id, token_ciphertext FROM auth_private.sessions
                   WHERE session_hash=$1 AND revoked_at IS NULL AND expires_at > now()
                   FOR UPDATE""",
                _hash(session_id),
            )
            if row is None:
                raise HTTPException(401, detail={"code": "AUTH_SESSION_INVALID"})
            import json
            current = json.loads(_decrypt(row["token_ciphertext"]))
            user_id = row["user_id"]
            base, key = _supabase()
            async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=False) as client:
                response = await client.post(
                    base + "/auth/v1/token?grant_type=refresh_token",
                    headers={"apikey": key, "Content-Type": "application/json"},
                    json={"refresh_token": current["refresh_token"]},
                )
            if response.status_code != 200:
                await conn.execute(
                    "UPDATE auth_private.sessions SET revoked_at=now(), updated_at=now() WHERE session_hash=$1",
                    _hash(session_id),
                )
                rejected = True
            else:
                tokens = response.json()
                new_access = tokens.get("access_token") if isinstance(tokens, dict) else None
                new_refresh = tokens.get("refresh_token") if isinstance(tokens, dict) else None
                if not new_access or not new_refresh:
                    raise HTTPException(502, detail={"code": "AUTH_REFRESH_RESPONSE_INVALID"})
                claims = await asyncio.to_thread(_verify_jwt, new_access)
                if claims.get("sub") != str(user_id):
                    await conn.execute(
                        "UPDATE auth_private.sessions SET revoked_at=now(), updated_at=now() WHERE session_hash=$1",
                        _hash(session_id),
                    )
                    raise HTTPException(401, detail={"code": "AUTH_REFRESH_SUBJECT_CHANGED"})
                expires_in = tokens.get("expires_in")
                if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in < 60:
                    raise HTTPException(502, detail={"code": "AUTH_REFRESH_EXPIRY_INVALID"})
                encrypted = _encrypt(json.dumps({
                    "access_token": new_access,
                    "refresh_token": new_refresh,
                    "expires_at": int(datetime.now(timezone.utc).timestamp()) + expires_in,
                    "user_id": str(user_id),
                    "app_role": claims.get("app_role", "customer"),
                }, separators=(",", ":")))
                session_ttl = _session_ttl()
                await conn.execute(
                    """UPDATE auth_private.sessions SET token_ciphertext=$2,
                       expires_at=now()+($3 * interval '1 second'), updated_at=now()
                       WHERE session_hash=$1 AND revoked_at IS NULL""",
                    _hash(session_id), encrypted, session_ttl,
                )
                profile = {"user_id": str(user_id), "app_role": claims.get("app_role", "customer")}
                rejected = False
    if rejected:
        raise HTTPException(401, detail={"code": "AUTH_REFRESH_REJECTED"})
    return profile, session_ttl


async def session_access_token(request: Request) -> str:
    """Resolve the opaque browser cookie to a verified, refreshed Supabase access token."""
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(401, detail={"code": "AUTH_SESSION_REQUIRED"})
    user_id, tokens = await _load_session(session_id)
    now = int(datetime.now(timezone.utc).timestamp())
    if tokens["expires_at"] - now < 90:
        _, max_age = await _rotate(session_id)
        request.state.auth_session_refresh_max_age = max_age
        user_id, tokens = await _load_session(session_id)
    claims = await asyncio.to_thread(_verify_jwt, tokens["access_token"])
    if claims.get("sub") != user_id:
        await _revoke(session_id)
        raise HTTPException(401, detail={"code": "AUTH_SESSION_SUBJECT_MISMATCH"})
    return tokens["access_token"]

async def _revoke(session_id: str) -> None:
    pool = await _db()
    await pool.execute(
        "UPDATE auth_private.sessions SET revoked_at=now(), updated_at=now() WHERE session_hash=$1 AND revoked_at IS NULL",
        _hash(session_id),
    )


@router.get("/auth/login/{provider}")
async def login(provider: str) -> RedirectResponse:
    normalized = provider.casefold()
    if normalized not in {"google", "apple", "microsoft"}:
        raise HTTPException(404, detail={"code": "AUTH_PROVIDER_NOT_SUPPORTED"})
    supabase_url, _ = _supabase()
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    await _create_pending(normalized, verifier, state)
    callback = _callback_url() + "?" + urlencode({"state": state})
    params = {
        "provider": PROVIDERS[normalized],
        "redirect_to": callback,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "s256",
    }
    if normalized == "microsoft":
        params["scopes"] = "email"
    if normalized in {"google", "microsoft"}:
        params["prompt"] = "select_account"
    response = RedirectResponse(supabase_url + "/auth/v1/authorize?" + urlencode(params), status_code=302)
    # Bind the OAuth response to the browser that initiated the flow. This prevents
    # a callback initiated in another browser from planting an attacker-selected account.
    response.set_cookie(
        OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, secure=True,
        samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/auth/callback")
async def callback(request: Request) -> Response:
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not state:
        # Email templates carry the original redirect URL in `next`.
        next_url = request.query_params.get("next", "")
        expected = urlsplit(_callback_url())
        supplied = urlsplit(next_url)
        if (
            not next_url
            or supplied.scheme != expected.scheme
            or supplied.netloc != expected.netloc
            or supplied.path != expected.path
            or supplied.username is not None
            or supplied.password is not None
            or supplied.fragment
        ):
            raise HTTPException(400, detail={"code": "AUTH_CALLBACK_STATE_MISSING"})
        state = parse_qs(supplied.query).get("state", [""])[0]
    if not state:
        raise HTTPException(400, detail={"code": "AUTH_CALLBACK_STATE_MISSING"})
    # Read the server-side flow type first, but do not consume the one-time
    # state until the initiating browser has proved possession of its state cookie.
    # Otherwise a callback from a different browser could burn a valid state and
    # deny the legitimate user their login.
    provider_hint = await _pending_provider(state)
    if provider_hint != "email" and not hmac.compare_digest(
        request.cookies.get(OAUTH_STATE_COOKIE, ""), state
    ):
        raise HTTPException(400, detail={"code": "AUTH_BROWSER_STATE_MISMATCH"})
    provider, verifier = await _consume_pending(state)
    if provider != provider_hint:
        raise HTTPException(400, detail={"code": "AUTH_STATE_INVALID_OR_EXPIRED"})
    if provider == "email":
        token_hash = request.query_params.get("token_hash", "")
        if request.query_params.get("type") != "email" or not token_hash:
            raise HTTPException(400, detail={"code": "AUTH_EMAIL_TOKEN_MISSING"})
        base, key = _supabase()
        async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=False) as client:
            verified = await client.post(
                base + "/auth/v1/verify",
                headers={"apikey": key, "Content-Type": "application/json"},
                json={"token_hash": token_hash, "type": "email"},
            )
        if verified.status_code != 200:
            raise HTTPException(401, detail={"code": "AUTH_EMAIL_TOKEN_REJECTED"})
        tokens = verified.json()
        if not isinstance(tokens, dict) or not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise HTTPException(502, detail={"code": "AUTH_TOKEN_RESPONSE_INVALID"})
    else:
        if not code:
            raise HTTPException(400, detail={"code": "AUTH_CALLBACK_CODE_MISSING"})
        tokens = await _exchange_code(code, verifier)
    session_id, max_age, _ = await _store_session(tokens)
    response = RedirectResponse(_post_login_redirect(), status_code=303)
    _cookie(response, session_id, max_age=max_age)
    if provider != "email":
        response.delete_cookie(
            OAUTH_STATE_COOKIE,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/auth/session")
async def session(request: Request) -> JSONResponse:
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(401, detail={"code": "AUTH_SESSION_REQUIRED"})
    user_id, tokens = await _load_session(session_id)
    now = int(datetime.now(timezone.utc).timestamp())
    if tokens["expires_at"] - now < 90:
        profile, max_age = await _rotate(session_id)
        response = JSONResponse({"authenticated": True, **profile}, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
        _cookie(response, session_id, max_age=max_age)
        return response
    claims = await asyncio.to_thread(_verify_jwt, tokens["access_token"])
    if claims.get("sub") != user_id:
        await _revoke(session_id)
        raise HTTPException(401, detail={"code": "AUTH_SESSION_SUBJECT_MISMATCH"})
    return JSONResponse({"authenticated": True, "user_id": user_id, "app_role": claims.get("app_role", "customer")}, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.post("/auth/refresh")
async def refresh(request: Request) -> JSONResponse:
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(401, detail={"code": "AUTH_SESSION_REQUIRED"})
    profile, max_age = await _rotate(session_id)
    response = JSONResponse({"authenticated": True, **profile}, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    _cookie(response, session_id, max_age=max_age)
    return response


@router.post("/auth/logout")
async def logout(request: Request) -> Response:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        try:
            try:
                _, tokens = await _load_session(session_id)
            except HTTPException:
                tokens = None
            if tokens:
                try:
                    base, key = _supabase()
                    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
                        await client.post(
                            base + "/auth/v1/logout?scope=local",
                            headers={"apikey": key, "Authorization": "Bearer " + tokens["access_token"]},
                        )
                except (httpx.HTTPError, HTTPException):
                    # Local revocation is authoritative for this BFF session even if Auth is unavailable.
                    pass
        finally:
            await _revoke(session_id)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


class EmailOtpIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    create_user: bool = True


@router.post("/auth/email/start")
async def email_otp_start(payload: EmailOtpIn) -> JSONResponse:
    email = payload.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@") or any(ch.isspace() for ch in email):
        raise HTTPException(422, detail={"code": "AUTH_EMAIL_INVALID"})
    state = secrets.token_urlsafe(32)
    await _create_pending("email", "", state)
    callback = _callback_url() + "?" + urlencode({"state": state})
    base, key = _supabase()
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = await client.post(
            base + "/auth/v1/otp?" + urlencode({"redirect_to": callback}),
            headers={"apikey": key, "Content-Type": "application/json"},
            json={
                "email": email,
                "create_user": payload.create_user,
            },
        )
    if response.status_code not in {200, 201}:
        raise HTTPException(502, detail={"code": "AUTH_EMAIL_OTP_UNAVAILABLE"})
    return JSONResponse({"status": "verification_sent"}, headers={"Cache-Control": "no-store"})


class AppleNativeSignInIn(BaseModel):
    id_token: str = Field(min_length=100, max_length=12000)
    nonce: str = Field(min_length=16, max_length=256)


@router.post("/auth/ios/apple")
async def ios_apple_sign_in(payload: AppleNativeSignInIn, request: Request) -> Response:
    """Exchange a native Apple ID token; only an opaque HttpOnly session cookie is returned."""
    # Native URLSession requests do not send Origin. Reject browser-originated
    # requests so this CSRF-exempt endpoint cannot be abused for login-CSRF.
    if request.headers.get("origin"):
        raise HTTPException(403, detail={"code": "AUTH_NATIVE_ORIGIN_REJECTED"})
    base, key = _supabase()
    async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=False) as client:
        response = await client.post(
            base + "/auth/v1/token?grant_type=id_token",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"provider": "apple", "id_token": payload.id_token, "nonce": payload.nonce},
        )
    if response.status_code != 200:
        raise HTTPException(401, detail={"code": "AUTH_APPLE_NATIVE_TOKEN_REJECTED"})
    tokens = response.json()
    if not isinstance(tokens, dict) or not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise HTTPException(502, detail={"code": "AUTH_TOKEN_RESPONSE_INVALID"})
    session_id, max_age, profile = await _store_session(tokens)
    result = JSONResponse({"authenticated": True, **profile}, headers={"Cache-Control": "no-store"})
    _cookie(result, session_id, max_age=max_age)
    return result



async def auth_readiness() -> dict[str, Any]:
    """Fail readiness until storage, signing keys, and configured providers are real."""
    required = [
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_JWKS_URL",
        "SUPABASE_JWT_ISSUER",
        "AUTH_CALLBACK_URL",
        "AUTH_SESSION_DATABASE_URL",
        "AUTH_SESSION_ENCRYPTION_KEY",
        "AUTH_EMAIL_DELIVERY_VERIFIED",
    ]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    result: dict[str, Any] = {
        "configured": not missing,
        "missing_configuration": missing,
        "database_ready": False,
        "jwks_ready": False,
        "providers": {"google": False, "apple": False, "microsoft": False},
        "email_delivery_verified": os.getenv("AUTH_EMAIL_DELIVERY_VERIFIED", "").lower() == "true",
        "ready": False,
    }
    if missing:
        return result
    try:
        base, key = _supabase()
        _callback_url()
        _fernet()
        _session_ttl()
        _post_login_redirect()
        expected_jwks = base + "/auth/v1/.well-known/jwks.json"
        if os.getenv("SUPABASE_JWKS_URL", "").strip() != expected_jwks:
            return result
        if os.getenv("SUPABASE_JWT_ISSUER", "").strip() != base + "/auth/v1":
            return result
        if os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip() != "authenticated":
            return result
        pool = await _db()
        async with pool.acquire() as conn:
            db = await conn.fetchrow(
                """SELECT
                    to_regclass('auth_private.pending_auth') IS NOT NULL AS pending_exists,
                    to_regclass('auth_private.sessions') IS NOT NULL AS sessions_exists,
                    has_schema_privilege(current_user, 'auth_private', 'USAGE') AS schema_usage,
                    COALESCE((SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('auth_private.pending_auth')), false) AS pending_rls,
                    COALESCE((SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('auth_private.sessions')), false) AS sessions_rls,
                    has_table_privilege(current_user, 'auth_private.pending_auth', 'SELECT') AS pending_select,
                    has_table_privilege(current_user, 'auth_private.pending_auth', 'INSERT') AS pending_insert,
                    has_table_privilege(current_user, 'auth_private.pending_auth', 'DELETE') AS pending_delete,
                    has_table_privilege(current_user, 'auth_private.sessions', 'SELECT') AS sessions_select,
                    has_table_privilege(current_user, 'auth_private.sessions', 'INSERT') AS sessions_insert,
                    has_table_privilege(current_user, 'auth_private.sessions', 'UPDATE') AS sessions_update,
                    has_table_privilege(current_user, 'auth_private.sessions', 'DELETE') AS sessions_delete,
                    has_schema_privilege('anon', 'auth_private', 'USAGE') AS anon_schema_usage,
                    has_schema_privilege('authenticated', 'auth_private', 'USAGE') AS authenticated_schema_usage,
                    has_table_privilege('anon', 'auth_private.sessions', 'SELECT') AS anon_session_select,
                    has_table_privilege('authenticated', 'auth_private.sessions', 'SELECT') AS authenticated_session_select,
                    has_table_privilege('anon', 'auth_private.pending_auth', 'SELECT') AS anon_pending_select,
                    has_table_privilege('authenticated', 'auth_private.pending_auth', 'SELECT') AS authenticated_pending_select,
                    EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='auth_private' AND tablename='sessions' AND policyname='auth_private_bff_service_all') AS sessions_service_policy,
                    EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='auth_private' AND tablename='pending_auth' AND policyname='auth_private_bff_service_all') AS pending_service_policy"""
            )
        required_database_checks = (
            "pending_exists", "sessions_exists", "schema_usage",
            "pending_rls", "sessions_rls",
            "pending_select", "pending_insert", "pending_delete",
            "sessions_select", "sessions_insert", "sessions_update", "sessions_delete",
            "sessions_service_policy", "pending_service_policy",
        )
        client_access_denied = not any(bool(db[name]) for name in (
            "anon_schema_usage", "authenticated_schema_usage",
            "anon_session_select", "authenticated_session_select",
            "anon_pending_select", "authenticated_pending_select",
        ))
        result["client_access_denied"] = client_access_denied
        result["database_ready"] = bool(db) and all(bool(db[name]) for name in required_database_checks) and client_access_denied
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            jwks_response = await client.get(expected_jwks)
            settings_response = await client.get(
                base + "/auth/v1/settings",
                headers={"apikey": key},
            )
        if jwks_response.status_code == 200:
            keys = jwks_response.json().get("keys", [])
            signing_keys = [item for item in keys if isinstance(item, dict) and item.get("use", "sig") == "sig"]
            result["jwks_ready"] = bool(signing_keys) and all(
                item.get("kid") and item.get("alg") in {"ES256", "RS256"}
                for item in signing_keys
            )
        if settings_response.status_code == 200:
            external = settings_response.json().get("external", {})
            result["providers"] = {
                "google": external.get("google") is True,
                "apple": external.get("apple") is True,
                "microsoft": external.get("azure") is True,
            }
    except Exception:
        pass
    providers_ready = all(result["providers"].values())
    result["ready"] = (
        result["configured"]
        and result["database_ready"]
        and result["jwks_ready"]
        and providers_ready
        and result["email_delivery_verified"]
    )
    return result


@router.get("/auth/providers")
async def providers() -> dict[str, Any]:
    return {
        "email_otp": True,
        "web": ["google", "apple", "microsoft"],
        "ios": {"apple_native": True, "microsoft_oauth": True, "callback_scheme_required": True, "apple_native_callback_scheme_required": False, "session_transport": "Supabase Swift SDK session or optional HttpOnly Secure BFF cookie"},
        "microsoft_provider_id": "azure",
    }

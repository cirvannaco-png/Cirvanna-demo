from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app import auth_sessions


def make_client():
    app = FastAPI()
    app.include_router(auth_sessions.router)
    return TestClient(app)


def test_pkce_challenge_uses_sha256_base64url_without_padding():
    verifier = "a" * 64
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert auth_sessions._challenge(verifier) == expected


def test_provider_contract_exposes_web_and_native_ios_paths():
    with make_client() as client:
        response = client.get("/auth/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["email_otp"] is True
    assert body["web"] == ["google", "apple", "microsoft"]
    assert body["microsoft_provider_id"] == "azure"
    assert body["ios"]["apple_native"] is True


def test_native_apple_endpoint_rejects_browser_origin():
    with make_client() as client:
        response = client.post(
            "/auth/ios/apple",
            headers={"Origin": "https://attacker.example"},
            json={"id_token": "x" * 120, "nonce": "n" * 32},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_NATIVE_ORIGIN_REJECTED"


def test_unknown_provider_is_rejected():
    with make_client() as client:
        response = client.get("/auth/login/facebook", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "AUTH_PROVIDER_NOT_SUPPORTED"


def test_microsoft_login_uses_supabase_azure_provider_and_pkce(monkeypatch):
    async def pending(provider, verifier, state):
        assert provider == "microsoft"
        assert len(verifier) >= 43
        assert len(state) >= 32

    monkeypatch.setattr(auth_sessions, "_create_pending", pending)
    monkeypatch.setattr(auth_sessions, "_supabase", lambda: ("https://project.supabase.co", "sb_publishable_test"))
    monkeypatch.setattr(auth_sessions, "_callback_url", lambda: "https://bff.example.com/auth/callback")
    with make_client() as client:
        response = client.get("/auth/login/microsoft", follow_redirects=False)
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    params = parse_qs(location.query)
    assert location.netloc == "project.supabase.co"
    assert params["provider"] == ["azure"]
    assert params["code_challenge_method"] == ["s256"]
    assert len(params["code_challenge"][0]) == 43
    assert params["scopes"] == ["email"]
    assert "state=" in params["redirect_to"][0]
    cookie = response.headers["set-cookie"].lower()
    assert "__host-cirvanna_oauth_state=" in cookie
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "max-age=0" not in cookie


def test_jwt_verifier_accepts_only_valid_supabase_es256_claims(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://project.supabase.co/auth/v1",
            "aud": "authenticated",
            "sub": "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4",
            "iat": now,
            "exp": now + 300,
            "app_role": "customer",
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "staging-key-1"},
    )
    class FakeJwks:
        def __init__(self, *args, **kwargs):
            pass

        def get_signing_key_from_jwt(self, supplied):
            assert supplied == token
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://project.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(auth_sessions.jwt, "PyJWKClient", FakeJwks)
    monkeypatch.setattr(auth_sessions, "_jwks_client", None)
    claims = auth_sessions._verify_jwt(token)
    assert claims["sub"] == "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4"
    assert claims["app_role"] == "customer"


def test_jwt_verifier_rejects_wrong_issuer(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    now = int(time.time())
    token = jwt.encode(
        {"iss": "https://attacker.example", "aud": "authenticated", "sub": "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4", "iat": now, "exp": now + 300},
        private_key,
        algorithm="ES256",
        headers={"kid": "attacker-key"},
    )
    class FakeJwks:
        def __init__(self, *args, **kwargs):
            pass

        def get_signing_key_from_jwt(self, supplied):
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://project.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(auth_sessions.jwt, "PyJWKClient", FakeJwks)
    monkeypatch.setattr(auth_sessions, "_jwks_client", None)
    with pytest.raises(HTTPException) as exc:
        auth_sessions._verify_jwt(token)
    assert exc.value.status_code == 401


def test_auth_cookie_is_httponly_secure_host_only_and_lax():
    from starlette.responses import Response

    response = Response()
    auth_sessions._cookie(response, "opaque-session-handle", max_age=3600)
    cookie = response.headers["set-cookie"].lower()
    assert "__host-cirvanna_session=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "domain=" not in cookie

def test_email_magic_link_callback_validates_nested_redirect_and_sets_opaque_cookie(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"access_token": "verified-access", "refresh_token": "rotated-refresh"}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            calls["url"] = url
            calls["json"] = kwargs["json"]
            return FakeResponse()

    async def consume(state):
        assert state == "state-123"
        return "email", ""

    async def store(tokens):
        assert tokens["access_token"] == "verified-access"
        return "opaque-handle", 3600, {"user_id": "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4", "app_role": "customer"}

    monkeypatch.setattr(auth_sessions, "_callback_url", lambda: "https://bff.example.com/auth/callback")
    monkeypatch.setattr(auth_sessions, "_pending_provider", lambda state: asyncio.sleep(0, result="email"))
    monkeypatch.setattr(auth_sessions, "_consume_pending", consume)
    monkeypatch.setattr(auth_sessions, "_supabase", lambda: ("https://project.supabase.co", "sb_publishable_test"))
    monkeypatch.setattr(auth_sessions, "_store_session", store)
    monkeypatch.setattr(auth_sessions.httpx, "AsyncClient", FakeClient)

    with make_client() as client:
        response = client.get(
            "/auth/callback",
            params={
                "next": "https://bff.example.com/auth/callback?state=state-123",
                "token_hash": "one-time-token-hash",
                "type": "email",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert calls["url"] == "https://project.supabase.co/auth/v1/verify"
    assert calls["json"] == {"token_hash": "one-time-token-hash", "type": "email"}
    cookie = response.headers["set-cookie"].lower()
    assert "__host-cirvanna_session=opaque-handle" in cookie
    assert "httponly" in cookie and "secure" in cookie


def test_oauth_callback_requires_initiating_browser_state_cookie_without_consuming_state(monkeypatch):
    consumed = False

    async def provider(state):
        assert state == "oauth-state"
        return "google"

    async def consume(state):
        nonlocal consumed
        consumed = True
        return "google", "pkce-verifier"

    monkeypatch.setattr(auth_sessions, "_pending_provider", provider)
    monkeypatch.setattr(auth_sessions, "_consume_pending", consume)
    with make_client() as client:
        response = client.get(
            "/auth/callback",
            params={"state": "oauth-state", "code": "authorization-code"},
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "AUTH_BROWSER_STATE_MISMATCH"
    assert consumed is False


def test_oauth_callback_accepts_matching_browser_state_and_clears_state_cookie(monkeypatch):
    async def provider(state):
        assert state == "oauth-state"
        return "google"

    async def consume(state):
        assert state == "oauth-state"
        return "google", "pkce-verifier"

    async def exchange(code, verifier):
        assert code == "authorization-code"
        assert verifier == "pkce-verifier"
        return {"access_token": "verified-access", "refresh_token": "rotated-refresh"}

    async def store(tokens):
        assert tokens["access_token"] == "verified-access"
        return "opaque-handle", 3600, {"user_id": "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4", "app_role": "customer"}

    monkeypatch.setattr(auth_sessions, "_pending_provider", provider)
    monkeypatch.setattr(auth_sessions, "_consume_pending", consume)
    monkeypatch.setattr(auth_sessions, "_exchange_code", exchange)
    monkeypatch.setattr(auth_sessions, "_store_session", store)
    with make_client() as client:
        client.cookies.set(auth_sessions.OAUTH_STATE_COOKIE, "oauth-state")
        response = client.get(
            "/auth/callback",
            params={"state": "oauth-state", "code": "authorization-code"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    cookie_headers = response.headers.get_list("set-cookie")
    assert any("__Host-cirvanna_session=opaque-handle" in item for item in cookie_headers)
    assert any("__Host-cirvanna_oauth_state=" in item and "Max-Age=0" in item for item in cookie_headers)


def test_email_magic_link_callback_rejects_external_next_url(monkeypatch):
    monkeypatch.setattr(auth_sessions, "_callback_url", lambda: "https://bff.example.com/auth/callback")
    with make_client() as client:
        response = client.get(
            "/auth/callback",
            params={
                "next": "https://attacker.example/auth/callback?state=state-123",
                "token_hash": "one-time-token-hash",
                "type": "email",
            },
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "AUTH_CALLBACK_STATE_MISSING"

def test_auth_readiness_fails_closed_when_runtime_secrets_are_missing(monkeypatch):
    for name in [
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_JWKS_URL",
        "SUPABASE_JWT_ISSUER",
        "AUTH_CALLBACK_URL",
        "AUTH_SESSION_DATABASE_URL",
        "AUTH_SESSION_ENCRYPTION_KEY",
        "AUTH_EMAIL_DELIVERY_VERIFIED",
    ]:
        monkeypatch.delenv(name, raising=False)
    result = asyncio.run(auth_sessions.auth_readiness())
    assert result["ready"] is False
    assert "AUTH_SESSION_DATABASE_URL" in result["missing_configuration"]
    assert result["database_ready"] is False
    assert result["jwks_ready"] is False


def test_post_login_redirect_rejects_external_redirects(monkeypatch):
    monkeypatch.setenv("AUTH_POST_LOGIN_REDIRECT", "https://attacker.example")
    with pytest.raises(HTTPException) as exc:
        auth_sessions._post_login_redirect()
    assert exc.value.status_code == 503

def test_api_session_refresh_marks_cookie_for_sliding_expiry(monkeypatch):
    user_id = "3f44c3f7-9b9d-44d8-8a56-ef25ab86d5b4"
    reads = 0

    async def load_session(session_id):
        nonlocal reads
        reads += 1
        expiry = int(time.time()) + (10 if reads == 1 else 3600)
        return user_id, {"access_token": "access", "refresh_token": "refresh", "expires_at": expiry}

    async def rotate(session_id):
        return {"user_id": user_id, "app_role": "customer"}, 86400

    monkeypatch.setattr(auth_sessions, "_load_session", load_session)
    monkeypatch.setattr(auth_sessions, "_rotate", rotate)
    monkeypatch.setattr(auth_sessions, "_verify_jwt", lambda token: {"sub": user_id, "app_role": "customer"})

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/commerce/me",
        "raw_path": b"/api/commerce/me",
        "query_string": b"",
        "headers": [(b"cookie", (auth_sessions.COOKIE_NAME + "=opaque-handle").encode())],
        "server": ("bff.example.com", 443),
        "client": ("test-client", 1234),
    }
    request = Request(scope)
    token = asyncio.run(auth_sessions.session_access_token(request))
    assert token == "access"
    assert request.state.auth_session_refresh_max_age == 86400

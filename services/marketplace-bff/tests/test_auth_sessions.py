from __future__ import annotations

import base64
import hashlib
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app import auth_sessions


def test_pkce_challenge_uses_sha256_base64url_without_padding():
    verifier = "a" * 64
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert auth_sessions._challenge(verifier) == expected


def test_provider_contract_exposes_web_and_native_ios_paths():
    with TestClient(auth_sessions.router) as client:
        response = client.get("/auth/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["email_otp"] is True
    assert body["web"] == ["google", "apple", "microsoft"]
    assert body["microsoft_provider_id"] == "azure"
    assert body["ios"]["apple_native"] is True


def test_unknown_provider_is_rejected(client=None):
    with TestClient(auth_sessions.router) as client:
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
    with TestClient(auth_sessions.router) as client:
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

    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://project.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(auth_sessions.jwt, "PyJWKClient", FakeJwks)
    monkeypatch.setattr(auth_sessions, "_jwks_client", None)
    with pytest.raises(Exception):
        auth_sessions._verify_jwt(token)


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

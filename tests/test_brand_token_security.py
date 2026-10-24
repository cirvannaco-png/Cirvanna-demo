"""Security tests for brand JWT primitives."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "services" / "brand-partner-api" / "token_security.py"
spec = importlib.util.spec_from_file_location("brand_token_security", MODULE_PATH)
brand_auth = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(brand_auth)


def test_missing_or_short_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("BRAND_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        brand_auth.create_access_token(brand_auth.BrandPrincipal(
            brand_id="brand-1", brand_name="Test", email="test@example.com"
        ))


def test_valid_access_token_round_trip(monkeypatch):
    monkeypatch.setenv("BRAND_JWT_SECRET", "test-only-secret-that-is-long-enough-123")
    principal = brand_auth.BrandPrincipal(
        brand_id="brand-1", brand_name="Test", email="test@example.com",
        permissions=["products:read"],
    )
    token = brand_auth.create_access_token(principal)
    decoded = brand_auth.decode_access_token(token)
    assert decoded.brand_id == "brand-1"
    assert decoded.permissions == ["products:read"]


def test_invalid_token_is_rejected(monkeypatch):
    monkeypatch.setenv("BRAND_JWT_SECRET", "test-only-secret-that-is-long-enough-123")
    with pytest.raises(HTTPException) as error:
        brand_auth.decode_access_token("not-a-jwt")
    assert error.value.status_code == 401


def test_missing_permission_is_rejected():
    principal = brand_auth.BrandPrincipal(
        brand_id="brand-1", brand_name="Test", email="test@example.com",
        permissions=["products:read"],
    )
    with pytest.raises(HTTPException) as error:
        brand_auth.require_permission(principal, "products:write")
    assert error.value.status_code == 403

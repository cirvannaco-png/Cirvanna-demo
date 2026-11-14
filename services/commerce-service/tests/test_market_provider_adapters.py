from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app import market_provider_adapters as adapters


DIGEST = "a" * 64
MERCHANT_TOKEN = "merchant-verification-adapter-token-at-least-thirty-two-bytes"
FULFILLMENT_TOKEN = "fulfillment-adapter-token-at-least-thirty-two-bytes"


def merchant():
    return SimpleNamespace(
        id="123e4567-e89b-12d3-a456-426614174000",
        legal_name="Studio One Limited",
        legal_country_code="KE",
        country_code="KE",
    )


def test_development_merchant_approval_is_explicitly_not_provider_evidence(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "development")

    result = adapters.verify_merchant_approval(merchant(), "manual-review-ref", ["KE"])

    assert result["verification_reference"] == "manual-review-ref"
    assert result["audit_note"] == "manual-development-verification"


def test_production_merchant_approval_fails_closed_without_adapter(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_URL", raising=False)
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_TOKEN", raising=False)

    with pytest.raises(HTTPException) as error:
        adapters.verify_merchant_approval(merchant(), "unverified-ref", ["KE"])

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "MERCHANT_VERIFICATION_ADAPTER_NOT_TRUSTED"


def test_verified_merchant_result_is_bound_to_exact_entity_and_operating_markets(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "staging")
    monkeypatch.setenv("MERCHANT_VERIFICATION_ADAPTER_URL", "https://merchant-adapter.example.test")
    monkeypatch.setenv("MERCHANT_VERIFICATION_ADAPTER_TOKEN", MERCHANT_TOKEN)
    observed = datetime.now(timezone.utc)
    expires = observed + timedelta(days=2)
    monkeypatch.setattr(adapters, "_adapter_post", lambda *_args, **_kwargs: {
        "verification_status": "verified",
        "merchant_id": merchant().id,
        "legal_country_code": "KE",
        "operating_markets": ["KE", "UG"],
        "provider_reference": "kyb-case-001",
        "all_required_checks_complete": True,
        "policy_version": "kyb-policy-2026-01",
        "provider_id": "kyb-provider",
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "evidence_sha256": DIGEST,
    })

    result = adapters.verify_merchant_approval(merchant(), "kyb-case-001", ["UG", "KE"])

    assert result["verification_reference"] == "kyb-provider:kyb-case-001"
    assert "evidence_sha256=" + DIGEST in result["audit_note"]


def test_merchant_verification_rejects_operating_market_mismatch(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "staging")
    monkeypatch.setenv("MERCHANT_VERIFICATION_ADAPTER_URL", "https://merchant-adapter.example.test")
    monkeypatch.setenv("MERCHANT_VERIFICATION_ADAPTER_TOKEN", MERCHANT_TOKEN)
    observed = datetime.now(timezone.utc)
    monkeypatch.setattr(adapters, "_adapter_post", lambda *_args, **_kwargs: {
        "verification_status": "verified",
        "merchant_id": merchant().id,
        "legal_country_code": "KE",
        "operating_markets": ["KE"],
        "provider_reference": "kyb-case-002",
        "all_required_checks_complete": True,
        "policy_version": "kyb-policy-2026-01",
        "provider_id": "kyb-provider",
        "observed_at": observed.isoformat(),
        "expires_at": (observed + timedelta(days=1)).isoformat(),
        "evidence_sha256": DIGEST,
    })

    with pytest.raises(HTTPException) as error:
        adapters.verify_merchant_approval(merchant(), "kyb-case-002", ["KE", "UG"])

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "MERCHANT_PROVIDER_EVIDENCE_MISMATCH"


def test_production_fulfilment_market_activation_requires_verified_serviceability(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.setenv("FULFILLMENT_ADAPTER_URL", "https://fulfilment-adapter.example.test")
    monkeypatch.setenv("FULFILLMENT_ADAPTER_TOKEN", FULFILLMENT_TOKEN)
    observed = datetime.now(timezone.utc)
    expires = observed + timedelta(hours=1)
    monkeypatch.setattr(adapters, "_adapter_post", lambda *_args, **_kwargs: {
        "status": "verified",
        "merchant_id": "merchant-001",
        "market_country_code": "KE",
        "provider": "carrier-001",
        "provider_reference": "service-zone-ref",
        "serviceability_confirmed": True,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "evidence_sha256": DIGEST,
    })

    adapters.verify_fulfillment_market(
        merchant_id="merchant-001",
        market_country_code="KE",
        provider="carrier-001",
        provider_reference="service-zone-ref",
        observed_at=observed,
        expires_at=expires,
    )


def test_fulfilment_quote_requires_exact_provider_bound_quote(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "staging")
    monkeypatch.setenv("FULFILLMENT_ADAPTER_URL", "https://fulfilment-adapter.example.test")
    monkeypatch.setenv("FULFILLMENT_ADAPTER_TOKEN", FULFILLMENT_TOKEN)
    quote = {
        "provider": "carrier-001",
        "provider_quote_id": "quote-001",
        "destination_country_code": "KE",
        "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery",
        "charge_basis": "per_quote",
        "amount_minor": 250,
        "currency": "KES",
        "status": "confirmed",
        "distance_km": "14.5",
        "observed_at": "2026-11-14T10:00:00+00:00",
        "expires_at": "2026-11-14T11:00:00+00:00",
    }
    monkeypatch.setattr(adapters, "_adapter_post", lambda *_args, **_kwargs: {
        "verification_status": "verified",
        "variant_id": "variant-001",
        "quote": dict(quote),
        "evidence_sha256": DIGEST,
    })

    adapters.verify_fulfillment_quote("variant-001", quote)

    monkeypatch.setattr(adapters, "_adapter_post", lambda *_args, **_kwargs: {
        "verification_status": "verified",
        "variant_id": "variant-001",
        "quote": {**quote, "amount_minor": 1},
        "evidence_sha256": DIGEST,
    })
    with pytest.raises(HTTPException) as error:
        adapters.verify_fulfillment_quote("variant-001", quote)

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "FULFILLMENT_QUOTE_PROVIDER_EVIDENCE_MISMATCH"


def test_fulfilment_adapter_not_ready_when_missing_in_production(monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.delenv("FULFILLMENT_ADAPTER_URL", raising=False)
    monkeypatch.delenv("FULFILLMENT_ADAPTER_TOKEN", raising=False)

    assert adapters.adapter_ready("FULFILLMENT_ADAPTER") is False

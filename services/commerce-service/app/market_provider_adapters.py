"""Production/staging verification adapters for merchant and fulfilment operations.

Vendor-specific SDKs stay behind a trusted Cirvanna adapter service. Commerce accepts
only verified, exact-resource evidence from that adapter in staging/production.
Local development fixtures may bypass the adapter but are never production evidence.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from typing import Any

import httpx
from fastapi import HTTPException

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,39}$")


def provider_verification_required() -> bool:
    return os.getenv("COMMERCE_ENVIRONMENT", "development").strip().lower() in {
        "staging", "stage", "production", "prod",
    }


def _provider_config(prefix: str) -> tuple[str, str]:
    url = os.getenv(prefix + "_URL", "").strip().rstrip("/")
    token = os.getenv(prefix + "_TOKEN", "").strip()
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local and not provider_verification_required()))
    ):
        raise HTTPException(503, detail={"code": prefix + "_ADAPTER_NOT_TRUSTED"})
    if len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": prefix + "_ADAPTER_AUTH_NOT_CONFIGURED"})
    return url, token


def _adapter_post(prefix: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base, token = _provider_config(prefix)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    try:
        with httpx.Client(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            ready = client.get(base + "/ready", headers=headers)
            if ready.status_code != 200:
                raise HTTPException(503, detail={"code": prefix + "_ADAPTER_NOT_READY"})
            readiness = ready.json()
            if not isinstance(readiness, dict) or readiness.get("ready") is not True:
                raise HTTPException(503, detail={"code": prefix + "_ADAPTER_NOT_READY"})
            response = client.post(base + path, headers=headers, json=payload)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, detail={"code": prefix + "_ADAPTER_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": prefix + "_ADAPTER_VERIFICATION_FAILED"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": prefix + "_ADAPTER_RESPONSE_INVALID"}) from exc
    if not isinstance(result, dict):
        raise HTTPException(502, detail={"code": prefix + "_ADAPTER_RESPONSE_INVALID"})
    return result


def _parse_aware(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        raise HTTPException(502, detail={"code": code})
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(502, detail={"code": code}) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(502, detail={"code": code})
    return parsed.astimezone(timezone.utc)


def _validate_evidence_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise HTTPException(502, detail={"code": code})
    return value


def verify_merchant_approval(
    merchant: Any,
    verification_reference: str,
    operating_markets: list[str],
) -> dict[str, str]:
    """Verify merchant approval against the configured legal/KYB adapter."""
    if not provider_verification_required():
        return {
            "verification_reference": verification_reference,
            "audit_note": "manual-development-verification",
        }
    reference = verification_reference.strip()
    if not reference or len(reference) > 120:
        raise HTTPException(422, detail={"code": "MERCHANT_VERIFICATION_REFERENCE_INVALID"})
    legal_country = (merchant.legal_country_code or merchant.country_code).upper()
    result = _adapter_post("MERCHANT_VERIFICATION_ADAPTER", "/v1/merchant-verifications/verify", {
        "merchant_id": merchant.id,
        "legal_name": merchant.legal_name,
        "legal_country_code": legal_country,
        "operating_markets": sorted({value.upper() for value in operating_markets}),
        "provider_reference": reference,
    })
    provider_id = result.get("provider_id")
    provider_reference = result.get("provider_reference")
    if not (
        result.get("verification_status") == "verified"
        and result.get("merchant_id") == merchant.id
        and result.get("legal_country_code") == legal_country
        and result.get("operating_markets") == sorted({value.upper() for value in operating_markets})
        and provider_reference == reference
        and result.get("all_required_checks_complete") is True
        and isinstance(result.get("policy_version"), str)
        and 1 <= len(result["policy_version"]) <= 80
        and isinstance(provider_id, str)
        and PROVIDER_ID_RE.fullmatch(provider_id)
    ):
        raise HTTPException(403, detail={"code": "MERCHANT_PROVIDER_EVIDENCE_MISMATCH"})
    observed = _parse_aware(result.get("observed_at"), "MERCHANT_PROVIDER_TIMESTAMP_INVALID")
    expires = _parse_aware(result.get("expires_at"), "MERCHANT_PROVIDER_TIMESTAMP_INVALID")
    current = datetime.now(timezone.utc)
    if observed > current + timedelta(minutes=5) or expires <= current or expires <= observed:
        raise HTTPException(403, detail={"code": "MERCHANT_PROVIDER_EVIDENCE_STALE"})
    digest = _validate_evidence_digest(result.get("evidence_sha256"), "MERCHANT_PROVIDER_DIGEST_INVALID")
    stored_reference = provider_id + ":" + reference
    if len(stored_reference) > 180:
        raise HTTPException(422, detail={"code": "MERCHANT_VERIFICATION_REFERENCE_INVALID"})
    return {
        "verification_reference": stored_reference,
        "audit_note": (
            "provider=" + provider_id
            + ";policy=" + result["policy_version"]
            + ";evidence_sha256=" + digest
            + ";observed_at=" + observed.isoformat()
            + ";expires_at=" + expires.isoformat()
        )[:500],
    }


def verify_fulfillment_market(
    *,
    merchant_id: str,
    market_country_code: str,
    provider: str,
    provider_reference: str,
    observed_at: datetime,
    expires_at: datetime,
) -> None:
    """Require independently checked provider serviceability before market activation."""
    if not provider_verification_required():
        return
    result = _adapter_post("FULFILLMENT_ADAPTER", "/v1/market-capabilities/verify", {
        "merchant_id": merchant_id,
        "market_country_code": market_country_code,
        "provider": provider,
        "provider_reference": provider_reference,
        "observed_at": observed_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    })
    digest = _validate_evidence_digest(result.get("evidence_sha256"), "FULFILLMENT_CAPABILITY_DIGEST_INVALID")
    result_observed = _parse_aware(result.get("observed_at"), "FULFILLMENT_CAPABILITY_TIMESTAMP_INVALID")
    result_expires = _parse_aware(result.get("expires_at"), "FULFILLMENT_CAPABILITY_TIMESTAMP_INVALID")
    if not (
        result.get("status") == "verified"
        and result.get("merchant_id") == merchant_id
        and result.get("market_country_code") == market_country_code
        and result.get("provider") == provider
        and result.get("provider_reference") == provider_reference
        and result.get("serviceability_confirmed") is True
        and result_observed == observed_at.astimezone(timezone.utc)
        and result_expires == expires_at.astimezone(timezone.utc)
        and result_expires > datetime.now(timezone.utc)
        and digest
    ):
        raise HTTPException(409, detail={"code": "FULFILLMENT_MARKET_PROVIDER_EVIDENCE_MISMATCH"})


def verify_fulfillment_quote(variant_id: str, quote: dict[str, Any]) -> None:
    """Verify every ingested live fulfilment quote against its source adapter."""
    if not provider_verification_required():
        return
    result = _adapter_post("FULFILLMENT_ADAPTER", "/v1/fulfillment-quotes/verify", {
        "variant_id": variant_id,
        "quote": quote,
    })
    _validate_evidence_digest(result.get("evidence_sha256"), "FULFILLMENT_QUOTE_DIGEST_INVALID")
    verified_quote = result.get("quote")
    exact_fields = (
        "provider", "provider_quote_id", "destination_country_code", "destination_key",
        "fulfillment_mode", "charge_basis", "amount_minor", "currency", "status",
        "distance_km", "observed_at", "expires_at",
    )
    exact = (
        isinstance(verified_quote, dict)
        and all(verified_quote.get(field) == quote.get(field) for field in exact_fields)
    )
    if (
        result.get("verification_status") != "verified"
        or result.get("variant_id") != variant_id
        or not exact
    ):
        raise HTTPException(409, detail={"code": "FULFILLMENT_QUOTE_PROVIDER_EVIDENCE_MISMATCH"})


def adapter_configured(prefix: str) -> bool:
    """Check local adapter settings without creating network traffic."""
    try:
        _provider_config(prefix)
        return True
    except HTTPException:
        return False


def adapter_ready(prefix: str) -> bool:
    """Probe a trusted provider adapter; configured credentials alone are not readiness."""
    try:
        base, token = _provider_config(prefix)
        with httpx.Client(
            timeout=httpx.Timeout(3.0, connect=1.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.get(
                base + "/ready",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        if response.status_code != 200:
            return False
        payload = response.json()
        return isinstance(payload, dict) and payload.get("ready") is True
    except (HTTPException, httpx.HTTPError, ValueError):
        return False


def verify_fx_quote(variant_id: str, quote: dict[str, Any]) -> None:
    """Bind an ingested FX rate and validity window to the configured FX adapter."""
    if not provider_verification_required():
        return
    result = _adapter_post("FX_ADAPTER", "/v1/fx-quotes/verify", {
        "variant_id": variant_id,
        "quote": quote,
    })
    _validate_evidence_digest(result.get("evidence_sha256"), "FX_QUOTE_DIGEST_INVALID")
    verified_quote = result.get("quote")
    exact_fields = (
        "provider", "provider_quote_id", "base_currency", "quote_currency", "rate",
        "rounding_rule", "spread_bps", "observed_at", "expires_at",
    )
    exact = (
        isinstance(verified_quote, dict)
        and all(verified_quote.get(field) == quote.get(field) for field in exact_fields)
    )
    if (
        result.get("verification_status") != "verified"
        or result.get("variant_id") != variant_id
        or not exact
    ):
        raise HTTPException(409, detail={"code": "FX_QUOTE_PROVIDER_EVIDENCE_MISMATCH"})


def verify_tax_quote(variant_id: str, quote: dict[str, Any]) -> None:
    """Bind an ingested tax rule and destination quote to the configured tax adapter."""
    if not provider_verification_required():
        return
    result = _adapter_post("TAX_ADAPTER", "/v1/tax-quotes/verify", {
        "variant_id": variant_id,
        "quote": quote,
    })
    _validate_evidence_digest(result.get("evidence_sha256"), "TAX_QUOTE_DIGEST_INVALID")
    verified_quote = result.get("quote")
    exact_fields = (
        "provider", "provider_quote_id", "destination_country_code", "destination_key",
        "jurisdiction", "tax_category", "basis", "amount_minor", "currency", "status",
        "authoritative", "rule_version", "observed_at", "expires_at",
    )
    exact = (
        isinstance(verified_quote, dict)
        and all(verified_quote.get(field) == quote.get(field) for field in exact_fields)
    )
    if (
        result.get("verification_status") != "verified"
        or result.get("variant_id") != variant_id
        or not exact
    ):
        raise HTTPException(409, detail={"code": "TAX_QUOTE_PROVIDER_EVIDENCE_MISMATCH"})


def verify_payment_capability(
    merchant_id: str, market_country_code: str, capability: dict[str, Any],
) -> None:
    """Bind supported transaction/settlement currencies to a payment provider record."""
    if not provider_verification_required():
        return
    result = _adapter_post("PAYMENT_CAPABILITY_ADAPTER", "/v1/payment-capabilities/verify", {
        "merchant_id": merchant_id,
        "market_country_code": market_country_code,
        "capability": capability,
    })
    _validate_evidence_digest(result.get("evidence_sha256"), "PAYMENT_CAPABILITY_DIGEST_INVALID")
    verified_capability = result.get("capability")
    exact_fields = (
        "provider", "state", "transaction_currencies", "settlement_currencies",
        "payment_methods", "provider_reference", "observed_at", "expires_at",
    )
    exact = (
        isinstance(verified_capability, dict)
        and all(verified_capability.get(field) == capability.get(field) for field in exact_fields)
    )
    if (
        result.get("verification_status") != "verified"
        or result.get("merchant_id") != merchant_id
        or result.get("market_country_code") != market_country_code
        or not exact
    ):
        raise HTTPException(409, detail={"code": "PAYMENT_CAPABILITY_PROVIDER_EVIDENCE_MISMATCH"})

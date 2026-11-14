"""Production/staging verification adapters for merchant and fulfilment operations.

Vendor-specific SDKs stay behind a trusted Cirvanna adapter service. Commerce accepts
only verified, exact-resource evidence from that adapter in staging/production.
Local development fixtures may bypass the adapter but are never production evidence.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
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


def verify_merchant_approval(merchant: Any, verification_reference: str) -> dict[str, str]:
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
        "operating_markets": sorted(
            row.market_country_code for row in getattr(merchant, "operating_markets", [])
        ),
        "provider_reference": reference,
    })
    provider_id = result.get("provider_id")
    provider_reference = result.get("provider_reference")
    if not (
        result.get("verification_status") == "verified"
        and result.get("merchant_id") == merchant.id
        and result.get("legal_country_code") == legal_country
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
    if observed > current.replace(microsecond=0) + __import__("datetime").timedelta(minutes=5) or expires <= current or expires <= observed:
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
    if not (
        result.get("status") == "verified"
        and result.get("merchant_id") == merchant_id
        and result.get("market_country_code") == market_country_code
        and result.get("provider") == provider
        and result.get("provider_reference") == provider_reference
        and result.get("serviceability_confirmed") is True
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
    exact_fields = (
        "provider", "provider_quote_id", "destination_country_code", "destination_key",
        "fulfillment_mode", "charge_basis", "amount_minor", "currency", "status",
    )
    exact = all(result.get(field) == quote.get(field) for field in exact_fields)
    if (
        result.get("status") != "verified"
        or result.get("variant_id") != variant_id
        or not exact
    ):
        raise HTTPException(409, detail={"code": "FULFILLMENT_QUOTE_PROVIDER_EVIDENCE_MISMATCH"})

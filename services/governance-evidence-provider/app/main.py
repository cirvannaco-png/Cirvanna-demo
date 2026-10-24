"""Authenticated, fail-closed evidence assembler for candidate-bound CAL decisions.

This service assembles evidence only from trusted internal services. It does not
invent user preferences, cultural requirements, context, catalog attributes, or
fit estimates. Missing providers and malformed/stale/mismatched evidence fail closed.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

SERVICE = "cirvanna-governance-evidence-provider"
bearer = HTTPBearer(auto_error=False)
TIMEOUT = 4.0
MAX_AGE_SECONDS = 30
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
app = FastAPI(title="Cirvanna Governance Evidence Provider", version="0.1.0")


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or now()).isoformat()


def _base(key: str) -> str:
    raw = os.getenv(key, "").strip()
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if not host or parts.username is not None or parts.password is not None or parts.query or parts.fragment or (parts.scheme != "https" and not (parts.scheme == "http" and local)):
        raise HTTPException(503, detail={"code": key + "_NOT_CONFIGURED_OR_UNTRUSTED"})
    return raw.rstrip("/")


def _token(key: str) -> str:
    value = os.getenv(key, "").strip()
    if len(value.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": key + "_NOT_CONFIGURED"})
    return value


def require_internal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = _token("EVIDENCE_PROVIDER_TOKEN")
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "EVIDENCE_PROVIDER_AUTH_FAILED"})


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    subject_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    catalog_product_id: str = Field(min_length=36, max_length=36)
    requested_at: str = Field(min_length=1, max_length=80)


async def _request(client: httpx.AsyncClient, env_url: str, env_token: str, method: str, path: str, payload: dict | None = None) -> dict:
    base, token = _base(env_url), _token(env_token)
    try:
        response = await client.request(method, base + path, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_TIMEOUT", "source": env_url}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_UNAVAILABLE", "source": env_url}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_REJECTED", "source": env_url, "upstream_status": response.status_code})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_INVALID_JSON", "source": env_url}) from exc
    if not isinstance(result, dict):
        raise HTTPException(503, detail={"code": "EVIDENCE_SOURCE_INVALID_SHAPE", "source": env_url})
    return result


POLICY_SIGNAL_KINDS = {"safety", "legal_eligibility", "user_hard_constraint", "other"}
POLICY_SIGNAL_STATES = {"pass", "block", "unknown"}


def _canonical_policy_evidence(
    request_id: str, user_id: str, candidate_id: str, catalog_product_id: str,
    candidate_attributes: list[str], context: dict[str, Any], upstream_signals: list[dict[str, Any]],
) -> bytes:
    """Canonical signature contract shared with the trusted policy-evidence provider."""
    normalized: list[dict[str, Any]] = []
    for signal in upstream_signals:
        if not isinstance(signal, dict):
            raise ValueError("upstream signals must be objects")
        kind, state = signal.get("kind"), signal.get("state")
        if kind not in POLICY_SIGNAL_KINDS or state not in POLICY_SIGNAL_STATES:
            raise ValueError("unsupported policy signal kind or state")
        if not isinstance(signal.get("required"), bool):
            raise ValueError("signal required must be boolean")
        if any(not isinstance(signal.get(key), str) or not signal[key].strip()
               for key in ("signal_id", "reason_code", "explanation", "source_version")):
            raise ValueError("policy signal provenance fields are required")
        confidence = signal.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise ValueError("policy signal confidence must be between zero and one")
        normalized.append({key: signal.get(key) for key in (
            "signal_id", "kind", "state", "reason_code", "explanation", "required", "confidence", "source_version"
        )})
    if len({item["signal_id"] for item in normalized}) != len(normalized):
        raise ValueError("duplicate policy signal identifiers")
    required_kinds = {"safety", "legal_eligibility", "user_hard_constraint"}
    if not required_kinds.issubset({item["kind"] for item in normalized}):
        raise ValueError("required safety, legal eligibility, and user hard-constraint signals are missing")
    if not isinstance(context, dict) or context.get("user_id") != user_id:
        raise ValueError("policy context must belong to the evaluated user")
    context_fields = ("user_id", "age_years", "location", "occasion", "climate")
    normalized_context = {key: context.get(key) for key in context_fields}
    if (normalized_context["age_years"] is not None and
            (isinstance(normalized_context["age_years"], bool) or not isinstance(normalized_context["age_years"], int)
             or not 0 <= normalized_context["age_years"] <= 125)):
        raise ValueError("policy context age is invalid")
    for key in ("location", "occasion", "climate"):
        value = normalized_context[key]
        if value is not None and (not isinstance(value, str) or len(value) > 120):
            raise ValueError("policy context fields are invalid")
    document = {
        "contract_version": "1.0.0", "request_id": request_id, "user_id": user_id,
        "candidate_id": candidate_id, "catalog_product_id": catalog_product_id,
        "context": normalized_context,
        "candidate_attributes": sorted({item.strip().casefold() for item in candidate_attributes}),
        "upstream_signals": sorted(normalized, key=lambda item: item["signal_id"]),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _attrs(product: dict[str, Any]) -> list[str]:
    raw = product.get("attributes")
    if product.get("attributes_complete") is not True or not isinstance(raw, dict) or not raw:
        raise HTTPException(503, detail={"code": "CATALOG_ATTRIBUTES_INCOMPLETE"})
    attrs: set[str] = set()
    for key, value in raw.items():
        k = str(key).strip().lower()
        if not k:
            continue
        if isinstance(value, (str, int, float, bool)):
            v = str(value).strip().lower()
            if v:
                attrs.add(f"{k}:{v}")
                attrs.add(v)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (str, int, float, bool)) and str(item).strip():
                    v = str(item).strip().lower()
                    attrs.add(f"{k}:{v}")
                    attrs.add(v)
    for key in ("name", "category", "brand", "description"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            attrs.add(f"{key}:{value.strip().lower()}")
    if not attrs:
        raise HTTPException(503, detail={"code": "CATALOG_ATTRIBUTES_INCOMPLETE"})
    return sorted(attrs)[:250]


def _fresh_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise HTTPException(503, detail={"code": "FIT_TIMESTAMP_MISSING"})
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "FIT_TIMESTAMP_INVALID"}) from exc
    if dt.tzinfo is None or dt > now() + timedelta(seconds=5) or now() - dt > timedelta(seconds=MAX_AGE_SECONDS):
        raise HTTPException(503, detail={"code": "FIT_EVIDENCE_STALE"})
    return dt.astimezone(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


async def _dependency_ready(
    client: httpx.AsyncClient, url_key: str, token_key: str, *, fit_provider: bool = False
) -> tuple[bool, dict[str, Any]]:
    """Probe source readiness, not just whether its URL is set."""
    try:
        result = await _request(client, url_key, token_key, "GET", "/ready")
    except HTTPException:
        return False, {}
    ready = result.get("ready") is True
    if fit_provider:
        # HMAC provenance cannot substitute for empirical fit-model calibration.
        ready = ready and result.get("fci_prediction_model_available") is True \
            and result.get("calibration_report_valid") is True
    return ready, result


@app.get("/ready")
async def readiness() -> dict[str, Any]:
    keys = ("EVIDENCE_PROVIDER_TOKEN", "NPL_SERVICE_TOKEN", "CULTURAL_IDENTITY_SERVICE_TOKEN", "CATALOG_API_TOKEN", "USI_PROFILE_API_TOKEN", "USER_CONTEXT_API_TOKEN", "FIT_EVIDENCE_API_TOKEN", "POLICY_EVIDENCE_API_TOKEN", "POLICY_EVIDENCE_HMAC_SECRET")
    urls = ("NPL_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_URL", "CATALOG_API_URL", "USI_PROFILE_API_URL", "USER_CONTEXT_API_URL", "FIT_EVIDENCE_API_URL", "POLICY_EVIDENCE_API_URL")
    configured = {key: len(os.getenv(key, "").encode("utf-8")) >= 32 for key in keys}
    for key in urls:
        try:
            _base(key)
            configured[key] = True
        except HTTPException:
            configured[key] = False
    upstream_ready: dict[str, bool] = {}
    fit_health: dict[str, Any] = {}
    if all(configured.values()):
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=2), trust_env=False, follow_redirects=False) as client:
            dependencies = (
                ("npl", "NPL_SERVICE_URL", "NPL_SERVICE_TOKEN", False),
                ("cultural_identity", "CULTURAL_IDENTITY_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_TOKEN", False),
                ("catalog", "CATALOG_API_URL", "CATALOG_API_TOKEN", False),
                ("usi_profile", "USI_PROFILE_API_URL", "USI_PROFILE_API_TOKEN", False),
                ("user_context", "USER_CONTEXT_API_URL", "USER_CONTEXT_API_TOKEN", False),
                ("fit_evidence", "FIT_EVIDENCE_API_URL", "FIT_EVIDENCE_API_TOKEN", True),
                ("policy_evidence", "POLICY_EVIDENCE_API_URL", "POLICY_EVIDENCE_API_TOKEN", False),
            )
            checks = await asyncio.gather(*(
                _dependency_ready(client, url_key, token_key, fit_provider=is_fit)
                for _, url_key, token_key, is_fit in dependencies
            ), return_exceptions=True)
            for (name, _url_key, _token_key, is_fit), check in zip(dependencies, checks):
                if isinstance(check, BaseException):
                    ready, health = False, {}
                else:
                    ready, health = check
                upstream_ready[name] = ready
                if is_fit:
                    fit_health = health
    else:
        upstream_ready = {name: False for name in ("npl", "cultural_identity", "catalog", "usi_profile", "user_context", "fit_evidence", "policy_evidence")}
    ready = all(configured.values()) and all(upstream_ready.values())
    result = {
        "service": SERVICE, "ready": ready, "configured": configured,
        "upstream_ready": upstream_ready,
        "fci_model_available": fit_health.get("fci_prediction_model_available") is True,
        "fit_calibration_report_valid": fit_health.get("calibration_report_valid") is True,
    }
    if not ready:
        raise HTTPException(503, detail=result)
    return result


@app.post("/v1/decision-evidence", dependencies=[Depends(require_internal)])
async def decision_evidence(payload: EvidenceRequest) -> dict[str, Any]:
    """Build an exact request envelope; no source is trusted based on browser fields."""
    try:
        requested = datetime.fromisoformat(payload.requested_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "REQUEST_TIMESTAMP_INVALID"}) from exc
    if requested.tzinfo is None or abs((now() - requested).total_seconds()) > 30:
        raise HTTPException(409, detail={"code": "REQUEST_TIMESTAMP_STALE"})
    catalog_product_id = payload.catalog_product_id.strip()
    if not UUID_RE.fullmatch(payload.candidate_id.strip()):
        raise HTTPException(422, detail={"code": "CANONICAL_CANDIDATE_ID_REQUIRED"})
    if not UUID_RE.fullmatch(catalog_product_id):
        raise HTTPException(422, detail={"code": "CANONICAL_CATALOG_PRODUCT_ID_REQUIRED"})

    request_id, user_id, candidate_id = payload.request_id, payload.subject_id, payload.candidate_id
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=2), trust_env=False, follow_redirects=False) as client:
        product = await _request(client, "CATALOG_API_URL", "CATALOG_API_TOKEN", "GET", "/products/" + quote(catalog_product_id, safe=""))
        if product.get("product_id", product.get("id")) != catalog_product_id or product.get("status") != "active":
            raise HTTPException(409, detail={"code": "CATALOG_CANDIDATE_MISMATCH_OR_INACTIVE"})
        candidate_attributes = _attrs(product)
        catalog_loaded_at = iso()

        common = {"request_id": request_id, "user_id": user_id, "candidate_id": candidate_id, "candidate_attributes": candidate_attributes}
        npl = await _request(client, "NPL_SERVICE_URL", "NPL_SERVICE_TOKEN", "POST", "/v1/evaluate", common)
        npl_loaded_at = iso()
        cultural = await _request(client, "CULTURAL_IDENTITY_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_TOKEN", "POST", "/v1/evaluate", {**common, "candidate_attributes_complete": True})
        cultural_loaded_at = iso()
        profile = await _request(client, "USI_PROFILE_API_URL", "USI_PROFILE_API_TOKEN", "GET", "/v1/profiles/" + quote(user_id, safe=""))
        usi_loaded_at = iso()
        context = await _request(client, "USER_CONTEXT_API_URL", "USER_CONTEXT_API_TOKEN", "GET", "/v1/context/" + quote(user_id, safe=""))
        context_loaded_at = iso()
        if (context.get("user_id") != user_id or not isinstance(context.get("context"), dict)
                or context["context"].get("user_id") != user_id):
            raise HTTPException(409, detail={"code": "USER_CONTEXT_MISSING_OR_MISMATCHED"})
        raw_context_for_fit = context["context"]
        fit_context = {key: raw_context_for_fit.get(key) for key in ("user_id", "age_years", "location", "occasion", "climate")}
        policy_evidence = await _request(client, "POLICY_EVIDENCE_API_URL", "POLICY_EVIDENCE_API_TOKEN", "POST", "/v1/evaluate", {
            **common, "catalog_product_id": catalog_product_id, "context": fit_context,
        })
        policy_loaded_at = iso()
        fit = await _request(client, "FIT_EVIDENCE_API_URL", "FIT_EVIDENCE_API_TOKEN", "POST", "/v1/estimate", {**common, "catalog_product_id": catalog_product_id, "context": fit_context})
        fit_generated_at = _fresh_timestamp(fit.get("generated_at"))

    for source, data in (("npl", npl), ("cultural", cultural)):
        if data.get("request_id") != request_id or data.get("user_id") != user_id or data.get("candidate_id") != candidate_id:
            raise HTTPException(409, detail={"code": "EVIDENCE_BINDING_MISMATCH", "source": source})
    if not isinstance(npl.get("negative_preferences"), list):
        raise HTTPException(503, detail={"code": "NPL_EVIDENCE_MISSING"})
    if not isinstance(npl.get("npl_evidence_signature"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", npl["npl_evidence_signature"]):
        raise HTTPException(503, detail={"code": "NPL_EVIDENCE_UNSIGNED"})
    if not isinstance(cultural.get("cultural_requirements"), list):
        raise HTTPException(503, detail={"code": "CULTURAL_EVIDENCE_MISSING"})
    if any(not isinstance(item, dict) or item.get("user_id") != user_id for item in cultural["cultural_requirements"]):
        raise HTTPException(409, detail={"code": "CULTURAL_REQUIREMENT_USER_MISMATCH"})
    if not isinstance(cultural.get("cultural_evidence_signature"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", cultural["cultural_evidence_signature"]):
        raise HTTPException(503, detail={"code": "CULTURAL_EVIDENCE_UNSIGNED"})
    usi_raw = profile.get("usi_profile")
    if (not isinstance(usi_raw, dict) or usi_raw.get("user_id") != user_id
            or not isinstance(usi_raw.get("preferences"), list) or not usi_raw["preferences"]
            or any(not isinstance(item, dict) or item.get("user_id") != user_id for item in usi_raw["preferences"])):
        raise HTTPException(503, detail={"code": "USI_PROFILE_MISSING_OR_MISMATCHED"})
    # Strip persistence metadata; the canonical decision contract accepts only
    # the strict USIProfileIn fields.
    usi = {key: usi_raw[key] for key in ("profile_id", "user_id", "version", "preferences") if key in usi_raw}
    if (context.get("user_id") != user_id or not isinstance(context.get("context"), dict)
            or context["context"].get("user_id") != user_id):
        raise HTTPException(409, detail={"code": "USER_CONTEXT_MISSING_OR_MISMATCHED"})
    raw_context = context["context"]
    decision_context = {key: raw_context.get(key) for key in ("user_id", "age_years", "location", "occasion", "climate")}
    if (policy_evidence.get("request_id") != request_id or policy_evidence.get("user_id") != user_id
            or policy_evidence.get("candidate_id") != candidate_id
            or policy_evidence.get("catalog_product_id") != catalog_product_id):
        raise HTTPException(409, detail={"code": "POLICY_EVIDENCE_BINDING_MISMATCH"})
    upstream_signals = policy_evidence.get("upstream_signals")
    if not isinstance(upstream_signals, list):
        raise HTTPException(503, detail={"code": "POLICY_EVIDENCE_MISSING"})
    policy_signature = policy_evidence.get("policy_evidence_signature")
    if not isinstance(policy_signature, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", policy_signature):
        raise HTTPException(503, detail={"code": "POLICY_EVIDENCE_UNSIGNED"})
    try:
        canonical_policy = _canonical_policy_evidence(
            request_id, user_id, candidate_id, catalog_product_id, candidate_attributes, fit_context, upstream_signals
        )
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "POLICY_EVIDENCE_INVALID"}) from exc
    policy_secret = _token("POLICY_EVIDENCE_HMAC_SECRET")
    expected_policy_signature = hmac.new(policy_secret.encode("utf-8"), canonical_policy, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_policy_signature, policy_signature.lower()):
        raise HTTPException(401, detail={"code": "POLICY_EVIDENCE_SIGNATURE_INVALID"})
    estimate, signature = fit.get("fit_estimate"), fit.get("fit_estimate_signature")
    if not isinstance(estimate, dict) or estimate.get("user_id") != user_id or estimate.get("candidate_id") != candidate_id:
        raise HTTPException(409, detail={"code": "FIT_EVIDENCE_BINDING_MISMATCH"})
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        raise HTTPException(503, detail={"code": "FIT_EVIDENCE_UNSIGNED"})
    eepl_policy = profile.get("eepl_policy")
    if not isinstance(eepl_policy, dict):
        raise HTTPException(503, detail={"code": "EEPL_POLICY_MISSING"})
    decision_request = {
        "request_id": request_id, "candidate_id": candidate_id, "context": decision_context,
        "eepl_policy": eepl_policy, "usi_profile": usi, "candidate_attributes": candidate_attributes,
        "candidate_attributes_complete": True, "negative_preferences": npl.get("negative_preferences"),
        "cultural_requirements": cultural.get("cultural_requirements"),
        "cultural_evidence_signature": cultural["cultural_evidence_signature"],
        "fit_estimate": estimate, "fit_estimate_signature": signature,
        "npl_evidence_signature": npl["npl_evidence_signature"],
        "upstream_signals": upstream_signals,
        "policy_version": "decision-pipeline-1.0.0",
        "minimum_fit_confidence": 0.70, "minimum_alignment_score": 0.60,
    }
    issued = now()
    return {
        "request_id": request_id, "subject_id": user_id, "candidate_id": candidate_id,
        "catalog_product_id": catalog_product_id,
        "issued_at": iso(issued), "expires_at": iso(issued + timedelta(seconds=45)),
        "evidence_freshness": {
            "npl_loaded_at": npl_loaded_at, "cultural_requirements_loaded_at": cultural_loaded_at,
            "fit_estimate_generated_at": fit_generated_at, "candidate_attributes_loaded_at": catalog_loaded_at,
            "usi_profile_loaded_at": usi_loaded_at, "user_context_loaded_at": context_loaded_at,
            "policy_evidence_loaded_at": policy_loaded_at,
        },
        "decision_request": decision_request,
    }

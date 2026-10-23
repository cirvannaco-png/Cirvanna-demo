"""Authenticated, fail-closed evidence assembler for candidate-bound CAL decisions.

This service assembles evidence only from trusted internal services. It does not
invent user preferences, cultural requirements, context, catalog attributes, or
fit estimates. Missing providers and malformed/stale/mismatched evidence fail closed.
"""
from __future__ import annotations

import hmac
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


@app.get("/ready")
def readiness() -> dict[str, Any]:
    keys = ("EVIDENCE_PROVIDER_TOKEN", "NPL_SERVICE_TOKEN", "CULTURAL_IDENTITY_SERVICE_TOKEN", "CATALOG_API_TOKEN", "USI_PROFILE_API_TOKEN", "USER_CONTEXT_API_TOKEN", "FIT_EVIDENCE_API_TOKEN")
    urls = ("NPL_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_URL", "CATALOG_API_URL", "USI_PROFILE_API_URL", "USER_CONTEXT_API_URL", "FIT_EVIDENCE_API_URL")
    configured = {key: len(os.getenv(key, "").encode("utf-8")) >= 32 for key in keys}
    for key in urls:
        try:
            _base(key)
            configured[key] = True
        except HTTPException:
            configured[key] = False
    ready = all(configured.values())
    result = {"service": SERVICE, "ready": ready, "configured": configured, "fci_model_available": False}
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
    if not UUID_RE.fullmatch(payload.candidate_id):
        raise HTTPException(422, detail={"code": "CANONICAL_CATALOG_PRODUCT_ID_REQUIRED"})

    request_id, user_id, candidate_id = payload.request_id, payload.subject_id, payload.candidate_id
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=2), trust_env=False, follow_redirects=False) as client:
        product = await _request(client, "CATALOG_API_URL", "CATALOG_API_TOKEN", "GET", "/products/" + quote(candidate_id, safe=""))
        if product.get("product_id", product.get("id")) != candidate_id or product.get("status") != "active":
            raise HTTPException(409, detail={"code": "CATALOG_CANDIDATE_MISMATCH_OR_INACTIVE"})
        candidate_attributes = _attrs(product)
        catalog_loaded_at = iso()

        common = {"request_id": request_id, "user_id": user_id, "candidate_id": candidate_id, "candidate_attributes": candidate_attributes}
        npl = await _request(client, "NPL_SERVICE_URL", "NPL_SERVICE_TOKEN", "POST", "/v1/evaluate", common)
        npl_loaded_at = iso()
        cultural = await _request(client, "CULTURAL_IDENTITY_SERVICE_URL", "CULTURAL_IDENTITY_SERVICE_TOKEN", "POST", "/v1/evaluate", {**common, "candidate_attributes_complete": True})
        cultural_loaded_at = iso()
        profile = await _request(client, "USI_PROFILE_API_URL", "USI_PROFILE_API_TOKEN", "GET", "/v1/profiles/" + quote(user_id, safe=""))
        context = await _request(client, "USER_CONTEXT_API_URL", "USER_CONTEXT_API_TOKEN", "GET", "/v1/context/" + quote(user_id, safe=""))
        fit = await _request(client, "FIT_EVIDENCE_API_URL", "FIT_EVIDENCE_API_TOKEN", "POST", "/v1/estimate", {**common, "context": context.get("context")})
        fit_generated_at = _fresh_timestamp(fit.get("generated_at"))

    for source, data in (("npl", npl), ("cultural", cultural)):
        if data.get("request_id") != request_id or data.get("user_id") != user_id or data.get("candidate_id") != candidate_id:
            raise HTTPException(409, detail={"code": "EVIDENCE_BINDING_MISMATCH", "source": source})
    if not isinstance(npl.get("npl_evidence_signature"), str) or len(npl["npl_evidence_signature"]) != 64:
        raise HTTPException(503, detail={"code": "NPL_EVIDENCE_UNSIGNED"})
    if not isinstance(cultural.get("cultural_evidence_signature"), str) or len(cultural["cultural_evidence_signature"]) != 64:
        raise HTTPException(503, detail={"code": "CULTURAL_EVIDENCE_UNSIGNED"})
    usi = profile.get("usi_profile")
    if not isinstance(usi, dict) or usi.get("user_id") != user_id or not isinstance(usi.get("preferences"), list) or not usi["preferences"]:
        raise HTTPException(503, detail={"code": "USI_PROFILE_MISSING_OR_MISMATCHED"})
    if (context.get("user_id") != user_id or not isinstance(context.get("context"), dict)
            or context["context"].get("user_id") != user_id):
        raise HTTPException(409, detail={"code": "USER_CONTEXT_MISSING_OR_MISMATCHED"})
    estimate, signature = fit.get("fit_estimate"), fit.get("fit_estimate_signature")
    if not isinstance(estimate, dict) or estimate.get("user_id") != user_id or estimate.get("candidate_id") != candidate_id:
        raise HTTPException(409, detail={"code": "FIT_EVIDENCE_BINDING_MISMATCH"})
    if not isinstance(signature, str) or len(signature) != 64:
        raise HTTPException(503, detail={"code": "FIT_EVIDENCE_UNSIGNED"})
    policy = profile.get("eepl_policy")
    if not isinstance(policy, dict):
        raise HTTPException(503, detail={"code": "EEPL_POLICY_MISSING"})
    decision_request = {
        "request_id": request_id, "candidate_id": candidate_id, "context": context["context"],
        "eepl_policy": policy, "usi_profile": usi, "candidate_attributes": candidate_attributes,
        "candidate_attributes_complete": True, "negative_preferences": npl.get("negative_preferences"),
        "cultural_requirements": cultural.get("cultural_requirements"),
        "cultural_evidence_signature": cultural["cultural_evidence_signature"],
        "fit_estimate": estimate, "fit_estimate_signature": signature,
        "npl_evidence_signature": npl["npl_evidence_signature"],
        "policy_version": "decision-pipeline-1.0.0",
        "minimum_fit_confidence": 0.70, "minimum_alignment_score": 0.60,
    }
    issued = now()
    return {
        "request_id": request_id, "subject_id": user_id, "candidate_id": candidate_id,
        "issued_at": iso(issued), "expires_at": iso(issued + timedelta(seconds=45)),
        "evidence_freshness": {
            "npl_loaded_at": npl_loaded_at, "cultural_requirements_loaded_at": cultural_loaded_at,
            "fit_estimate_generated_at": fit_generated_at, "candidate_attributes_loaded_at": catalog_loaded_at,
        },
        "decision_request": decision_request,
    }

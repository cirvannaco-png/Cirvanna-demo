"""PNELLY conversational discovery, Look It and capability routing.

DermalSight is an optional non-diagnostic skin-analysis capability within
PNELLY. Click It remains an independent marketplace service and API.
"""
from __future__ import annotations

import hmac
import os
import httpx
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from xari.routing import ROUTES, plan_route

SERVICE = "cirvanna-pnelly"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna PNELLY API",
    version="0.1.0",
    description="PNELLY conversational discovery, Look It and DermalSight capability routing.",
)

def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("PNELLY_API_TOKEN", "").strip() or os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32 or credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Valid Xari bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid Xari bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

class MarketplaceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=25)

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split()).strip()


def _marketplace_search_config() -> tuple[str, str] | None:
    raw = os.getenv("VISION_INTELLIGENCE_API_URL", "").strip().rstrip("/")
    token = os.getenv("VISION_INTELLIGENCE_API_TOKEN", "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        return None
    return raw, token


async def _execute_marketplace_search(payload: MarketplaceSearchRequest) -> dict[str, object]:
    config = _marketplace_search_config()
    if config is None:
        raise HTTPException(503, detail={"code": "MARKETPLACE_SEARCH_NOT_CONFIGURED"})
    base, token = config
    body: dict[str, object] = {"query": payload.normalized_query, "limit": payload.limit}
    if payload.category and payload.category.strip():
        body["category"] = payload.category.strip()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/v1/search/text",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "MARKETPLACE_SEARCH_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "MARKETPLACE_SEARCH_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        if response.status_code in {400, 413, 415, 422}:
            raise HTTPException(response.status_code, detail={"code": "MARKETPLACE_SEARCH_REQUEST_REJECTED"})
        if response.status_code in {502, 503, 504}:
            raise HTTPException(503, detail={"code": "MARKETPLACE_SEARCH_UNAVAILABLE"})
        raise HTTPException(502, detail={"code": "MARKETPLACE_SEARCH_FAILED"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "MARKETPLACE_SEARCH_INVALID_RESPONSE"}) from exc
    if (
        not isinstance(result, dict)
        or result.get("status") != "complete"
        or not isinstance(result.get("results"), list)
        or not isinstance(result.get("candidate_count"), int)
    ):
        raise HTTPException(502, detail={"code": "MARKETPLACE_SEARCH_INVALID_RESPONSE"})
    return result


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=3, max_length=128)
    intent: Literal[
        "assistant_chat", "skin_analysis", "marketplace_search", "look_it",
        "virtual_try_on", "virtual_twin", "wardrobe",
    ]
    consents: dict[str, bool] = Field(default_factory=dict)

@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}

@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, object]:
    token = os.getenv("PNELLY_API_TOKEN", "").strip() or os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
    token_configured = len(token.encode("utf-8")) >= 32
    search_configured = _marketplace_search_config() is not None
    result = {
        "status": "ready" if token_configured else "not_ready",
        "service": SERVICE,
        "api_authentication_configured": token_configured,
        "marketplace_search_adapter_configured": search_configured,
        "execution_adapters_enabled": search_configured,
        "ready": token_configured,
    }
    if not token_configured:
        raise HTTPException(status_code=503, detail=result)
    return result

@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    return {
        "service": SERVICE,
        "contract_version": "1.0.0",
        "canonical_name": "PNELLY",
        "legacy_names": ["Xari", "Tari", "Xyra"],
        "dermalsight": {"parent_capability": "PNELLY", "service": "DermalSight", "non_diagnostic": True, "execution_enabled": False, "consent_required": True},
        "execution_enabled": _marketplace_search_config() is not None,
        "marketplace_description_search": {
            "implemented": True,
            "configured": _marketplace_search_config() is not None,
            "endpoint": "POST /v1/marketplace/search",
            "returns_candidate_results_only": True,
            "cal_authorization_required_before_display": True,
        },
        "capabilities": {
            route.intent: {
                "required_consents": list(route.required_consents),
                "route_planning": True,
                "execution": False,
                "upstream_env": route.upstream_env,
            }
            for route in ROUTES.values()
        },
        "reason": "validated_execution_adapters_not_integrated",
    }

@app.post("/v1/route", tags=["routing"], dependencies=[Depends(require_api_token)])
def route(request: RouteRequest) -> dict[str, object]:
    try:
        plan = plan_route(request.intent, request.consents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ROUTE_REQUEST"}) from exc
    return {
        "request_id": request.request_id,
        "contract_version": plan.contract_version,
        "intent": plan.intent,
        "capability": plan.capability,
        "status": plan.status,
        "code": plan.code,
        "missing_consents": list(plan.missing_consents),
        "upstream_configured": plan.configured,
        "execution_supported": plan.execution_supported,
        "detail": (
            "This endpoint plans routing only; it does not execute or claim completion."
        ),
    }

@app.post(
    "/v1/marketplace/search",
    tags=["marketplace"],
    dependencies=[Depends(require_api_token)],
)
async def marketplace_search(request: MarketplaceSearchRequest) -> dict[str, object]:
    """Search active marketplace candidates using a natural-language description.

    Similarity ranks are not probabilities, and this endpoint is not CAL approval.
    Returned candidates must pass NPL/cultural constraints and CAL before display.
    """
    result = await _execute_marketplace_search(request)
    candidates = result.pop("results", [])
    return {
        "status": "complete",
        "query": request.normalized_query,
        "candidate_count": result.get("candidate_count", len(candidates)),
        "candidates": candidates,
        "catalog_truncated": result.get("catalog_truncated", False),
        "model": result.get("model"),
        "scores_are_probabilities": False,
        "display_authorized": False,
        "decision_status": "PENDING_CAL",
        "decision_notice": "Search candidates require NPL hard-veto, cultural-identity and CAL checks before display or purchase.",
        "provenance": "live_Cirvanna_marketplace_search",
    }


# Look It is a PNELLY conversational image-search capability. It has its own
# consent scope and endpoint; it never invokes or aliases the independent Click It API.
LOOK_IT_MAX_IMAGE_BYTES = 10 * 1024 * 1024
LOOK_IT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

def _look_it_consent_config() -> tuple[str, str] | None:
    raw = os.getenv("CONSENT_API_URL", "").strip().rstrip("/")
    token = os.getenv("CONSENT_API_TOKEN", "").strip()
    if not raw or len(token.encode('utf-8')) < 32:
        return None
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))):
        return None
    return raw, token

async def _verify_look_it_consent(subject_id: str, consent_id: str) -> None:
    config = _look_it_consent_config()
    if config is None:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_PROVIDER_NOT_CONFIGURED"})
    base, token = config
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = await client.post(base + "/internal/v1/consents/verify",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={"subject_id": subject_id, "consent_id": consent_id, "required_scopes": ["image_processing", "look_it"]})
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "LOOK_IT_CONSENT_VERIFICATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_VERIFIER_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "LOOK_IT_CONSENT_NOT_VERIFIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_VERIFIER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "LOOK_IT_CONSENT_INVALID_RESPONSE"}) from exc
    scopes = receipt.get("granted_scopes") if isinstance(receipt, dict) else None
    if not (isinstance(receipt, dict) and receipt.get('verified') is True and receipt.get('active') is True
        and receipt.get('subject_id') == subject_id and receipt.get('consent_id') == consent_id
        and isinstance(scopes, list) and {'image_processing', 'look_it'}.issubset(set(scopes))):
        raise HTTPException(403, detail={"code": "LOOK_IT_CONSENT_NOT_VERIFIED"})

async def _execute_marketplace_image_search(*, data: bytes, filename: str, content_type: str, category: str | None, limit: int) -> dict[str, object]:
    config = _marketplace_search_config()
    if config is None:
        raise HTTPException(503, detail={"code": "MARKETPLACE_SEARCH_NOT_CONFIGURED"})
    base, token = config
    fields = {"consent_image_processing": "true", "consent_look_it": "true", "limit": str(limit)}
    if category and category.strip():
        fields["category"] = category.strip()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=2.0), trust_env=False, follow_redirects=False) as client:
            response = await client.post(base + "/v1/search/image",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, data=fields,
                files={"image": (filename or "look-it-reference", data, content_type)})
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "LOOK_IT_SEARCH_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "LOOK_IT_SEARCH_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        detail = {}
        try:
            payload = response.json().get("detail", {})
            detail = payload if isinstance(payload, dict) else {}
        except (ValueError, AttributeError):
            pass
        code = detail.get("code") if isinstance(detail.get("code"), str) else "LOOK_IT_SEARCH_FAILED"
        if response.status_code in {400, 403, 413, 415, 422}:
            raise HTTPException(response.status_code, detail={"code": code})
        raise HTTPException(503 if response.status_code in {502, 503, 504} else 502, detail={"code": code})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "LOOK_IT_INVALID_RESPONSE"}) from exc
    if not isinstance(result, dict) or result.get("status") != "complete" or not isinstance(result.get("results"), list):
        raise HTTPException(502, detail={"code": "LOOK_IT_INVALID_RESPONSE"})
    return result

@app.post("/v1/marketplace/search/image", tags=["look-it"], dependencies=[Depends(require_api_token)])
async def look_it_image_search(
    subject_id: Annotated[str, Form(min_length=3, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=160)],
    consent_image_processing: Annotated[bool, Form()],
    consent_look_it: Annotated[bool, Form()],
    image: Annotated[UploadFile, File()],
    category: Annotated[str | None, Form()] = None,
    limit: Annotated[int, Form(ge=1, le=25)] = 10,
) -> dict[str, object]:
    """Search a visual reference within PNELLY; this is not the Click It API."""
    try:
        if not consent_image_processing or not consent_look_it:
            raise HTTPException(403, detail={"code": "EXPLICIT_LOOK_IT_CONSENT_REQUIRED"})
        if image.content_type not in LOOK_IT_MIME_TYPES:
            raise HTTPException(415, detail={"code": "UNSUPPORTED_LOOK_IT_IMAGE_TYPE"})
        if image.size is not None and image.size > LOOK_IT_MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "LOOK_IT_IMAGE_SIZE_LIMIT_EXCEEDED"})
        await _verify_look_it_consent(subject_id.strip(), consent_id.strip())
        data = await image.read(LOOK_IT_MAX_IMAGE_BYTES + 1)
        if not data:
            raise HTTPException(400, detail={"code": "EMPTY_LOOK_IT_IMAGE"})
        if len(data) > LOOK_IT_MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "LOOK_IT_IMAGE_SIZE_LIMIT_EXCEEDED"})
        result = await _execute_marketplace_image_search(data=data, filename=image.filename or 'look-it-reference',
            content_type=image.content_type or 'application/octet-stream', category=category, limit=limit)
        candidates = result.get("results", [])
        return {
            "status": "complete", "search_mode": "pnelly_look_it_image_to_catalog_text_similarity",
            "candidate_count": len(candidates), "candidates": candidates,
            "catalog_truncated": result.get("catalog_truncated", False), "model": result.get("model"),
            "image_persisted": False, "scores_are_probabilities": False, "display_authorized": False,
            "decision_status": "PENDING_CAL",
            "outfit_decomposition": result.get("outfit_decomposition", {"status": "unavailable", "reason": "VALIDATED_OUTFIT_DECOMPOSITION_MODEL_NOT_CONFIGURED", "components": []}),
            "merchant_comparison": result.get("merchant_comparison", {"status": "unavailable", "reason": "CANONICAL_VARIANT_ID_AND_OFFER_OBSERVATION_TIMESTAMP_REQUIRED"}),
            "notice": "Image similarity is not a probability or fit guarantee. Candidates remain hidden until NPL, explicit cultural requirements and CAL SHOW are verified.",
        }
    finally:
        await image.close()

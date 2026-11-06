"""Authenticated Xari route planning and marketplace-description search.

The dedicated marketplace-search endpoint executes the private model-backed
retrieval adapter; candidates still require NPL/cultural constraints and CAL.
Other intents remain route-plan-only until their execution adapters are integrated.
"""
from __future__ import annotations

import hmac
import os
import httpx
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from xari.routing import ROUTES, plan_route

SERVICE = "cirvanna-pnelly"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna PNELLY API",
    version="0.1.0",
    description="PNELLY orchestration with backward-compatible Xari route and marketplace-search contracts.",
)

def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("PNELLY_API_TOKEN", "").strip() or os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32 or credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Valid PNELLY bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid PNELLY bearer token.",
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
        "assistant_chat", "skin_analysis", "marketplace_search",
        "virtual_try_on", "virtual_twin", "wardrobe", "click_it",
    ]
    consents: dict[str, bool] = Field(default_factory=dict)

@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}

@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, object]:
    token = os.getenv("XARI_API_TOKEN", "").strip() or os.getenv("TARI_API_TOKEN", "").strip()
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
        "contract_compatibility": {"xari_routes_preserved": True, "route_contract_version": "1.0.0"},
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


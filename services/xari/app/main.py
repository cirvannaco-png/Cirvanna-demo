"""Guarded Xari API: authenticate requests and produce consent-aware route plans.

This API does not run chat, visual analysis, try-on, twin generation, or Click It.
It intentionally returns route plans only until validated execution adapters exist.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from xari.routing import ROUTES, plan_route

SERVICE = "cirvanna-xari"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Xari API",
    version="0.1.0",
    description="Authenticated, consent-aware routing contract; execution adapters are not enabled.",
)

def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("XARI_API_TOKEN", "")
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
    token_configured = len(os.getenv("XARI_API_TOKEN", "").encode("utf-8")) >= 32
    result = {
        "status": "ready" if token_configured else "not_ready",
        "service": SERVICE,
        "api_authentication_configured": token_configured,
        "execution_adapters_enabled": False,
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
        "canonical_name": "Xari",
        "legacy_names": ["Tari", "Xyra"],
        "execution_enabled": False,
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
    plan = plan_route(request.intent, request.consents)
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

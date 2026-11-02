"""Authenticated API boundary for Cirvanna Complementer and intelligence contracts."""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.complementer import compose_complementary_look
from app.personal_aesthetic import compose_personal_aesthetic
from app.product_intelligence import evaluate_product_intelligence
from app.skin_scenario import build_skin_scenario_preview
from app.preference_feedback import build_preference_feedback_event
from app.contracts_v2 import (
    PersonalRecommendationRequest,
    ProductIntelligenceRequest,
    SkinScenarioRequest,
    PreferenceFeedbackRequest,
)

SERVICE = "cirvanna-complementer-agent"
VERSION = "0.2.0"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Complementer Agent",
    version=VERSION,
    description=(
        "Preference-led personal aesthetic composition and provenance-aware product "
        "intelligence contracts. Advice is non-authoritative."
    ),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreferencesIn(StrictModel):
    aesthetics: list[Literal["minimalist", "classic", "romantic", "bold", "bohemian", "streetwear", "editorial", "natural"]] = Field(default_factory=list, max_length=8)
    favorite_colors: list[str] = Field(default_factory=list, max_length=12)
    avoid_colors: list[str] = Field(default_factory=list, max_length=12)
    favorite_fragrance_families: list[Literal["fresh", "citrus", "floral", "woody", "amber", "gourmand", "aquatic", "spicy", "green", "musk"]] = Field(default_factory=list, max_length=10)
    fragrance_sensitive: bool = False
    fragrance_free: bool = False
    fragrance_intensity: Literal["light", "moderate", "bold"] | None = None
    earrings_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_earring_shapes: list[Literal["stud", "huggie", "hoop", "drop", "geometric", "statement", "slim drop", "small hoop", "compact hoop", "sculptural statement"]] = Field(default_factory=list, max_length=8)
    preferred_metals: list[Literal["gold", "silver", "rose_gold", "mixed"]] = Field(default_factory=list, max_length=4)

    @field_validator("favorite_colors", "avoid_colors")
    @classmethod
    def validate_color_labels(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 32 for value in cleaned):
            raise ValueError("color labels must be non-empty and at most 32 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("color labels must be unique")
        return cleaned


class LookIn(StrictModel):
    outfit_colors: list[str] = Field(default_factory=list, max_length=8)
    neckline: Literal["high", "crew", "collared", "v_neck", "strapless", "off_shoulder", "scoop", "unknown"] = "unknown"
    hairstyle: Literal["up", "down", "short", "braids", "locs", "protected_style", "unknown"] = "unknown"
    climate: Literal["hot_humid", "hot_dry", "cool", "temperate", "unknown"] = "unknown"
    occasion: str | None = Field(default=None, max_length=80)

    @field_validator("outfit_colors")
    @classmethod
    def validate_outfit_colors(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 32 for value in cleaned):
            raise ValueError("outfit color labels must be non-empty and at most 32 characters")
        return cleaned


class RecommendationRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    preferences: PreferencesIn
    look: LookIn = Field(default_factory=LookIn)

    @field_validator("request_id", "user_id")
    @classmethod
    def trim_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be blank")
        return value


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("COMPLEMENTER_SERVICE_TOKEN", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "COMPLEMENTER_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail="Valid internal bearer authentication is required.", headers={"WWW-Authenticate": "Bearer"})


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE, "version": VERSION}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, object]:
    token_ready = len(os.getenv("COMPLEMENTER_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    result = {
        "status": "ready" if token_ready else "not_ready",
        "service": SERVICE,
        "api_authentication_configured": token_ready,
        "ready": token_ready,
    }
    if not token_ready:
        raise HTTPException(503, detail=result)
    return result


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    return {
        "service": SERVICE,
        "complementer_v1_advisory": True,
        "personal_aesthetic_v2_contract": True,
        "product_intelligence_contract": True,
        "preference_feedback_event_contract": True,
        "profile_persistence_connected": False,
        "catalog_integration_connected": False,
        "skin_forecast_provider_validated": False,
        "skin_scenario_contract": True,
        "cal_display_authority": "external_CaTaCaCi_CAL",
    }


@app.post(
    "/v1/complementer/recommend",
    tags=["complementer"],
    dependencies=[Depends(require_internal_token)],
)
def recommend(request: RecommendationRequest) -> dict[str, object]:
    return compose_complementary_look(request.model_dump())


@app.post(
    "/v2/complementer/compose",
    tags=["complementer"],
    dependencies=[Depends(require_internal_token)],
)
def compose_personal_look(request: PersonalRecommendationRequest) -> dict[str, object]:
    """Coordinate fragrance, colour, jewellery and finishing details without identity replacement."""
    return compose_personal_aesthetic(request.model_dump())


@app.post(
    "/v1/marketplace/product-intelligence/evaluate",
    tags=["product-intelligence"],
    dependencies=[Depends(require_internal_token)],
)
def evaluate_product(request: ProductIntelligenceRequest) -> dict[str, object]:
    """Return dimension-level evidence matches; this is not ranking or display authorization."""
    return evaluate_product_intelligence(
        request.product.model_dump(),
        request.profile.model_dump(),
        now=datetime.now(timezone.utc),
    )


@app.post(
    "/v1/skin-state/scenario",
    tags=["skin-scenario"],
    dependencies=[Depends(require_internal_token)],
)
def skin_scenario(request: SkinScenarioRequest) -> dict[str, object]:
    """Return a scenario definition only until a validated longitudinal model is configured."""
    if not request.consent:
        raise HTTPException(403, detail={"code": "SKIN_SCENARIO_CONSENT_REQUIRED"})
    try:
        return build_skin_scenario_preview(request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_SKIN_SCENARIO", "message": str(exc)}) from exc


@app.post(
    "/v1/complementer/feedback",
    tags=["preference-learning"],
    dependencies=[Depends(require_internal_token)],
)
def preference_feedback(request: PreferenceFeedbackRequest) -> dict[str, object]:
    """Return a feedback event proposal; durable USI/TAL/NPL persistence is not yet connected."""
    try:
        return build_preference_feedback_event(request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_PREFERENCE_FEEDBACK", "message": str(exc)}) from exc

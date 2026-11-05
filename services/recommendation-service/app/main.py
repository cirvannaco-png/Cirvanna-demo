"""Authenticated API boundary for Cirvanna's Complementer advisory agent."""
from __future__ import annotations

import hmac
import os
import re
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.complementer import compose_complementary_look
from app.daily_looks import build_daily_looks
from app.intelligence.learning import build_learning_event

SERVICE = "cirvanna-complementer-agent"
VERSION = "0.2.0"
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Complementer Agent",
    version=VERSION,
    description=(
        "Preference-led personal aesthetic intelligence for fragrance, colour, "
        "jewellery, accessories and look completion. Advisory only."
    ),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreferencesIn(StrictModel):
    aesthetics: list[Literal[
        "minimalist", "elegant", "classic", "romantic", "bold",
        "bohemian", "streetwear", "editorial", "natural", "cultural"
    ]] = Field(default_factory=list, max_length=10)
    cultural_contexts: list[str] = Field(default_factory=list, max_length=8)

    favorite_colors: list[str] = Field(default_factory=list, max_length=12)
    avoid_colors: list[str] = Field(default_factory=list, max_length=12)
    favorite_makeup_colors: list[str] = Field(default_factory=list, max_length=12)
    favorite_jewellery_colors: list[str] = Field(default_factory=list, max_length=12)
    favorite_accessory_colors: list[str] = Field(default_factory=list, max_length=12)

    favorite_fragrance_families: list[Literal[
        "fresh", "citrus", "floral", "woody", "amber", "gourmand",
        "aquatic", "spicy", "green", "musk", "fruity", "chypre"
    ]] = Field(default_factory=list, max_length=12)
    preferred_scent_profiles: list[Literal[
        "fresh", "powdery", "woody", "warm", "sweet", "clean",
        "spicy", "green", "aquatic", "smoky"
    ]] = Field(default_factory=list, max_length=10)
    fragrance_sensitive: bool = False
    fragrance_free: bool = False
    fragrance_intensity: Literal["light", "moderate", "bold"] | None = None
    fragrance_longevity: Literal["short", "moderate", "long", "any"] = "any"
    fragrance_occasions: list[Literal[
        "daily", "work", "evening", "formal", "date", "travel", "sport", "special_occasion"
    ]] = Field(default_factory=list, max_length=8)
    fragrance_budget_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    fragrance_budget_currency: str | None = Field(default=None, min_length=3, max_length=3)

    earrings_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_earring_shapes: list[Literal[
        "stud", "huggie", "hoop", "drop", "geometric", "statement",
        "slim drop", "small hoop", "compact hoop", "sculptural statement"
    ]] = Field(default_factory=list, max_length=8)
    preferred_metals: list[Literal["gold", "silver", "rose_gold", "mixed"]] = Field(default_factory=list, max_length=4)

    necklace_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_necklace_styles: list[Literal[
        "chain", "pendant", "collar", "choker", "layered", "statement"
    ]] = Field(default_factory=list, max_length=8)
    glasses_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_glasses_shapes: list[Literal[
        "round", "square", "cat_eye", "rectangular", "oval", "aviator", "geometric", "oversized"
    ]] = Field(default_factory=list, max_length=8)
    self_reported_face_shape: Literal["round", "square", "oval", "heart", "oblong"] | None = None
    preferred_accessories: list[Literal["scarf", "belt", "bag", "watch", "hair_accessory", "brooch"]] = Field(default_factory=list, max_length=8)
    avoid_accessory_categories: list[Literal["scarf", "belt", "bag", "watch", "hair_accessory", "brooch"]] = Field(default_factory=list, max_length=8)

    @field_validator(
        "favorite_colors", "avoid_colors", "favorite_makeup_colors",
        "favorite_jewellery_colors", "favorite_accessory_colors", "cultural_contexts",
    )
    @classmethod
    def validate_labels(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 64 for value in cleaned):
            raise ValueError("preference labels must be non-empty and at most 64 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("preference labels must be unique")
        return cleaned

    @field_validator("fragrance_budget_currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not CURRENCY_PATTERN.fullmatch(normalized):
            raise ValueError("currency must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def validate_budget_pair(self) -> "PreferencesIn":
        if self.fragrance_budget_minor is not None and self.fragrance_budget_currency is None:
            raise ValueError("fragrance_budget_currency is required when a fragrance budget is set")
        if self.fragrance_budget_minor is None and self.fragrance_budget_currency is not None:
            raise ValueError("fragrance budget currency cannot be set without a budget")
        return self


class LookIn(StrictModel):
    outfit_colors: list[str] = Field(default_factory=list, max_length=8)
    makeup_colors: list[str] = Field(default_factory=list, max_length=8)
    jewellery_colors: list[str] = Field(default_factory=list, max_length=8)
    accessory_colors: list[str] = Field(default_factory=list, max_length=8)
    jewellery_current_style: str | None = Field(default=None, max_length=80)
    neckline: Literal["high", "crew", "collared", "v_neck", "strapless", "off_shoulder", "scoop", "unknown"] = "unknown"
    hairstyle: Literal["up", "down", "short", "braids", "locs", "protected_style", "unknown"] = "unknown"
    climate: Literal["hot_humid", "hot_dry", "cool", "temperate", "unknown"] = "unknown"
    occasion: str | None = Field(default=None, max_length=80)

    @field_validator("outfit_colors", "makeup_colors", "jewellery_colors", "accessory_colors")
    @classmethod
    def validate_look_colors(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 32 for value in cleaned):
            raise ValueError("look colour labels must be non-empty and at most 32 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("look colour labels must be unique")
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


class WardrobeItemForDailyLook(StrictModel):
    item_id: str = Field(min_length=3, max_length=128)
    owner_user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    attributes: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["draft", "active", "archived", "deleted"]


class TariDailyLooksRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    local_date: str = Field(min_length=10, max_length=10)
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=80)
    wardrobe_items: list[WardrobeItemForDailyLook] = Field(max_length=150)
    style_signals: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("request_id", "user_id")
    @classmethod
    def trim_daily_look_identifiers(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier must not be blank")
        return cleaned

    @field_validator("local_date")
    @classmethod
    def valid_local_date(cls, value: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("local_date must be an ISO calendar date") from exc
        return value


class FeedbackRequest(StrictModel):
    feedback_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    recommendation_id: str = Field(min_length=1, max_length=128)
    category: Literal["colour", "fragrance", "earrings", "necklaces", "glasses", "aesthetic", "look_completion", "other"]
    outcome: Literal["approved", "rejected"]
    consent_to_personalization: bool = False
    preference_action: Literal["observe_only", "save_preference"] = "observe_only"
    preference_value: str | None = Field(default=None, max_length=160)
    reason_code: str | None = Field(default=None, max_length=80)

    @field_validator("feedback_id", "user_id", "recommendation_id")
    @classmethod
    def trim_feedback_ids(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be blank")
        return value

    @model_validator(mode="after")
    def validate_explicit_learning(self) -> "FeedbackRequest":
        if self.preference_action == "save_preference" and not self.preference_value:
            raise ValueError("preference_value is required to save a preference")
        if self.preference_value is not None:
            self.preference_value = self.preference_value.strip()
            if not self.preference_value:
                raise ValueError("preference_value must not be blank")
        return self


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
        "durable_personal_memory_configured": False,
        "catalog_product_retrieval_configured": False,
        "ready": token_ready,
    }
    if not token_ready:
        raise HTTPException(503, detail=result)
    return result


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    return {
        "service": SERVICE,
        "fragrance_direction": True,
        "colour_coordination": True,
        "jewellery_and_accessories": True,
        "aesthetic_direction": True,
        "look_completion": True,
        "tari_daily_look_orchestration": True,
        "tari_daily_look_roles": ["everyday", "elevated", "explore"],
        "virtual_twin_preview_enabled": False,
        "feedback_event_contract": True,
        "durable_personal_memory": False,
        "catalog_product_intelligence_integration": False,
        "causal_skin_state_forecasting": False,
        "product_display_authority": "CaTaCaCi/CAL",
    }


@app.post(
    "/v1/complementer/recommend",
    tags=["complementer"],
    dependencies=[Depends(require_internal_token)],
)
def recommend(request: RecommendationRequest) -> dict[str, object]:
    return compose_complementary_look(request.model_dump())


@app.post(
    "/v1/tari/daily-looks",
    tags=["tari daily looks"],
    dependencies=[Depends(require_internal_token)],
)
def tari_daily_looks(request: TariDailyLooksRequest) -> dict[str, object]:
    """Compose exactly three role slots from an authenticated BFF's wardrobe snapshot."""
    try:
        return build_daily_looks(
            request_id=request.request_id,
            user_id=request.user_id,
            wardrobe_items=[item.model_dump() for item in request.wardrobe_items],
            local_date=request.local_date,
            occasion=request.occasion,
            climate=request.climate,
            style_signals=request.style_signals,
        )
    except PermissionError as exc:
        raise HTTPException(403, detail={"code": "WARDROBE_SUBJECT_MISMATCH"}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_DAILY_LOOK_REQUEST"}) from exc


@app.post(
    "/v1/complementer/feedback",
    tags=["learning"],
    dependencies=[Depends(require_internal_token)],
)
def feedback(request: FeedbackRequest) -> dict[str, object]:
    if not request.consent_to_personalization:
        raise HTTPException(400, detail={"code": "EXPLICIT_PERSONALIZATION_CONSENT_REQUIRED"})
    try:
        event = build_learning_event(request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_LEARNING_EVENT", "message": str(exc)}) from exc
    return {
        "status": "accepted_for_handoff",
        "learning_event": event,
        "durable_persistence": "not_configured",
        "next_owner": "CaTaCaCi/TAL",
    }

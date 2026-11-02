"""Authenticated API boundary for Cirvanna's Complementer advisory agent."""
from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.complementer import compose_complementary_look

SERVICE = "cirvanna-complementer-agent"
VERSION = "0.1.0"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Complementer Agent",
    version=VERSION,
    description="Preference-led advice for colour, fragrance, earrings and aesthetic composition. Advisory only.",
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


@app.post(
    "/v1/complementer/recommend",
    tags=["complementer"],
    dependencies=[Depends(require_internal_token)],
)
def recommend(request: RecommendationRequest) -> dict[str, object]:
    return compose_complementary_look(request.model_dump())

"""Strict v2 request contracts for Complementer and marketplace intelligence."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonalPreferencesIn(StrictModel):
    aesthetics: list[Literal[
        "minimalist", "classic", "romantic", "bold", "bohemian", "streetwear",
        "editorial", "natural", "elegant", "cultural", "sporty", "professional",
        "artsy", "vintage", "glam",
    ]] = Field(default_factory=list, max_length=8)
    favorite_colors: list[str] = Field(default_factory=list, max_length=12)
    avoid_colors: list[str] = Field(default_factory=list, max_length=12)
    favorite_fragrance_families: list[Literal[
        "fresh", "citrus", "floral", "woody", "amber", "gourmand",
        "aquatic", "spicy", "green", "musk",
    ]] = Field(default_factory=list, max_length=10)
    preferred_scent_notes: list[str] = Field(default_factory=list, max_length=8)
    fragrance_sensitive: bool = False
    fragrance_free: bool = False
    fragrance_intensity: Literal["light", "moderate", "bold"] | None = None
    fragrance_projection: Literal["intimate", "moderate", "strong"] | None = None
    fragrance_longevity: Literal["short", "moderate", "long"] | None = None
    fragrance_budget_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    fragrance_budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    earrings_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_earring_shapes: list[str] = Field(default_factory=list, max_length=8)
    necklace_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_necklace_shapes: list[str] = Field(default_factory=list, max_length=8)
    preferred_metals: list[Literal["gold", "silver", "rose_gold", "mixed"]] = Field(default_factory=list, max_length=4)
    glasses_preference: Literal["yes", "no_preference", "avoid"] = "no_preference"
    preferred_frame_shapes: list[str] = Field(default_factory=list, max_length=8)
    preferred_finishing_accessories: list[Literal["bag", "scarf", "belt", "watch", "hair_accessory", "brooch"]] = Field(default_factory=list, max_length=6)
    preferred_makeup_colors: list[str] = Field(default_factory=list, max_length=8)
    self_described_undertone: Literal["warm", "cool", "neutral", "olive"] | None = None
    self_described_face_shape: Literal["round", "oval", "square", "heart"] | None = None
    user_declared_cultural_style_tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator(
        "favorite_colors", "avoid_colors", "preferred_scent_notes",
        "preferred_earring_shapes", "preferred_necklace_shapes",
        "preferred_frame_shapes", "preferred_makeup_colors",
        "user_declared_cultural_style_tags",
    )
    @classmethod
    def clean_labels(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 80 for value in cleaned):
            raise ValueError("labels must be non-empty and no longer than 80 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("labels must be unique")
        return cleaned

    @model_validator(mode="after")
    def validate_budget(self):
        if (self.fragrance_budget_minor is None) != (self.fragrance_budget_currency is None):
            raise ValueError("fragrance budget amount and currency must be supplied together")
        if self.fragrance_budget_currency is not None:
            self.fragrance_budget_currency = self.fragrance_budget_currency.upper()
            if not self.fragrance_budget_currency.isalpha():
                raise ValueError("fragrance budget currency must be a three-letter code")
        return self


class PersonalLookIn(StrictModel):
    outfit_colors: list[str] = Field(default_factory=list, max_length=8)
    neckline: Literal["high", "crew", "collared", "v_neck", "strapless", "off_shoulder", "scoop", "unknown"] = "unknown"
    hairstyle: Literal["up", "down", "short", "braids", "locs", "protected_style", "unknown"] = "unknown"
    climate: Literal["hot_humid", "hot_dry", "cool", "temperate", "unknown"] = "unknown"
    occasion: str | None = Field(default=None, max_length=80)
    signature_items: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("outfit_colors", "signature_items")
    @classmethod
    def validate_context_labels(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 80 for value in cleaned):
            raise ValueError("look labels must be non-empty and no longer than 80 characters")
        return cleaned


class PersonalRecommendationRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    preferences: PersonalPreferencesIn
    look: PersonalLookIn = Field(default_factory=PersonalLookIn)

    @field_validator("request_id", "user_id")
    @classmethod
    def trim_ids(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier must not be blank")
        return cleaned


class ProductFacetIn(StrictModel):
    values: list[str] = Field(default_factory=list, max_length=40)
    evidence_level: Literal[
        "independently_reviewed", "merchant_asserted", "user_reported",
        "aggregated_observed", "unknown",
    ] = "unknown"
    source_ref: str | None = Field(default=None, max_length=240)
    reviewed_at: str | None = Field(default=None, max_length=40)
    freshness_days: int = Field(default=180, ge=1, le=3650)
    sample_size: int | None = Field(default=None, ge=0, le=1_000_000_000)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 100 for value in cleaned):
            raise ValueError("facet values must be non-empty and no longer than 100 characters")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("facet values must be unique")
        return cleaned

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.evidence_level != "unknown" and not (self.source_ref or "").strip():
            raise ValueError("non-unknown evidence requires source_ref")
        if self.evidence_level == "aggregated_observed" and self.sample_size is None:
            raise ValueError("aggregated evidence requires sample_size")
        return self


class ProductIntelligenceMetadataIn(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    climate_compatibility: ProductFacetIn | None = None
    cultural_usage: ProductFacetIn | None = None
    occasion_context: ProductFacetIn | None = None
    skin_response: ProductFacetIn | None = None
    feature_complementarity: ProductFacetIn | None = None
    historical_success: ProductFacetIn | None = None


class ProductIn(StrictModel):
    product_id: str = Field(min_length=1, max_length=128)
    catalog_version: int = Field(ge=1)
    product_intelligence: ProductIntelligenceMetadataIn | None = None


class ProductProfileIn(StrictModel):
    climate: str | None = Field(default=None, max_length=80)
    declared_cultural_contexts: list[str] = Field(default_factory=list, max_length=20)
    occasion: str | None = Field(default=None, max_length=80)
    self_reported_skin_attributes: list[str] = Field(default_factory=list, max_length=20)
    user_selected_style_features: list[str] = Field(default_factory=list, max_length=20)


class ProductIntelligenceRequest(StrictModel):
    product: ProductIn
    profile: ProductProfileIn


class SkinScenarioRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=128)
    product_version: int = Field(ge=1)
    consent: bool
    forecast_horizon_weeks: int = Field(ge=1, le=12)
    humidity_scenario: Literal["low", "moderate", "high", "variable"]
    sleep_scenario: Literal["typical", "disrupted", "severely_disrupted"]
    self_reported_skin_attributes: list[str] = Field(default_factory=list, max_length=12)
    cycle_context: Literal["menstrual", "follicular", "ovulatory", "luteal"] | None = None
    cycle_context_consent: bool = False

    @model_validator(mode="after")
    def validate_optional_cycle_context(self):
        if self.cycle_context is not None and not self.cycle_context_consent:
            raise ValueError("cycle context requires separate explicit consent")
        return self


class PreferenceFeedbackRequest(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    recommendation_id: str = Field(min_length=1, max_length=128)
    dimension: Literal[
        "clothing_colour", "makeup_colour", "fragrance_family", "fragrance_note",
        "earrings", "necklace", "glasses", "accessory", "aesthetic",
    ]
    action: Literal["approved", "rejected", "modified", "not_relevant"]
    value: str = Field(min_length=1, max_length=120)
    modified_value: str | None = Field(default=None, max_length=120)
    learning_consent: bool

    @field_validator("event_id", "request_id", "user_id", "recommendation_id", "value", "modified_value")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned

"""Typed, evidence-backed marketplace product intelligence metadata.

This module validates seller/product facts only. It never stores user profiles,
infers protected identity, or authorizes product display.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(StrictModel):
    source_type: Literal[
        "manufacturer_declared",
        "merchant_catalogued",
        "independent_cosmetic_test",
        "editorially_reviewed",
        "consented_aggregate",
    ]
    reference: str = Field(min_length=3, max_length=240)
    reviewed_at: str = Field(min_length=10, max_length=40)

    @field_validator("reference", "reviewed_at")
    @classmethod
    def trim_evidence_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("evidence reference and review date must not be blank")
        return cleaned


class ClimateCompatibility(StrictModel):
    compatible_conditions: list[Literal["hot_humid", "hot_dry", "temperate", "cool"]] = Field(min_length=1, max_length=4)
    evidence: EvidenceRef

    @field_validator("compatible_conditions")
    @classmethod
    def unique_conditions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("climate conditions must be unique")
        return values


class ContextUsage(StrictModel):
    intended_contexts: list[Literal[
        "daily", "work", "evening", "formal", "date", "travel", "sport", "special_occasion"
    ]] = Field(min_length=1, max_length=8)
    evidence: EvidenceRef


class CulturalUsage(StrictModel):
    declared_tags: list[str] = Field(min_length=1, max_length=20)
    editorial_reviewed: bool
    evidence: EvidenceRef

    @field_validator("declared_tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().split()) for value in values]
        if any(not value or len(value) > 80 for value in cleaned):
            raise ValueError("cultural tags must be non-empty and at most 80 characters")
        if len(cleaned) != len(set(value.casefold() for value in cleaned)):
            raise ValueError("cultural tags must be unique")
        return cleaned

    @model_validator(mode="after")
    def require_editorial_evidence(self) -> "CulturalUsage":
        if not self.editorial_reviewed or self.evidence.source_type != "editorially_reviewed":
            raise ValueError("cultural product metadata requires explicit editorial review evidence")
        return self


class SkinResponseMetadata(StrictModel):
    ingredient_labels: list[str] = Field(default_factory=list, max_length=250)
    cosmetic_intent_tags: list[str] = Field(default_factory=list, max_length=20)
    caution_labels: list[str] = Field(default_factory=list, max_length=40)
    evidence: EvidenceRef

    @field_validator("ingredient_labels", "cosmetic_intent_tags", "caution_labels")
    @classmethod
    def validate_skin_labels(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.strip().split()) for value in values]
        if any(not value or len(value) > 120 for value in cleaned):
            raise ValueError("skin metadata labels must be non-empty and at most 120 characters")
        return cleaned

    @model_validator(mode="after")
    def require_non_clinical_evidence(self) -> "SkinResponseMetadata":
        if self.evidence.source_type not in {
            "manufacturer_declared", "independent_cosmetic_test", "merchant_catalogued"
        }:
            raise ValueError("skin metadata requires manufacturer, merchant or cosmetic-test evidence")
        return self


class AppearanceComplement(StrictModel):
    shade_families: list[str] = Field(default_factory=list, max_length=30)
    undertone_matches: list[Literal["warm", "cool", "neutral", "olive", "golden", "not_assessed"]] = Field(default_factory=list, max_length=6)
    finishes: list[str] = Field(default_factory=list, max_length=20)
    pairing_colors: list[str] = Field(default_factory=list, max_length=30)
    feature_complement_tags: list[str] = Field(default_factory=list, max_length=30)
    evidence: EvidenceRef


class ObservedOutcome(StrictModel):
    metric: Literal["positive_review_share", "repurchase_share", "reported_satisfaction"]
    value: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=30, le=10_000_000)
    observation_window_days: int = Field(ge=30, le=3650)
    evidence: EvidenceRef
    limitations: str = Field(min_length=20, max_length=600)

    @model_validator(mode="after")
    def require_aggregate_evidence(self) -> "ObservedOutcome":
        if self.evidence.source_type != "consented_aggregate":
            raise ValueError("observed outcomes require consented aggregate evidence")
        return self


class ProductIntelligence(StrictModel):
    schema_version: Literal["1.0"]
    climate_compatibility: ClimateCompatibility | None = None
    context_usage: ContextUsage | None = None
    cultural_usage: CulturalUsage | None = None
    skin_response: SkinResponseMetadata | None = None
    appearance_complement: AppearanceComplement | None = None
    observed_outcomes: ObservedOutcome | None = None


def validate_product_intelligence_attributes(attributes: dict) -> dict:
    """Validate optional namespaced metadata while preserving unrelated catalog tags."""
    if "product_intelligence" not in attributes:
        return attributes
    intelligence = ProductIntelligence.model_validate(attributes["product_intelligence"])
    normalized = dict(attributes)
    normalized["product_intelligence"] = intelligence.model_dump(mode="json", exclude_none=True)
    return normalized

"""Typed, evidence-backed marketplace product intelligence metadata.

This module validates seller/product facts only. It never stores user profiles,
infers protected identity, establishes clinical efficacy, or authorizes display.
Catalog remains the canonical owner of product identity and version history.
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
        "independent_product_test",
        "public_research",
        "licensed_research",
        "licensed_provider_api",
        "regulatory_publication",
        "editorially_reviewed",
        "consented_aggregate",
    ]
    reference: str = Field(min_length=3, max_length=240)
    reviewed_at: str = Field(min_length=10, max_length=40)
    # source_id binds this reference to the CIL source-rights registry. It is
    # optional for legacy metadata, mandatory for new structured records.
    source_id: str | None = Field(default=None, min_length=3, max_length=120)
    evidence_grade: Literal["E1", "E2", "E3", "E4", "E5", "E6"] | None = None
    scope: Literal["finished_product", "ingredient", "model", "general"] | None = None

    @field_validator("reference", "reviewed_at")
    @classmethod
    def trim_evidence_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("evidence reference and review date must not be blank")
        return cleaned

    @field_validator("source_id")
    @classmethod
    def trim_source_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source_id must not be blank")
        return cleaned


class IngredientDeclaration(StrictModel):
    inci_name: str = Field(min_length=1, max_length=120)
    evidence: EvidenceRef
    label_order: int | None = Field(default=None, ge=1, le=500)

    @field_validator("inci_name")
    @classmethod
    def normalize_inci_label(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("INCI label must not be blank")
        return cleaned

    @model_validator(mode="after")
    def require_product_label_evidence(self) -> "IngredientDeclaration":
        if self.evidence.source_id is None:
            raise ValueError("structured ingredient declarations require a CIL source_id")
        if self.evidence.scope != "finished_product":
            raise ValueError("ingredient declarations require finished-product label/test evidence")
        if self.evidence.evidence_grade not in {"E1", "E2", "E4"}:
            raise ValueError("ingredient declarations require product-specific E1, E2, or E4 evidence")
        if self.evidence.source_type not in {
            "manufacturer_declared", "merchant_catalogued",
            "independent_cosmetic_test", "independent_product_test",
        }:
            raise ValueError("ingredient declarations require product-label or product-test provenance")
        return self


class ProductClaim(StrictModel):
    claim_id: str = Field(min_length=3, max_length=120)
    claim_type: Literal[
        "ingredient_presence", "cosmetic_intent", "formulation_description",
        "finished_product_efficacy",
    ]
    statement: str = Field(min_length=10, max_length=600)
    evidence: EvidenceRef
    review_status: Literal["pending_review", "rejected"] = "pending_review"
    limitations: str = Field(min_length=20, max_length=600)

    @field_validator("claim_id", "statement", "limitations")
    @classmethod
    def trim_claim_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("claim fields must not be blank")
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
            "manufacturer_declared", "independent_cosmetic_test", "independent_product_test",
            "merchant_catalogued",
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
    ingredient_declarations: list[IngredientDeclaration] = Field(default_factory=list, max_length=250)
    claims: list[ProductClaim] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def require_unique_ingredients_and_claims(self) -> "ProductIntelligence":
        ingredient_keys = [item.inci_name.casefold() for item in self.ingredient_declarations]
        if len(ingredient_keys) != len(set(ingredient_keys)):
            raise ValueError("ingredient declarations must be unique after case/space normalization")
        claim_ids = [item.claim_id for item in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("product claim IDs must be unique")
        return self


def validate_product_intelligence_attributes(attributes: dict) -> dict:
    """Validate optional namespaced metadata while preserving unrelated catalog tags."""
    if "product_intelligence" not in attributes:
        return attributes
    intelligence = ProductIntelligence.model_validate(attributes["product_intelligence"])
    normalized = dict(attributes)
    normalized["product_intelligence"] = intelligence.model_dump(mode="json", exclude_none=True)
    return normalized

"""Cirvanna Intelligence Layer domain contracts.

The package provides source-rights, evidence, product, model-validation and
consented outcome contracts. It is not yet a deployed service or durable store.
"""
from .evidence import (
    ClaimAssessment,
    ClaimSupport,
    ClaimType,
    EvidenceGrade,
    EvidenceRecord,
    EvidenceScope,
    ProductClaim,
    assess_product_claim,
)
from .feedback import (
    FeedbackAggregate,
    FeedbackReason,
    RecommendationAction,
    RecommendationOutcome,
    SuitabilityResponse,
    aggregate_feedback_cohort,
)
from .models import ModelMetric, ModelValidationCard, ModelValidationStatus
from .product import IngredientDeclaration, ProductIntelligenceRecord, normalize_inci_label
from .source_registry import DataPurpose, RightsStatus, SourceKind, SourceRecord

__all__ = [
    "ClaimAssessment", "ClaimSupport", "ClaimType", "DataPurpose",
    "EvidenceGrade", "EvidenceRecord", "EvidenceScope", "FeedbackAggregate",
    "FeedbackReason", "IngredientDeclaration", "ModelMetric", "ModelValidationCard",
    "ModelValidationStatus", "ProductClaim", "ProductIntelligenceRecord",
    "RecommendationAction", "RecommendationOutcome", "RightsStatus", "SourceKind",
    "SourceRecord", "SuitabilityResponse", "aggregate_feedback_cohort",
    "assess_product_claim", "normalize_inci_label",
]

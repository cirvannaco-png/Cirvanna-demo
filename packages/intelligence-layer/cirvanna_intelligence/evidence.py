"""Evidence and claim-assessment contracts for product intelligence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .source_registry import DataPurpose, SourceKind, SourceRecord, _parse_aware, _required_text


class EvidenceGrade(StrEnum):
    E1 = "E1"  # Independent, product-specific clinical or controlled evaluation
    E2 = "E2"  # Peer-reviewed research with scope preserved
    E3 = "E3"  # Independently validated model evidence
    E4 = "E4"  # Manufacturer/merchant product documentation
    E5 = "E5"  # Consented, aggregated customer feedback
    E6 = "E6"  # Unverified or marketing-only assertion


class EvidenceScope(StrEnum):
    FINISHED_PRODUCT = "finished_product"
    INGREDIENT = "ingredient"
    MODEL = "model"
    GENERAL = "general"


class ClaimType(StrEnum):
    INGREDIENT_PRESENCE = "ingredient_presence"
    COSMETIC_INTENT = "cosmetic_intent"
    FORMULATION_DESCRIPTION = "formulation_description"
    FINISHED_PRODUCT_EFFICACY = "finished_product_efficacy"


class ClaimSupport(StrEnum):
    SUPPORTED = "supported"
    PROVISIONAL = "provisional"
    UNSUPPORTED = "unsupported"
    RIGHTS_UNCLEARED = "rights_uncleared"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    grade: EvidenceGrade
    scope: EvidenceScope
    reference: str
    methodology: str
    population: str
    limitations: str
    reviewed_at: str
    sample_size: int | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "source_id", "reference", "methodology", "population", "limitations"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, max_length=1200))
        if not isinstance(self.grade, EvidenceGrade):
            raise ValueError("grade must be an EvidenceGrade")
        if not isinstance(self.scope, EvidenceScope):
            raise ValueError("scope must be an EvidenceScope")
        _parse_aware(self.reviewed_at, "reviewed_at")
        if self.grade in {EvidenceGrade.E1, EvidenceGrade.E2, EvidenceGrade.E3} and self.sample_size is None:
            raise ValueError("E1-E3 evidence requires a documented sample_size")
        if self.sample_size is not None and (
            not isinstance(self.sample_size, int) or isinstance(self.sample_size, bool) or self.sample_size < 1
        ):
            raise ValueError("sample_size must be a positive integer or None")


@dataclass(frozen=True)
class ProductClaim:
    claim_id: str
    product_id: str
    claim_type: ClaimType
    statement: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("claim_id", "product_id", "statement"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, max_length=1000))
        if not isinstance(self.claim_type, ClaimType):
            raise ValueError("claim_type must be a ClaimType")
        if not isinstance(self.evidence_ids, tuple) or not self.evidence_ids:
            raise ValueError("evidence_ids must be a non-empty tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain non-empty identifiers")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: str
    support: ClaimSupport
    qualifying_evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    user_facing_claim_allowed: bool


def assess_product_claim(
    claim: ProductClaim,
    evidence_records: Mapping[str, EvidenceRecord],
    sources: Mapping[str, SourceRecord],
    *,
    purpose: DataPurpose = DataPurpose.COMMERCIAL_RECOMMENDATION,
    at: str | None = None,
) -> ClaimAssessment:
    """Assess whether evidence can support the exact scope of a product claim.

    Ingredient-level research is deliberately insufficient to establish finished-
    product efficacy. Customer feedback and marketing claims are not clinical proof.
    """
    if not isinstance(claim, ProductClaim):
        raise ValueError("claim must be a ProductClaim")

    found: list[EvidenceRecord] = []
    reasons: list[str] = []
    rights_cleared: list[EvidenceRecord] = []
    for evidence_id in claim.evidence_ids:
        item = evidence_records.get(evidence_id)
        if item is None:
            reasons.append("EVIDENCE_REFERENCE_MISSING")
            continue
        found.append(item)
        source = sources.get(item.source_id)
        if source is None:
            reasons.append("SOURCE_REGISTRY_ENTRY_MISSING")
            continue
        if not source.allows(purpose, at=at):
            reasons.append("SOURCE_RIGHTS_DO_NOT_ALLOW_PURPOSE")
            continue
        rights_cleared.append(item)

    if not found:
        return ClaimAssessment(claim.claim_id, ClaimSupport.UNSUPPORTED, (), tuple(sorted(set(reasons or ["NO_EVIDENCE"]))), False)
    if not rights_cleared:
        return ClaimAssessment(claim.claim_id, ClaimSupport.RIGHTS_UNCLEARED, (), tuple(sorted(set(reasons))), False)

    def qualifying(item: EvidenceRecord) -> bool:
        source = sources[item.source_id]
        product_scope = item.scope is EvidenceScope.FINISHED_PRODUCT
        if claim.claim_type is ClaimType.FINISHED_PRODUCT_EFFICACY:
            return (
                product_scope
                and item.grade in {EvidenceGrade.E1, EvidenceGrade.E2}
                and source.source_kind in {
                    SourceKind.PUBLIC_RESEARCH, SourceKind.REGULATORY_PUBLICATION,
                    SourceKind.INDEPENDENT_PRODUCT_TEST, SourceKind.LICENSED_PROVIDER,
                }
            )
        if claim.claim_type is ClaimType.INGREDIENT_PRESENCE:
            return (
                product_scope
                and item.grade in {EvidenceGrade.E1, EvidenceGrade.E2, EvidenceGrade.E4}
                and source.source_kind in {
                    SourceKind.MANUFACTURER_DOCUMENTATION,
                    SourceKind.MERCHANT_CATALOGUE,
                    SourceKind.PUBLIC_RESEARCH,
                    SourceKind.REGULATORY_PUBLICATION,
                    SourceKind.INDEPENDENT_PRODUCT_TEST,
                }
            )
        if claim.claim_type in {ClaimType.COSMETIC_INTENT, ClaimType.FORMULATION_DESCRIPTION}:
            return (
                product_scope
                and item.grade in {EvidenceGrade.E1, EvidenceGrade.E2, EvidenceGrade.E4}
                and source.source_kind in {
                    SourceKind.MANUFACTURER_DOCUMENTATION,
                    SourceKind.MERCHANT_CATALOGUE,
                    SourceKind.PUBLIC_RESEARCH,
                    SourceKind.REGULATORY_PUBLICATION,
                    SourceKind.INDEPENDENT_PRODUCT_TEST,
                }
            )
        return False

    qualified = tuple(sorted(item.evidence_id for item in rights_cleared if qualifying(item)))
    if not qualified:
        reasons.append("EVIDENCE_SCOPE_OR_QUALITY_INSUFFICIENT")
        return ClaimAssessment(claim.claim_id, ClaimSupport.UNSUPPORTED, (), tuple(sorted(set(reasons))), False)

    if claim.claim_type is ClaimType.FINISHED_PRODUCT_EFFICACY:
        support = ClaimSupport.SUPPORTED
        reasons.append("PRODUCT_SPECIFIC_E1_E2_EVIDENCE")
    elif any(
        item.grade in {EvidenceGrade.E1, EvidenceGrade.E2}
        for item in rights_cleared if item.evidence_id in qualified
    ):
        support = ClaimSupport.SUPPORTED
        reasons.append("PRODUCT_SPECIFIC_RESEARCH_OR_TEST_EVIDENCE")
    elif any(
        sources[item.source_id].source_kind is SourceKind.MANUFACTURER_DOCUMENTATION
        for item in rights_cleared if item.evidence_id in qualified
    ):
        support = ClaimSupport.PROVISIONAL
        reasons.append("MANUFACTURER_DECLARATION_REQUIRES_CLAIM_REVIEW")
    else:
        support = ClaimSupport.PROVISIONAL
        reasons.append("MERCHANT_CATALOGUE_EVIDENCE_REQUIRES_VERIFICATION")

    # Provisional claims remain usable for internal review, never as asserted
    # efficacy or safety promises. The caller owns the user-facing claim policy.
    return ClaimAssessment(
        claim_id=claim.claim_id,
        support=support,
        qualifying_evidence_ids=qualified,
        reason_codes=tuple(sorted(set(reasons))),
        user_facing_claim_allowed=support is ClaimSupport.SUPPORTED,
    )

"""Canonical product-intelligence records; Catalog remains product authority."""
from __future__ import annotations

from dataclasses import dataclass

from .evidence import EvidenceRecord, EvidenceScope, ProductClaim
from .source_registry import _required_text


def normalize_inci_label(value: str) -> str:
    """Normalize spacing/case only; this is not an authoritative INCI lookup."""
    return " ".join(_required_text(value, "inci_name", max_length=120).split()).casefold()


@dataclass(frozen=True)
class IngredientDeclaration:
    product_id: str
    inci_name: str
    evidence_id: str
    label_order: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _required_text(self.product_id, "product_id"))
        object.__setattr__(self, "inci_name", _required_text(self.inci_name, "inci_name", max_length=120))
        object.__setattr__(self, "evidence_id", _required_text(self.evidence_id, "evidence_id"))
        if self.label_order is not None and (
            not isinstance(self.label_order, int) or isinstance(self.label_order, bool) or self.label_order < 1
        ):
            raise ValueError("label_order must be a positive integer or None")


@dataclass(frozen=True)
class ProductIntelligenceRecord:
    product_id: str
    catalog_version: int
    ingredients: tuple[IngredientDeclaration, ...]
    claims: tuple[ProductClaim, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _required_text(self.product_id, "product_id"))
        if not isinstance(self.catalog_version, int) or isinstance(self.catalog_version, bool) or self.catalog_version < 1:
            raise ValueError("catalog_version must be a positive integer")
        if not isinstance(self.ingredients, tuple) or not isinstance(self.claims, tuple):
            raise ValueError("ingredients and claims must be tuples")
        if any(not isinstance(item, IngredientDeclaration) for item in self.ingredients):
            raise ValueError("ingredients must contain IngredientDeclaration records")
        if any(not isinstance(item, ProductClaim) for item in self.claims):
            raise ValueError("claims must contain ProductClaim records")
        if any(item.product_id != self.product_id for item in self.ingredients + self.claims):
            raise ValueError("all ingredient declarations and claims must belong to the product")
        normalized = [normalize_inci_label(item.inci_name) for item in self.ingredients]
        if len(normalized) != len(set(normalized)):
            raise ValueError("ingredient declarations must not repeat an INCI label")
        claim_ids = [item.claim_id for item in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique within a product record")

    def validate_evidence_links(self, evidence_records: dict[str, EvidenceRecord]) -> None:
        for item in self.ingredients:
            evidence = evidence_records.get(item.evidence_id)
            if evidence is None:
                raise ValueError(f"ingredient declaration references missing evidence: {item.evidence_id}")
            if evidence.scope is not EvidenceScope.FINISHED_PRODUCT:
                raise ValueError("ingredient declaration evidence must identify a finished product label/test")
        for claim in self.claims:
            missing = [item for item in claim.evidence_ids if item not in evidence_records]
            if missing:
                raise ValueError(f"claim references missing evidence: {', '.join(sorted(missing))}")

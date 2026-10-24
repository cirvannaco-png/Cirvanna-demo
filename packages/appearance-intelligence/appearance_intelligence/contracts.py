"""Versioned contracts for catalog-backed appearance decisions."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

_CURRENCY = re.compile(r"^[A-Z]{3}$")

def normalize_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())

def normalize_category(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")

class SpecialistId(str, Enum):
    HAIR = "hair"
    FACE = "face"
    SKIN = "skin"
    LOOK = "look"
    FOOTWEAR = "footwear"
    MAKEUP = "makeup"
    SKINCARE = "skincare"

class EvaluationStatus(str, Enum):
    COMPLETED = "completed"
    NO_CATALOG_CANDIDATES = "no_catalog_candidates"
    NEEDS_REVIEW = "needs_review"
    PROVIDER_UNAVAILABLE = "provider_unavailable"

@dataclass(frozen=True)
class CatalogProduct:
    """Validated view of the canonical Catalog Service product contract."""
    product_id: str
    sku: str
    name: str
    category: str
    price_minor: int
    currency: str
    attributes: Mapping[str, Any]
    status: str = "active"
    catalog_version: int = 1
    brand: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        for name in ("product_id", "sku", "name", "category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.price_minor, bool) or not isinstance(self.price_minor, int) or self.price_minor < 0:
            raise ValueError("price_minor must be a non-negative integer")
        if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency.strip().upper()):
            raise ValueError("currency must be a three-letter code")
        if self.status != "active":
            raise ValueError("only active canonical catalog products may be evaluated")
        if isinstance(self.catalog_version, bool) or not isinstance(self.catalog_version, int) or self.catalog_version < 1:
            raise ValueError("catalog_version must be a positive integer")
        if not isinstance(self.attributes, Mapping):
            raise ValueError("attributes must be a mapping")
        object.__setattr__(self, "currency", self.currency.strip().upper())
        object.__setattr__(self, "attributes", dict(self.attributes))

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> "CatalogProduct":
        if not isinstance(record, Mapping):
            raise ValueError("catalog product must be an object")
        required = ("product_id", "sku", "name", "category", "price_minor", "currency", "attributes", "status", "catalog_version")
        missing = [key for key in required if key not in record]
        if missing:
            raise ValueError("catalog product is missing required fields: " + ", ".join(missing))
        return cls(
            product_id=record["product_id"], sku=record["sku"], name=record["name"],
            category=record["category"], price_minor=record["price_minor"],
            currency=record["currency"], attributes=record["attributes"],
            status=record["status"], catalog_version=record["catalog_version"],
            brand=record.get("brand"), description=record.get("description"),
        )

    @property
    def normalized_category(self) -> str:
        return normalize_category(self.category)

    def npl_attributes(self) -> tuple[str, ...]:
        """Provide only catalog-declared fields to canonical NPL."""
        tags = {normalize_text(self.product_id), normalize_text(self.sku), normalize_text(self.name), self.normalized_category}
        if self.brand:
            tags.add(normalize_text(self.brand))
        for key, value in self.attributes.items():
            normalized_key = normalize_category(str(key))
            if not normalized_key:
                continue
            tags.add(normalized_key)
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            for item in values:
                if isinstance(item, (str, int, float, bool)):
                    normalized_value = normalize_text(str(item))
                    if normalized_value:
                        tags.add(normalized_value)
                        tags.add(f"{normalized_key}:{normalized_value}")
        return tuple(sorted(tags))

@dataclass(frozen=True)
class CatalogSnapshot:
    """One complete catalog read stamped by the trusted adapter."""
    products: tuple[CatalogProduct, ...]
    fetched_at: datetime
    complete: bool
    source: str = "cirvanna-catalog-service"

    def __post_init__(self) -> None:
        if not isinstance(self.products, tuple) or any(not isinstance(p, CatalogProduct) for p in self.products):
            raise ValueError("products must be a tuple of validated CatalogProduct records")
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        if not isinstance(self.complete, bool):
            raise ValueError("complete must be a boolean")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be non-empty")
        ids = [p.product_id for p in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError("catalog snapshot contains duplicate product IDs")

    def is_fresh(self, now: datetime, max_age_seconds: int = 120) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if not isinstance(max_age_seconds, int) or max_age_seconds < 1:
            raise ValueError("max_age_seconds must be positive")
        age = (now - self.fetched_at).total_seconds()
        return self.complete and 0 <= age <= max_age_seconds

@dataclass(frozen=True)
class AppearanceContext:
    """Server-authenticated identity plus explicitly declared user constraints."""
    request_id: str
    user_id: str
    currency: str | None = None
    budget_minor: int | None = None
    hard_constraints: Mapping[str, str] = field(default_factory=dict)
    preferred_attributes: Mapping[str, str] = field(default_factory=dict)
    cultural_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("request_id", "user_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.currency is not None:
            if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency.strip().upper()):
                raise ValueError("currency must be a three-letter code")
            object.__setattr__(self, "currency", self.currency.strip().upper())
        if self.budget_minor is not None:
            if isinstance(self.budget_minor, bool) or not isinstance(self.budget_minor, int) or self.budget_minor < 0:
                raise ValueError("budget_minor must be a non-negative integer")
            if self.currency is None:
                raise ValueError("currency is required with a budget")
        for name in ("hard_constraints", "preferred_attributes"):
            values = getattr(self, name)
            if not isinstance(values, Mapping):
                raise ValueError(f"{name} must be a mapping")
            if any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip() for k, v in values.items()):
                raise ValueError(f"{name} keys and values must be non-empty strings")
            object.__setattr__(self, name, dict(values))
        if not isinstance(self.cultural_requirements, tuple) or any(not isinstance(v, str) or not v.strip() for v in self.cultural_requirements):
            raise ValueError("cultural_requirements must be a tuple of non-empty strings")

@dataclass(frozen=True)
class CandidateEvaluation:
    product: CatalogProduct
    npl_decision: Any
    arbitration: Any

    @property
    def may_display(self) -> bool:
        return bool(self.arbitration.may_display)

    @property
    def verdict(self) -> str:
        return self.arbitration.verdict.value

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.arbitration.reasons)

@dataclass(frozen=True)
class SpecialistResult:
    specialist: SpecialistId
    status: EvaluationStatus
    candidates: tuple[CandidateEvaluation, ...] = ()
    notices: tuple[str, ...] = ()

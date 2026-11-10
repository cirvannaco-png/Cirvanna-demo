"""Rights-aware registry contracts for Cirvanna intelligence sources.

A source being publicly visible does not, by itself, grant permission for
commercial reuse, model training, redistribution, or automated collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from urllib.parse import urlsplit


class SourceKind(StrEnum):
    PUBLIC_RESEARCH = "public_research"
    MANUFACTURER_DOCUMENTATION = "manufacturer_documentation"
    MERCHANT_CATALOGUE = "merchant_catalogue"
    CUSTOMER_FEEDBACK = "customer_feedback"
    INDEPENDENT_PRODUCT_TEST = "independent_product_test"
    LICENSED_PROVIDER = "licensed_provider"
    REGULATORY_PUBLICATION = "regulatory_publication"
    MODEL_VALIDATION = "model_validation"


class RightsStatus(StrEnum):
    PUBLIC_DOMAIN = "public_domain"
    OPEN_LICENSE = "open_license"
    LICENSED = "licensed"
    API_TERMS = "api_terms"
    RESEARCH_ONLY = "research_only"
    PERMISSION_REQUIRED = "permission_required"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


class DataPurpose(StrEnum):
    INTERNAL_RESEARCH = "internal_research"
    PRODUCT_ENRICHMENT = "product_enrichment"
    COMMERCIAL_RECOMMENDATION = "commercial_recommendation"
    MODEL_EVALUATION = "model_evaluation"
    MODEL_TRAINING = "model_training"
    AGGREGATE_ANALYTICS = "aggregate_analytics"


_NON_USABLE_RIGHTS = {
    RightsStatus.PERMISSION_REQUIRED,
    RightsStatus.UNKNOWN,
    RightsStatus.PROHIBITED,
}
_RIGHTS_REQUIRING_BASIS = {
    RightsStatus.PUBLIC_DOMAIN,
    RightsStatus.OPEN_LICENSE,
    RightsStatus.LICENSED,
    RightsStatus.API_TERMS,
    RightsStatus.RESEARCH_ONLY,
}
_RESEARCH_ONLY_PURPOSES = {
    DataPurpose.INTERNAL_RESEARCH,
    DataPurpose.MODEL_EVALUATION,
}


def _parse_aware(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _required_text(value: str, field_name: str, *, max_length: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    cleaned = " ".join(value.strip().split())
    if not cleaned or len(cleaned) > max_length:
        raise ValueError(f"{field_name} must contain 1-{max_length} characters")
    return cleaned


@dataclass(frozen=True)
class SourceRecord:
    """A source registration; it stores provenance, not copied source content."""

    source_id: str
    owner: str
    source_kind: SourceKind
    locator: str
    access_method: str
    rights_status: RightsStatus
    permitted_purposes: tuple[DataPurpose, ...]
    collected_at: str
    reviewed_at: str
    rights_reference: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    expires_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "owner", "locator", "access_method"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if not isinstance(self.source_kind, SourceKind):
            raise ValueError("source_kind must be a SourceKind")
        if not isinstance(self.rights_status, RightsStatus):
            raise ValueError("rights_status must be a RightsStatus")
        if not isinstance(self.permitted_purposes, tuple) or any(
            not isinstance(item, DataPurpose) for item in self.permitted_purposes
        ):
            raise ValueError("permitted_purposes must be a tuple of DataPurpose values")
        if len(self.permitted_purposes) != len(set(self.permitted_purposes)):
            raise ValueError("permitted_purposes must not contain duplicates")

        if self.rights_status in _RIGHTS_REQUIRING_BASIS:
            if not self.rights_reference or not self.rights_reference.strip():
                raise ValueError("reusable sources require a rights_reference or licence/terms record")
        if self.rights_status in _NON_USABLE_RIGHTS and self.permitted_purposes:
            raise ValueError("unknown, prohibited, or permission-pending sources cannot grant permitted purposes")
        if self.rights_status is RightsStatus.RESEARCH_ONLY and any(
            item not in _RESEARCH_ONLY_PURPOSES for item in self.permitted_purposes
        ):
            raise ValueError("research-only sources cannot be used for commercial recommendation or training")
        if self.attribution_required and not (self.attribution_text and self.attribution_text.strip()):
            raise ValueError("attribution text is required when attribution_required is true")
        if not isinstance(self.attribution_required, bool):
            raise ValueError("attribution_required must be boolean")

        locator = self.locator
        if locator.startswith(("http://", "https://")):
            parsed_locator = urlsplit(locator)
            if parsed_locator.scheme != "https" or not parsed_locator.hostname:
                raise ValueError("web source locators must use absolute HTTPS URLs")
            if parsed_locator.username is not None or parsed_locator.password is not None:
                raise ValueError("source locators must not embed credentials")

        collected = _parse_aware(self.collected_at, "collected_at")
        reviewed = _parse_aware(self.reviewed_at, "reviewed_at")
        if reviewed < collected:
            raise ValueError("reviewed_at cannot precede collected_at")
        if self.expires_at is not None:
            expires = _parse_aware(self.expires_at, "expires_at")
            if expires <= reviewed:
                raise ValueError("expires_at must be later than reviewed_at")

    def allows(self, purpose: DataPurpose, *, at: str | None = None) -> bool:
        """Return whether the recorded terms permit a purpose at the requested time."""
        if not isinstance(purpose, DataPurpose):
            raise ValueError("purpose must be a DataPurpose")
        if self.rights_status in _NON_USABLE_RIGHTS or purpose not in self.permitted_purposes:
            return False
        if self.rights_status is RightsStatus.RESEARCH_ONLY and purpose not in _RESEARCH_ONLY_PURPOSES:
            return False
        if self.expires_at is not None:
            moment = _parse_aware(at, "at") if at is not None else datetime.now(timezone.utc)
            if moment >= _parse_aware(self.expires_at, "expires_at"):
                return False
        return True

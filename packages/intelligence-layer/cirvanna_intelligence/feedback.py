"""Consent-gated recommendation outcome records and conservative aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .source_registry import _parse_aware, _required_text


class RecommendationAction(StrEnum):
    OPENED = "opened"
    SAVED = "saved"
    REJECTED = "rejected"
    PURCHASED = "purchased"
    IGNORED = "ignored"


class SuitabilityResponse(StrEnum):
    SUITABLE = "suitable"
    UNSUITABLE = "unsuitable"
    UNCERTAIN = "uncertain"
    NOT_REPORTED = "not_reported"


class FeedbackReason(StrEnum):
    PRICE = "price"
    COLOUR_OR_SHADE = "colour_or_shade"
    SCENT_OR_TEXTURE = "scent_or_texture"
    FINISH_OR_APPEARANCE = "finish_or_appearance"
    CLIMATE_CONTEXT = "climate_context"
    PERSONAL_PREFERENCE = "personal_preference"
    PRODUCT_INFORMATION_INCOMPLETE = "product_information_incomplete"
    AVAILABILITY = "availability"
    OTHER_DECLARED_REASON = "other_declared_reason"


@dataclass(frozen=True)
class RecommendationOutcome:
    event_id: str
    recommendation_id: str
    product_id: str
    context_key: str
    contributor_token: str
    cal_decision_reference: str
    cal_verdict: str
    consent_granted: bool
    consent_receipt_id: str | None
    consent_scope: str | None
    action: RecommendationAction
    reported_suitability: SuitabilityResponse
    reason_codes: tuple[FeedbackReason, ...]
    observed_at: str
    model_version: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "event_id", "recommendation_id", "product_id", "context_key",
            "contributor_token", "cal_decision_reference",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, max_length=240))
        if not isinstance(self.cal_verdict, str) or self.cal_verdict.strip().upper() != "SHOW":
            raise ValueError("outcome events can only reference a verified CAL SHOW decision")
        if not isinstance(self.consent_granted, bool):
            raise ValueError("consent_granted must be boolean")
        if not self.consent_granted:
            raise PermissionError("recommendation outcome learning requires explicit consent")
        if not self.consent_receipt_id or not self.consent_receipt_id.strip():
            raise PermissionError("an active consent receipt is required")
        if self.consent_scope != "recommendation_outcome_learning":
            raise PermissionError("the consent receipt must cover recommendation_outcome_learning")
        if not isinstance(self.action, RecommendationAction):
            raise ValueError("action must be a RecommendationAction")
        if not isinstance(self.reported_suitability, SuitabilityResponse):
            raise ValueError("reported_suitability must be a SuitabilityResponse")
        if not isinstance(self.reason_codes, tuple) or any(not isinstance(item, FeedbackReason) for item in self.reason_codes):
            raise ValueError("reason_codes must be a tuple of FeedbackReason values")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must not contain duplicates")
        if self.reported_suitability is SuitabilityResponse.NOT_REPORTED and self.reason_codes:
            raise ValueError("reason codes require an explicit suitability response")
        _parse_aware(self.observed_at, "observed_at")
        if self.model_version is not None:
            object.__setattr__(self, "model_version", _required_text(self.model_version, "model_version", max_length=240))


@dataclass(frozen=True)
class FeedbackAggregate:
    product_id: str
    context_key: str
    status: str
    contributor_count: int
    reported_count: int | None
    suitable_count: int | None
    unsuitable_count: int | None
    unsure_count: int | None
    unsuitable_share: float | None
    review_recommended: bool
    reason_code: str


def aggregate_feedback_cohort(
    events: tuple[RecommendationOutcome, ...],
    *,
    minimum_contributors: int = 30,
    unsuitable_share_review_threshold: float,
) -> FeedbackAggregate:
    """Return a descriptive review signal, never an automatic product suppression.

    One contributor may contribute at most once to a product/context cohort. A
    missing or uncertain response is not recoded as a failure. The 30-person
    default is a disclosure floor, not differential privacy or causal proof.
    """
    if not isinstance(events, tuple) or not events:
        raise ValueError("events must be a non-empty tuple")
    if any(not isinstance(item, RecommendationOutcome) for item in events):
        raise ValueError("events must contain RecommendationOutcome values")
    if not isinstance(minimum_contributors, int) or isinstance(minimum_contributors, bool) or minimum_contributors < 30:
        raise ValueError("minimum_contributors must be at least 30")
    if (
        isinstance(unsuitable_share_review_threshold, bool)
        or not isinstance(unsuitable_share_review_threshold, (int, float))
        or not isfinite(unsuitable_share_review_threshold)
        or not 0.0 <= unsuitable_share_review_threshold <= 1.0
    ):
        raise ValueError("unsuitable_share_review_threshold must be finite and between 0 and 1")

    products = {item.product_id for item in events}
    contexts = {item.context_key for item in events}
    event_ids = [item.event_id for item in events]
    contributors = [item.contributor_token for item in events]
    if len(products) != 1 or len(contexts) != 1:
        raise ValueError("one aggregate must contain one product and one context cohort")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("event IDs must be unique within a cohort")
    if len(contributors) != len(set(contributors)):
        raise ValueError("each contributor may contribute only once per product/context cohort")

    product_id = next(iter(products))
    context_key = next(iter(contexts))
    contributor_count = len(events)
    response_contributors = sum(
        item.reported_suitability is not SuitabilityResponse.NOT_REPORTED for item in events
    )
    if response_contributors < minimum_contributors:
        return FeedbackAggregate(
            product_id, context_key, "suppressed", contributor_count,
            None, None, None, None, None, False, "CIL_MINIMUM_COHORT_NOT_MET",
        )

    suitable = sum(item.reported_suitability is SuitabilityResponse.SUITABLE for item in events)
    unsuitable = sum(item.reported_suitability is SuitabilityResponse.UNSUITABLE for item in events)
    unsure = sum(item.reported_suitability is SuitabilityResponse.UNCERTAIN for item in events)
    reported = suitable + unsuitable
    share = unsuitable / reported if reported else None
    review = share is not None and share >= float(unsuitable_share_review_threshold)
    return FeedbackAggregate(
        product_id=product_id,
        context_key=context_key,
        status="review_required" if review else "collecting",
        contributor_count=contributor_count,
        reported_count=reported,
        suitable_count=suitable,
        unsuitable_count=unsuitable,
        unsure_count=unsure,
        unsuitable_share=share,
        review_recommended=review,
        reason_code="CIL_UNSUITABLE_SHARE_REVIEW" if review else "CIL_NO_SUPPRESSION_SIGNAL",
    )

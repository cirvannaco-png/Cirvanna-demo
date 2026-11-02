"""Provenance-aware marketplace Product Intelligence evaluation.

This is a metadata compatibility explainer, not ranking, medical advice,
checkout authorization or CaTaCaCi/CAL display authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "1.0.0"
ALLOWED_EVIDENCE = {
    "independently_reviewed",
    "merchant_asserted",
    "user_reported",
    "aggregated_observed",
    "unknown",
}
MIN_HISTORICAL_SAMPLE_SIZE = 20


def _normalise(values: Any) -> set[str]:
    # Single-valued context fields (climate, occasion) and multi-valued facets
    # share the same normalization path.
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {
        " ".join(str(value).strip().casefold().split())
        for value in values
        if isinstance(value, str) and value.strip()
    }


def _facet_result(
    facet: dict[str, Any] | None,
    requested: Any,
    *,
    now: datetime,
    facet_name: str,
) -> dict[str, Any]:
    expected = _normalise(requested)
    if not expected:
        return {
            "status": "not_requested",
            "matched_values": [],
            "reason": "No matching user context was supplied; this dimension was not evaluated.",
        }
    if not isinstance(facet, dict):
        return {
            "status": "unknown",
            "matched_values": [],
            "reason": f"No product evidence is available for {facet_name}.",
        }

    evidence_level = facet.get("evidence_level", "unknown")
    if evidence_level not in ALLOWED_EVIDENCE:
        raise ValueError(f"{facet_name}.evidence_level is unsupported")
    values = _normalise(facet.get("values"))
    source_ref = facet.get("source_ref")
    reviewed_at = facet.get("reviewed_at")
    freshness_days = facet.get("freshness_days", 180)
    sample_size = facet.get("sample_size")

    if not isinstance(freshness_days, int) or not 1 <= freshness_days <= 3650:
        raise ValueError(f"{facet_name}.freshness_days must be between 1 and 3650")
    if sample_size is not None and (not isinstance(sample_size, int) or sample_size < 0):
        raise ValueError(f"{facet_name}.sample_size must be a non-negative integer")
    if evidence_level != "unknown" and (not isinstance(source_ref, str) or not source_ref.strip()):
        raise ValueError(f"{facet_name}.source_ref is required for non-unknown evidence")
    if reviewed_at is not None:
        if not isinstance(reviewed_at, str):
            raise ValueError(f"{facet_name}.reviewed_at must be an ISO-8601 string")
        try:
            timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{facet_name}.reviewed_at is invalid") from exc
        if timestamp.tzinfo is None:
            raise ValueError(f"{facet_name}.reviewed_at must include a timezone")
        if timestamp > now:
            raise ValueError(f"{facet_name}.reviewed_at cannot be in the future")
        age_days = (now - timestamp).total_seconds() / 86400
        if age_days > freshness_days:
            return {
                "status": "stale",
                "matched_values": [],
                "evidence_level": evidence_level,
                "source_ref": source_ref,
                "reason": f"Product {facet_name} evidence is outside its declared freshness window.",
            }

    if evidence_level == "unknown" or not values:
        return {
            "status": "unknown",
            "matched_values": [],
            "reason": f"Product {facet_name} evidence is missing or explicitly unknown.",
        }

    if evidence_level == "aggregated_observed":
        if sample_size is None or sample_size < MIN_HISTORICAL_SAMPLE_SIZE:
            return {
                "status": "suppressed_small_sample",
                "matched_values": [],
                "evidence_level": evidence_level,
                "reason": "Historical pattern is withheld because the cohort is too small for this display policy.",
            }

    matched = sorted(expected.intersection(values))
    if not matched:
        return {
            "status": "no_match",
            "matched_values": [],
            "evidence_level": evidence_level,
            "source_ref": source_ref,
            "reason": f"No supplied {facet_name} evidence matches the selected user context.",
        }

    status_by_level = {
        "independently_reviewed": "reviewed_match",
        "merchant_asserted": "merchant_claim_match",
        "user_reported": "user_reported_match",
        "aggregated_observed": "observed_pattern_match",
    }
    return {
        "status": status_by_level[evidence_level],
        "matched_values": matched,
        "evidence_level": evidence_level,
        "source_ref": source_ref,
        "sample_size": sample_size if evidence_level == "aggregated_observed" else None,
        "reason": (
            f"Product evidence for {facet_name} overlaps the context you selected. "
            f"Evidence source: {evidence_level.replace('_', ' ')}."
        ),
    }


def evaluate_product_intelligence(
    product: dict[str, Any],
    profile: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain evidence matches without producing a blended score or display verdict."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    product_id = product.get("product_id")
    catalog_version = product.get("catalog_version")
    if not isinstance(product_id, str) or not product_id.strip():
        raise ValueError("product_id is required")
    if not isinstance(catalog_version, int) or catalog_version < 1:
        raise ValueError("catalog_version must be a positive integer")

    metadata = product.get("product_intelligence")
    if not isinstance(metadata, dict) or metadata.get("schema_version") != "1.0":
        metadata = {}

    dimensions = {
        "climate_compatibility": _facet_result(
            metadata.get("climate_compatibility"), profile.get("climate"),
            now=now, facet_name="climate compatibility",
        ),
        "cultural_usage": _facet_result(
            metadata.get("cultural_usage"), profile.get("declared_cultural_contexts"),
            now=now, facet_name="cultural usage",
        ),
        "occasion_context": _facet_result(
            metadata.get("occasion_context"), profile.get("occasion"),
            now=now, facet_name="occasion context",
        ),
        "skin_response": _facet_result(
            metadata.get("skin_response"), profile.get("self_reported_skin_attributes"),
            now=now, facet_name="cosmetic skin response",
        ),
        "feature_complementarity": _facet_result(
            metadata.get("feature_complementarity"), profile.get("user_selected_style_features"),
            now=now, facet_name="style complementarity",
        ),
    }

    history = metadata.get("historical_success")
    if not isinstance(history, dict):
        history = {}
    history_result = _facet_result(
        history,
        ["positive_response_pattern"],
        now=now,
        facet_name="historical response pattern",
    )
    dimensions["historical_success"] = history_result

    known = sum(
        item["status"] not in {"unknown", "not_requested", "stale", "suppressed_small_sample"}
        for item in dimensions.values()
    )
    requested = sum(item["status"] != "not_requested" for item in dimensions.values())
    return {
        "schema_version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "product_id": product_id,
        "catalog_version": catalog_version,
        "dimensions": dimensions,
        "evidence_coverage": {
            "requested_dimensions": requested,
            "dimensions_with_comparable_evidence": known,
        },
        "overall_score": None,
        "scores_are_probabilities": False,
        "display_authorized": False,
        "decision_owner": "CaTaCaCi/CAL",
        "explanation": (
            "Each dimension is reported separately. Merchant claims, reviewed evidence, "
            "user reports and aggregate observations are not interchangeable; missing or "
            "stale metadata remains unknown."
        ),
        "limits": [
            "This evaluation is not a product ranking, safety guarantee, fit guarantee or medical assessment.",
            "Cultural context is evaluated only when the user has explicitly selected a context.",
            "Skin-response tags are cosmetic metadata, not a diagnosis or proof of ingredient safety.",
            "Historical outcomes are descriptive associations, not causal evidence or a prediction for an individual.",
            "A candidate must pass the existing user-policy, NPL, Cultural Identity, independent evidence and CAL SHOW gates before display.",
        ],
    }

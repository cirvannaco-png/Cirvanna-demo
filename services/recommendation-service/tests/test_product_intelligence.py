from datetime import datetime, timezone, timedelta

import pytest

from app.product_intelligence import evaluate_product_intelligence


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def product():
    reviewed = (NOW - timedelta(days=3)).isoformat()
    return {
        "product_id": "product-123",
        "catalog_version": 4,
        "product_intelligence": {
            "schema_version": "1.0",
            "climate_compatibility": {
                "values": ["hot_humid"], "evidence_level": "independently_reviewed",
                "source_ref": "review:climate-4", "reviewed_at": reviewed, "freshness_days": 90,
            },
            "cultural_usage": {
                "values": ["ceremonial"], "evidence_level": "merchant_asserted",
                "source_ref": "merchant:usage-4",
            },
            "occasion_context": {
                "values": ["evening"], "evidence_level": "user_reported",
                "source_ref": "survey:occasion-4",
            },
            "skin_response": {
                "values": ["lightweight"], "evidence_level": "independently_reviewed",
                "source_ref": "review:skin-4",
            },
            "feature_complementarity": {
                "values": ["gold accents"], "evidence_level": "merchant_asserted",
                "source_ref": "merchant:style-4",
            },
            "historical_success": {
                "values": ["positive_response_pattern"], "evidence_level": "aggregated_observed",
                "source_ref": "cohort:history-4", "sample_size": 42,
            },
        },
    }


def profile():
    return {
        "climate": "hot_humid",
        "declared_cultural_contexts": ["ceremonial"],
        "occasion": "evening",
        "self_reported_skin_attributes": ["lightweight"],
        "user_selected_style_features": ["gold accents"],
    }


def test_evidence_facets_match_and_keep_provenance_distinct():
    result = evaluate_product_intelligence(product(), profile(), now=NOW)
    dimensions = result["dimensions"]
    assert dimensions["climate_compatibility"]["status"] == "reviewed_match"
    assert dimensions["cultural_usage"]["status"] == "merchant_claim_match"
    assert dimensions["occasion_context"]["status"] == "user_reported_match"
    assert dimensions["historical_success"]["status"] == "observed_pattern_match"
    assert result["display_authorized"] is False
    assert result["overall_score"] is None
    assert result["scores_are_probabilities"] is False


def test_cultural_usage_is_not_evaluated_without_explicit_user_context():
    user = profile()
    user["declared_cultural_contexts"] = []
    result = evaluate_product_intelligence(product(), user, now=NOW)
    assert result["dimensions"]["cultural_usage"]["status"] == "not_requested"


def test_missing_product_evidence_remains_unknown():
    item = {"product_id": "p-1", "catalog_version": 1}
    result = evaluate_product_intelligence(item, profile(), now=NOW)
    assert result["dimensions"]["climate_compatibility"]["status"] == "unknown"
    assert result["dimensions"]["skin_response"]["status"] == "unknown"


def test_stale_evidence_is_not_used():
    item = product()
    item["product_intelligence"]["climate_compatibility"]["reviewed_at"] = (
        NOW - timedelta(days=120)
    ).isoformat()
    result = evaluate_product_intelligence(item, profile(), now=NOW)
    assert result["dimensions"]["climate_compatibility"]["status"] == "stale"


def test_historical_patterns_below_minimum_sample_are_suppressed():
    item = product()
    item["product_intelligence"]["historical_success"]["sample_size"] = 12
    result = evaluate_product_intelligence(item, profile(), now=NOW)
    assert result["dimensions"]["historical_success"]["status"] == "suppressed_small_sample"
    assert result["dimensions"]["historical_success"]["matched_values"] == []


def test_invalid_provenance_is_rejected():
    item = product()
    item["product_intelligence"]["climate_compatibility"]["evidence_level"] = "invented"
    with pytest.raises(ValueError):
        evaluate_product_intelligence(item, profile(), now=NOW)


def test_unselected_context_is_not_personalized_by_geography_or_assumption():
    user = profile()
    user["declared_cultural_contexts"] = []
    result = evaluate_product_intelligence(product(), user, now=NOW)
    assert result["dimensions"]["cultural_usage"]["status"] == "not_requested"

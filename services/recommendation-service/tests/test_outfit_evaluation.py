from __future__ import annotations

import pytest

from app.evaluation.outfit_eval import EvaluationError, evaluate_records, simple_baseline_score, validate_record


def reviewed(outfit_id, relevance, *, exclusion=False, disposition="accept"):
    return [
        {
            "reviewer_key": "reviewer-a",
            "outfit_id": outfit_id,
            "relevance": relevance,
            "coherence": relevance,
            "context_fit": relevance,
            "exclusion_violation": exclusion,
            "disposition": disposition,
            "proposed_item_ids": ["item-replacement"] if disposition == "edit" else [],
        },
        {
            "reviewer_key": "reviewer-b",
            "outfit_id": outfit_id,
            "relevance": relevance,
            "coherence": relevance,
            "context_fit": relevance,
            "exclusion_violation": exclusion,
            "disposition": disposition,
            "proposed_item_ids": ["item-replacement"] if disposition == "edit" else [],
        },
    ]


def sample_record():
    return {
        "dataset_version": "1.0",
        "case_id": "case-opaque-001",
        "split": "locked_test",
        "scenario": {
            "context_tags": ["work", "warm-weather"],
            "style_preferences": ["minimalist", "classic"],
            "hard_exclusions": ["wool"],
        },
        "candidate_outfits": [
            {
                "outfit_id": "outfit-a",
                "item_ids": ["shirt-1", "trouser-1", "shoe-1"],
                "categories": ["tops", "bottoms", "shoes"],
                "colors": ["navy", "cream"],
                "style_tags": ["minimalist", "classic"],
                "context_tags": ["work", "warm-weather"],
                "algorithm_score": 0.95,
                "hard_exclusion_hits": [],
            },
            {
                "outfit_id": "outfit-b",
                "item_ids": ["dress-1", "shoe-2"],
                "categories": ["dress", "shoes"],
                "colors": ["black"],
                "style_tags": ["formal"],
                "context_tags": ["evening"],
                "algorithm_score": 0.70,
                "hard_exclusion_hits": [],
            },
            {
                "outfit_id": "outfit-c",
                "item_ids": ["shirt-2", "trouser-2"],
                "categories": ["tops", "bottoms"],
                "colors": ["blue", "white"],
                "style_tags": ["classic"],
                "context_tags": ["work"],
                "algorithm_score": 0.60,
                "hard_exclusion_hits": ["wool"],
            },
        ],
        "human_reviews": (
            reviewed("outfit-a", 5)
            + reviewed("outfit-b", 2)
            + reviewed("outfit-c", 1, exclusion=True, disposition="reject")
        ),
        "user_outcomes": [
            {"subject_key": "hmac-user-a", "event_id": "e1", "ranker_id": "algorithm", "outfit_id": "outfit-a", "exposure_id": "exposure-1", "event_type": "exposed", "occurred_at": "2026-01-01T09:00:00Z"},
            {"subject_key": "hmac-user-a", "event_id": "e2", "ranker_id": "algorithm", "outfit_id": "outfit-a", "exposure_id": "exposure-1", "event_type": "edited", "occurred_at": "2026-01-01T09:05:00Z", "edited_item_count": 1},
            {"subject_key": "hmac-user-a", "event_id": "e3", "ranker_id": "algorithm", "outfit_id": "outfit-a", "exposure_id": "exposure-1", "event_type": "rejected", "occurred_at": "2026-01-02T09:00:00Z"},
            {"subject_key": "hmac-user-a", "event_id": "e4", "ranker_id": "algorithm", "outfit_id": "outfit-a", "exposure_id": "exposure-2", "event_type": "exposed", "occurred_at": "2026-01-03T09:00:00Z"},
            {"subject_key": "hmac-user-a", "event_id": "e5", "ranker_id": "algorithm", "outfit_id": "outfit-a", "exposure_id": "exposure-2", "event_type": "rejected", "occurred_at": "2026-01-04T09:00:00Z"},
        ],
    }


def test_simple_baseline_is_deterministic_and_documented():
    record = sample_record()
    score = simple_baseline_score(record["candidate_outfits"][0], record["scenario"])
    assert score == 1.0
    assert simple_baseline_score(record["candidate_outfits"][1], record["scenario"]) < score


def test_evaluation_compares_algorithm_and_baseline_on_same_candidate_pool():
    result = evaluate_records([sample_record()], k=2)
    assert result["cases_evaluated"] == 1
    assert result["rankers"]["algorithm"]["mean_relevance_at_k"] == 3.5
    assert result["rankers"]["simple_baseline"]["mean_relevance_at_k"] == 3.0
    assert result["rankers"]["algorithm"]["human_exclusion_violation_rate_at_k"] > 0
    assert result["algorithm_minus_baseline"]["mean_relevance_at_k"] is not None
    assert result["user_behavior"]["algorithm"]["edit_rate"] == 0.5
    assert result["user_behavior"]["algorithm"]["repeated_rejection_rate"] == 1.0
    assert result["user_behavior"]["algorithm"]["reexposures_after_first_rejection"] == 1
    assert result["user_behavior"]["simple_baseline"]["edit_rate"] is None


def test_every_candidate_requires_two_independent_human_reviews():
    record = sample_record()
    record["human_reviews"] = [item for item in record["human_reviews"] if item["reviewer_key"] != "reviewer-b"]
    with pytest.raises(EvaluationError, match="two independent human reviews"):
        validate_record(record)


def test_duplicate_reviewer_annotation_is_rejected():
    record = sample_record()
    record["human_reviews"].append(dict(record["human_reviews"][0]))
    with pytest.raises(EvaluationError, match="duplicate review"):
        validate_record(record)


def test_uncertain_or_human_exclusion_violations_are_reported_not_averaged_away():
    record = sample_record()
    result = evaluate_records([record], k=3)
    assert result["hard_exclusion_cases_with_any_human_violation"]["algorithm"] == 1
    assert result["rankers"]["algorithm"]["human_exclusion_violation_rate_at_k"] > 0


def test_user_events_require_timezone_and_pseudonymous_subject_key():
    record = sample_record()
    record["user_outcomes"][0]["occurred_at"] = "2026-01-01T09:00:00"
    with pytest.raises(EvaluationError, match="include a timezone"):
        validate_record(record)
    record = sample_record()
    record["user_outcomes"][0]["subject_key"] = " "
    with pytest.raises(EvaluationError, match="pseudonymous"):
        validate_record(record)


def test_edit_annotations_require_explicit_replacement_items():
    record = sample_record()
    record["human_reviews"][0]["disposition"] = "edit"
    record["human_reviews"][0]["proposed_item_ids"] = []
    with pytest.raises(EvaluationError, match="edit reviews require"):
        validate_record(record)

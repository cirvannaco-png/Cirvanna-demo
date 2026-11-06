from __future__ import annotations
import pytest
from app.outfit_evaluation import evaluate

def make_record(case_id="case-1", split="test", user="user-a"):
    return {
        "schema_version": "1.0", "case_id": case_id, "user_key": user,
        "reviewer_key": "reviewer-a", "reviewed_at": "2026-11-06T08:00:00Z",
        "split": split, "preferred_tags": ["linen", "minimal"], "excluded_tags": ["leather"],
        "candidate_pool": [
            {"candidate_id": "model-top", "item_ids": ["shirt-1", "trouser-1", "shoe-1"],
             "categories": ["top", "bottom", "shoes"], "tags": ["linen", "minimal"],
             "model_score": 0.95, "human_relevance": 5, "shown": True,
             "user_edited": True, "user_rejected": False},
            {"candidate_id": "baseline-top", "item_ids": ["shirt-2", "skirt-1", "shoe-2"],
             "categories": ["top", "bottom", "shoes"], "tags": ["cotton", "classic"],
             "model_score": 0.55, "human_relevance": 4, "shown": False,
             "user_edited": False, "user_rejected": False},
            {"candidate_id": "excluded", "item_ids": ["jacket-1", "trouser-2"],
             "categories": ["outerwear", "bottom"], "tags": ["leather", "minimal"],
             "model_score": 0.99, "human_relevance": 5, "shown": False,
             "user_edited": False, "user_rejected": False},
        ],
    }

def test_same_candidate_pool_compares_model_with_simple_baseline():
    result = evaluate([make_record()], k=2)
    metrics = result["split_metrics"]["test"]
    assert metrics["candidate_model"]["relevance_mean_at_k"] == 5.0
    assert metrics["simple_baseline"]["relevance_mean_at_k"] == 4.5
    assert metrics["candidate_model"]["exclusion_violation_rate_at_k"] == 0.5
    assert metrics["simple_baseline"]["exclusion_violation_rate_at_k"] == 0.0
    assert result["paired_model_minus_baseline"]["test"]["relevance_mean_at_k"] == 0.5

def test_edits_and_repeated_rejections_are_measured_from_observed_impressions():
    a, b = make_record("case-1"), make_record("case-2")
    for row in (a, b):
        row["candidate_pool"][0].update({"user_edited": False, "user_rejected": True, "rejection_key": "signature-1"})
    metrics = evaluate([a, b], k=1)["observed_user_outcomes"]["test"]
    assert metrics["shown_recommendation_count"] == 2
    assert metrics["user_edit_rate"] == 0.0
    assert metrics["user_rejection_count"] == 2
    assert metrics["repeated_rejection_rate_among_rejections"] == 1.0

def test_unshown_candidate_cannot_have_user_outcomes():
    row = make_record()
    row["candidate_pool"][0]["shown"] = False
    with pytest.raises(ValueError, match="must have been shown"):
        evaluate([row])

def test_rejection_requires_stable_signature():
    row = make_record()
    row["candidate_pool"][0]["user_rejected"] = True
    with pytest.raises(ValueError, match="rejection_key"):
        evaluate([row])

def test_human_rating_must_be_one_to_five():
    row = make_record()
    row["candidate_pool"][0]["human_relevance"] = 6
    with pytest.raises(ValueError, match="human rating"):
        evaluate([row])

def test_case_ids_are_unique_within_split():
    with pytest.raises(ValueError, match="unique within each split"):
        evaluate([make_record(), make_record()])

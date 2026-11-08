from __future__ import annotations

import pytest

from tools.pnelly_evaluation.prepare_pnelly_cases import prepare_cases


def _trace():
    return {
        "evaluation_trace": {
            "trace_version": "1.0",
            "candidate_pool_truncated": False,
            "privacy": {
                "raw_user_id_included": False,
                "raw_wardrobe_item_ids_included": False,
                "display_names_included": False,
                "image_assets_included": False,
            },
            "no_result_roles": ["explore"],
            "consent": {
                "required": True,
                "validated_by_gateway": True,
                "scope": "style_learning_or_personalization",
            },
            "cases": [{
                "schema_version": "1.0",
                "case_id": "case-1",
                "participant_key": "participant-pseudo-1",
                "session_id": "session-pseudo-1",
                "assigned_system": "cirvanna",
                "context": {
                    "role": "everyday", "required_categories": [],
                    "preferred_style_tags": [], "preferred_color_tags": [],
                    "occasion": "work", "climate": "warm",
                    "hard_excluded_item_ids": [], "hard_excluded_tags": [],
                },
                "candidate_outfits": [{
                    "look_id": "look-1", "garment_ids": ["garment-1"],
                    "category_tags": ["top"], "style_tags": [], "color_tags": [],
                    "occasion_tags": [], "exclusion_tags": [],
                }],
                "cirvanna_ranked_look_ids": ["look-1"],
                "human_reviews": [], "adjudications": [], "exposures": [],
            }],
        }
    }


def _two_reviews():
    return [
        {"case_id": "case-1", "look_id": "look-1", "reviewer_key": "reviewer-a",
         "relevance": 4, "exclusion_violation": False},
        {"case_id": "case-1", "look_id": "look-1", "reviewer_key": "reviewer-b",
         "relevance": 5, "exclusion_violation": False},
    ]


def _adjudication(adjudicator_key="reviewer-c"):
    return {
        "case_id": "case-1",
        "look_id": "look-1",
        "adjudicator_key": adjudicator_key,
        "relevance": 5,
        "exclusion_violation": False,
    }


def test_prepare_requires_two_distinct_blinded_reviewers_per_candidate():
    cases, summary = prepare_cases(
        [_trace()], _two_reviews(), adjudication_rows=[_adjudication()]
    )
    assert len(cases) == 1
    assert len(cases[0]["human_reviews"]) == 2
    assert cases[0]["adjudications"] == [_adjudication()]
    assert summary["no_result_roles_by_role"] == {"explore": 1}
    assert summary["review_count"] == 2
    assert summary["adjudication_count"] == 1


def test_prepare_rejects_unresolved_review_disagreement():
    with pytest.raises(ValueError, match="reviewer disagreement requires adjudication"):
        prepare_cases([_trace()], _two_reviews())


def test_prepare_requires_adjudicator_independent_of_both_reviewers():
    with pytest.raises(ValueError, match="adjudicator must be independent"):
        prepare_cases(
            [_trace()], _two_reviews(),
            adjudication_rows=[_adjudication(adjudicator_key="reviewer-a")],
        )


def test_prepare_rejects_duplicate_adjudication_for_one_candidate():
    with pytest.raises(ValueError, match="duplicate adjudication"):
        prepare_cases(
            [_trace()], _two_reviews(),
            adjudication_rows=[_adjudication(), _adjudication(adjudicator_key="reviewer-d")],
        )


def test_prepare_rejects_adjudication_for_unknown_candidate():
    wrong = dict(_adjudication(), look_id="unknown-look")
    with pytest.raises(ValueError, match="adjudication references an unknown candidate"):
        prepare_cases([_trace()], _two_reviews(), adjudication_rows=[wrong])


def test_prepare_rejects_duplicate_reviewer_and_missing_rating():
    reviews = _two_reviews()
    reviews[1]["reviewer_key"] = "reviewer-a"
    with pytest.raises(ValueError, match="exactly two distinct reviewer ratings"):
        prepare_cases([_trace()], reviews)


def test_prepare_rejects_truncated_pool_and_raw_identity():
    trace = _trace()
    trace["evaluation_trace"]["candidate_pool_truncated"] = True
    with pytest.raises(ValueError, match="truncated candidate pools"):
        prepare_cases([trace], _two_reviews())
    trace = _trace()
    trace["evaluation_trace"]["privacy"]["raw_user_id_included"] = True
    with pytest.raises(ValueError, match="privacy gate"):
        prepare_cases([trace], _two_reviews())


def test_prepare_rejects_raw_identity_in_trace_envelope():
    trace = _trace()
    trace["subject_id"] = "real-user-123"
    with pytest.raises(ValueError, match="raw user/account identifier"):
        prepare_cases([trace], _two_reviews())


def test_prepare_preserves_all_no_result_runs_without_fabricating_review_cases():
    trace = _trace()
    trace["evaluation_trace"]["cases"] = []
    trace["evaluation_trace"]["no_result_roles"] = ["everyday", "elevated", "explore"]
    cases, summary = prepare_cases([trace], [])
    assert cases == []
    assert summary["trace_count"] == 1
    assert summary["case_count"] == 0
    assert summary["no_result_roles_by_role"] == {
        "everyday": 1, "elevated": 1, "explore": 1
    }

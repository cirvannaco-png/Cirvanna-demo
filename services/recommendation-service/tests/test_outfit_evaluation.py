import pytest
from app.outfit_evaluation import evaluate

def row(case_id="case-1"):
    return {
        "schema_version":"1.0","case_id":case_id,"user_key":"pseudonym-1",
        "reviewer_key":"reviewer-1","reviewed_at":"2026-11-06T08:00:00Z","split":"test",
        "preferred_tags":["linen","minimal"],"excluded_tags":["leather"],
        "candidate_pool":[
            {"candidate_id":"model","item_ids":["top1","bottom1","shoe1"],"categories":["top","bottom","shoes"],"tags":["linen","minimal"],"model_score":0.95,"human_relevance":5,"shown":True,"user_edited":True,"user_rejected":False},
            {"candidate_id":"baseline","item_ids":["top2","bottom2","shoe2"],"categories":["top","bottom","shoes"],"tags":["cotton","classic"],"model_score":0.55,"human_relevance":4,"shown":False,"user_edited":False,"user_rejected":False},
            {"candidate_id":"excluded","item_ids":["jacket","pants"],"categories":["outerwear","bottom"],"tags":["leather"],"model_score":0.99,"human_relevance":5,"shown":False,"user_edited":False,"user_rejected":False}
        ]
    }

def test_compares_model_and_simple_baseline_on_same_pool():
    metrics=evaluate([row()],k=2)["split_metrics"]["test"]
    assert metrics["candidate_model"]["relevance_mean_at_k"] == 5
    assert metrics["simple_baseline"]["relevance_mean_at_k"] == 4.5
    assert metrics["candidate_model"]["exclusion_violation_rate_at_k"] == 0.5
    assert metrics["simple_baseline"]["exclusion_violation_rate_at_k"] == 0

def test_measures_edits_and_repeated_rejections():
    a,b=row("a"),row("b")
    for x in (a,b):
        x["candidate_pool"][0].update({"user_edited":False,"user_rejected":True,"rejection_key":"same-outfit"})
    result=evaluate([a,b],k=1)["observed_user_outcomes"]["test"]
    assert result["user_edit_rate"] == 0
    assert result["user_rejection_count"] == 2
    assert result["repeated_rejection_rate_among_rejections"] == 1

def test_rejects_outcomes_without_impression():
    x=row()
    x["candidate_pool"][0]["shown"]=False
    with pytest.raises(ValueError,match="shown impression"):
        evaluate([x])

def test_rejects_unlabelled_or_invalid_human_rating():
    x=row()
    x["candidate_pool"][0]["human_relevance"]=6
    with pytest.raises(ValueError,match="human rating"):
        evaluate([x])

def test_rejects_duplicate_case_ids():
    with pytest.raises(ValueError,match="unique within split"):
        evaluate([row(),row()])

import pytest
from app.outfit_evaluation import evaluate

def row(case_id="case-1",user="pseudonym-1"):
    return {"schema_version":"1.0","case_id":case_id,"user_key":user,"reviewed_at":"2026-11-06T08:00:00Z",
      "split":"test","preferred_tags":["linen","minimal"],"excluded_tags":["leather"],"candidate_pool":[
       {"candidate_id":"model","item_ids":["top1","bottom1","shoe1"],"categories":["top","bottom","shoes"],"tags":["linen","minimal"],
        "model_score":0.95,"human_reviews":[{"reviewer_key":"reviewer-a","relevance":5},{"reviewer_key":"reviewer-b","relevance":5}],
        "shown":True,"user_edited":True,"user_rejected":False},
       {"candidate_id":"baseline","item_ids":["top2","bottom2","shoe2"],"categories":["top","bottom","shoes"],"tags":["cotton","classic"],
        "model_score":0.55,"human_reviews":[{"reviewer_key":"reviewer-a","relevance":4},{"reviewer_key":"reviewer-b","relevance":4}],
        "shown":False,"user_edited":False,"user_rejected":False},
       {"candidate_id":"excluded","item_ids":["jacket","pants"],"categories":["outerwear","bottom"],"tags":["leather"],
        "model_score":0.99,"human_reviews":[{"reviewer_key":"reviewer-a","relevance":5},{"reviewer_key":"reviewer-b","relevance":5}],
        "shown":False,"user_edited":False,"user_rejected":False}]}

def test_compares_ranker_and_baseline_on_same_human_reviewed_pool():
    metrics=evaluate([row()],k=2)["split_metrics"]["test"]
    assert metrics["candidate_model"]["relevance_mean_at_k"]==5
    assert metrics["simple_baseline"]["relevance_mean_at_k"]==4.5
    assert metrics["candidate_model"]["exclusion_violation_rate_at_k"]==0.5
    assert metrics["simple_baseline"]["exclusion_violation_rate_at_k"]==0

def test_measures_observed_edits_and_repeated_rejections():
    a,b=row("a"),row("b")
    for x in (a,b): x["candidate_pool"][0].update({"user_edited":False,"user_rejected":True,"rejection_key":"same-outfit"})
    result=evaluate([a,b],k=1)["observed_user_outcomes"]["test"]
    assert result["user_edit_rate"]==0
    assert result["user_rejection_count"]==2
    assert result["repeated_rejection_rate_among_rejections"]==1

def test_requires_two_distinct_blinded_reviewers_per_candidate():
    x=row(); x["candidate_pool"][0]["human_reviews"]=[{"reviewer_key":"one","relevance":4}]
    with pytest.raises(ValueError,match="two independent"): evaluate([x])

def test_reviewer_keys_must_be_distinct():
    x=row(); x["candidate_pool"][0]["human_reviews"][1]["reviewer_key"]="reviewer-a"
    with pytest.raises(ValueError,match="unique per candidate"): evaluate([x])

def test_rejects_user_outcomes_without_shown_impression():
    x=row(); x["candidate_pool"][0]["shown"]=False
    with pytest.raises(ValueError,match="shown impression"): evaluate([x])

def test_rejection_requires_stable_signature():
    x=row(); x["candidate_pool"][0].update({"user_rejected":True,"rejection_key":""})
    with pytest.raises(ValueError,match="rejection_key"): evaluate([x])

def test_human_rating_must_be_integer_one_to_five():
    x=row(); x["candidate_pool"][0]["human_reviews"][0]["relevance"]=6
    with pytest.raises(ValueError,match="1-5"): evaluate([x])

def test_participant_must_not_leak_across_splits():
    a=row("a"); b=row("b"); b["split"]="train"
    with pytest.raises(ValueError,match="participant leakage"): evaluate([a,b])

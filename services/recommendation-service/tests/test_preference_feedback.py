import pytest

from app.preference_feedback import build_preference_feedback_event


def payload(action, **extra):
    value = {
        "event_id": "evt-123",
        "request_id": "req-1",
        "user_id": "user-1",
        "recommendation_id": "rec-1",
        "dimension": "aesthetic",
        "action": action,
        "value": "bold",
        "learning_consent": True,
    }
    value.update(extra)
    return value


def test_approved_feedback_routes_to_usi_tal():
    result = build_preference_feedback_event(payload("approved"))
    assert result["events"][0]["owner"] == "USI/TAL"
    assert result["events"][0]["event_kind"] == "positive_preference_evidence"
    assert result["persistence"] == "not_connected"


def test_rejection_routes_to_npl_but_does_not_hard_block_itself():
    result = build_preference_feedback_event(payload("rejected"))
    assert result["events"][0]["owner"] == "NPL"
    assert result["events"][0]["event_kind"] == "negative_recommendation_evidence"
    assert "does not create a permanent hard exclusion" in result["explanation"]


def test_modified_feedback_records_original_rejection_and_new_approval():
    result = build_preference_feedback_event(payload("modified", modified_value="classic"))
    assert [item["owner"] for item in result["events"]] == ["NPL", "USI/TAL"]
    assert result["events"][0]["target_value"] == "bold"
    assert result["events"][1]["target_value"] == "classic"
    assert result["events"][0]["event_id"] != result["events"][1]["event_id"]


def test_not_relevant_does_not_change_preference():
    result = build_preference_feedback_event(payload("not_relevant"))
    assert result["events"] == []


def test_feedback_requires_consent():
    request = payload("approved")
    request["learning_consent"] = False
    with pytest.raises(ValueError, match="consent"):
        build_preference_feedback_event(request)

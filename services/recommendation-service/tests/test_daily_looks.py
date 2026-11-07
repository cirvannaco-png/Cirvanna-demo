from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.daily_looks import build_daily_looks, _kind
from app.main import app


TOKEN = "complementer-internal-token-that-is-at-least-32-bytes"


def wardrobe():
    owner = "user-123"
    return [
        {"item_id": "top-001", "owner_user_id": owner, "display_name": "Linen shirt", "category": "tops", "attributes": ["blue", "linen", "casual"], "status": "active"},
        {"item_id": "top-002", "owner_user_id": owner, "display_name": "Silk blouse", "category": "blouses", "attributes": ["cream", "silk", "formal"], "status": "active"},
        {"item_id": "top-003", "owner_user_id": owner, "display_name": "Printed tee", "category": "t-shirts", "attributes": ["pattern", "bold"], "status": "active"},
        {"item_id": "bottom-01", "owner_user_id": owner, "display_name": "Dark trousers", "category": "trousers", "attributes": ["black", "work"], "status": "active"},
        {"item_id": "bottom-02", "owner_user_id": owner, "display_name": "Cotton skirt", "category": "skirts", "attributes": ["olive", "casual"], "status": "active"},
        {"item_id": "shoe-001", "owner_user_id": owner, "display_name": "Leather flats", "category": "footwear", "attributes": ["black"], "status": "active"},
        {"item_id": "archived-1", "owner_user_id": owner, "display_name": "Old jacket", "category": "outerwear", "attributes": [], "status": "archived"},
    ]


def test_expanded_wardrobe_accessories_are_classified_as_look_complements():
    for category in (
        "bags", "jewelry", "ties", "eyewear", "watches", "belts",
        "scarves", "hats", "hair_accessories", "socks", "makeup",
        "fragrance", "haircare",
    ):
        assert _kind({"category": category, "attributes": []}) == "accessory"


def test_builds_exactly_three_distinct_looks_from_active_owner_items():
    result = build_daily_looks(
        request_id="daily-001",
        user_id="user-123",
        wardrobe_items=wardrobe(),
        local_date="2026-11-05",
        occasion="work",
        climate="hot_dry",
        style_signals=["formal"],
    )
    assert result["look_count"] == 3
    assert [look["role"] for look in result["looks"]] == ["everyday", "elevated", "explore"]
    assert result["ready_count"] == 3
    combinations = [frozenset(look["item_ids"]) for look in result["looks"]]
    assert len(set(combinations)) == 3
    assert all(look["status"] == "ready" for look in result["looks"])
    assert all("archived-1" not in look["item_ids"] for look in result["looks"])
    assert all(look["virtual_twin_preview"]["status"] == "unavailable" for look in result["looks"])


def test_never_fabricates_a_look_when_wardrobe_is_insufficient():
    result = build_daily_looks(
        request_id="daily-002",
        user_id="user-123",
        wardrobe_items=[wardrobe()[0]],
        local_date="2026-11-05",
    )
    assert result["look_count"] == 3
    assert result["ready_count"] == 0
    assert all(look["status"] == "needs_input" for look in result["looks"])
    assert all(look["item_ids"] == [] for look in result["looks"])
    assert all(look["missing"] for look in result["looks"])


def test_a_second_role_is_not_filled_by_duplicating_a_single_outfit():
    items = wardrobe()[:1] + wardrobe()[3:4]
    result = build_daily_looks(
        request_id="daily-003",
        user_id="user-123",
        wardrobe_items=items,
        local_date="2026-11-05",
    )
    assert result["ready_count"] == 1
    assert [look["status"] for look in result["looks"]] == ["ready", "needs_input", "needs_input"]


def test_foreign_owner_is_rejected():
    items = wardrobe()
    items[0]["owner_user_id"] = "another-user"
    with pytest.raises(PermissionError):
        build_daily_looks(
            request_id="daily-004",
            user_id="user-123",
            wardrobe_items=items,
            local_date="2026-11-05",
        )


def test_duplicate_ids_and_invalid_dates_are_rejected(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    items = wardrobe()
    items.append(dict(items[0]))
    with pytest.raises(ValueError, match="duplicate"):
        build_daily_looks(
            request_id="daily-005",
            user_id="user-123",
            wardrobe_items=items,
            local_date="2026-11-05",
        )

    client = TestClient(app)
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "request_id": "daily-006",
            "user_id": "user-123",
            "local_date": "05-11-2026",
            "wardrobe_items": [],
        },
    )
    assert response.status_code == 422


def test_api_requires_internal_authentication_and_rejects_cross_owner_items(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    client = TestClient(app)
    body = {
        "request_id": "daily-007",
        "user_id": "user-123",
        "local_date": "2026-11-05",
        "wardrobe_items": wardrobe(),
    }
    assert client.post("/v1/pnelly/daily-looks", json=body).status_code == 401

    body["wardrobe_items"][0]["owner_user_id"] = "another-user"
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "WARDROBE_SUBJECT_MISMATCH"


def test_capabilities_report_preview_is_not_enabled():
    data = TestClient(app).get("/capabilities").json()
    assert data["pnelly_daily_look_orchestration"] is True
    assert data["pnelly_daily_look_roles"] == ["everyday", "elevated", "explore"]
    assert data["virtual_twin_preview_enabled"] is False


def test_category_values_used_by_wardrobe_ui_are_recognized():
    items = [
        {"item_id": "top-101", "owner_user_id": "user-123", "display_name": "Linen shirt", "category": "tops", "attributes": [], "status": "active"},
        {"item_id": "bottom-101", "owner_user_id": "user-123", "display_name": "Linen trousers", "category": "lower_body", "attributes": [], "status": "active"},
    ]
    result = build_daily_looks(
        request_id="daily-ui-category",
        user_id="user-123",
        wardrobe_items=items,
        local_date="2026-11-05",
    )
    assert result["ready_count"] == 1
    assert result["looks"][0]["item_ids"]
    assert "bottom-101" in result["looks"][0]["item_ids"]


def test_declared_occasion_changes_look_ranking():
    items = [
        {"item_id": "casual-top", "owner_user_id": "user-123", "display_name": "Casual tee", "category": "tops", "attributes": ["casual"], "status": "active"},
        {"item_id": "work-top", "owner_user_id": "user-123", "display_name": "Tailored blouse", "category": "tops", "attributes": ["work", "formal", "tailored"], "status": "active"},
        {"item_id": "bottom-10", "owner_user_id": "user-123", "display_name": "Straight trousers", "category": "trousers", "attributes": [], "status": "active"},
    ]
    result = build_daily_looks(
        request_id="daily-work-context",
        user_id="user-123",
        wardrobe_items=items,
        local_date="2026-11-05",
        occasion="work",
    )
    assert "work-top" in result["looks"][0]["item_ids"]
    assert "declared occasion (work)" in result["looks"][0]["reason"]


def test_declared_climate_changes_look_ranking():
    items = [
        {"item_id": "linen-top", "owner_user_id": "user-123", "display_name": "Linen blouse", "category": "tops", "attributes": ["linen", "breathable", "lightweight"], "status": "active"},
        {"item_id": "wool-top", "owner_user_id": "user-123", "display_name": "Wool sweater", "category": "tops", "attributes": ["wool", "heavy"], "status": "active"},
        {"item_id": "bottom-11", "owner_user_id": "user-123", "display_name": "Cotton trousers", "category": "trousers", "attributes": [], "status": "active"},
    ]
    result = build_daily_looks(
        request_id="daily-climate-context",
        user_id="user-123",
        wardrobe_items=items,
        local_date="2026-11-05",
        climate="hot_humid",
    )
    assert "linen-top" in result["looks"][0]["item_ids"]
    assert "declared climate (hot humid)" in result["looks"][0]["reason"]


def test_consent_based_feedback_signal_changes_look_ranking():
    items = [
        {"item_id": "plain-top", "owner_user_id": "user-123", "display_name": "Plain shirt", "category": "tops", "attributes": [], "status": "active"},
        {"item_id": "teal-top", "owner_user_id": "user-123", "display_name": "Teal shirt", "category": "tops", "attributes": ["teal"], "status": "active"},
        {"item_id": "bottom-12", "owner_user_id": "user-123", "display_name": "Straight trousers", "category": "trousers", "attributes": [], "status": "active"},
    ]
    result = build_daily_looks(
        request_id="daily-feedback-context",
        user_id="user-123",
        wardrobe_items=items,
        local_date="2026-11-05",
        feedback_signals=["feedback:teal"],
    )
    assert "teal-top" in result["looks"][0]["item_ids"]
    assert result["personalization"]["feedback_signals_used"] is True
    assert result["personalization"]["feedback_source"] == "consented_wardrobe_feedback"
    assert "consented like/wear feedback: teal" in result["looks"][0]["reason"]


def test_legacy_tari_route_remains_a_hidden_compatibility_alias(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    client = TestClient(app)
    body = {"request_id": "daily-legacy-alias", "user_id": "user-123", "local_date": "2026-11-06", "wardrobe_items": wardrobe()}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    canonical = client.post("/v1/pnelly/daily-looks", headers=headers, json=body)
    legacy = client.post("/v1/tari/daily-looks", headers=headers, json=body)
    assert canonical.status_code == legacy.status_code == 200
    assert canonical.json() == legacy.json()



def test_evaluation_trace_is_opt_in_pseudonymous_and_role_specific():
    import json
    items = wardrobe()
    excluded_id = "top-002"
    eligible = [item for item in items if item["item_id"] != excluded_id]
    result = build_daily_looks(
        request_id="daily-eval-001",
        user_id="user-123",
        wardrobe_items=eligible,
        evaluation_wardrobe_items=items,
        hard_excluded_item_ids=[excluded_id],
        local_date="2026-11-05",
        occasion="work",
        climate="hot_dry",
        style_signals=["style:editorial", "color:teal"],
        evaluation_trace_enabled=True,
        evaluation_secret="pnelly-evaluation-hmac-secret-with-at-least-32-bytes",
    )
    trace = result["evaluation_trace"]
    assert trace["trace_version"] == "1.0"
    assert trace["human_review_state"] == "awaiting_two_independent_reviewers_per_candidate"
    assert trace["user_exposure_state"] == "not_collected_by_composer"
    assert trace["privacy"]["raw_user_id_included"] is False
    assert trace["privacy"]["raw_wardrobe_item_ids_included"] is False
    assert trace["privacy"]["display_names_included"] is False
    assert [case["context"]["role"] for case in trace["cases"]] == ["everyday", "elevated", "explore"]
    for case in trace["cases"]:
        assert case["assigned_system"] == "cirvanna"
        assert case["participant_key"].startswith("participant_")
        assert case["session_id"].startswith("session_")
        assert case["context"]["preferred_style_tags"] == ["editorial"]
        assert case["context"]["preferred_color_tags"] == ["teal"]
        assert case["context"]["hard_excluded_item_ids"]
        assert case["cirvanna_ranked_look_ids"]
    payload = json.dumps(trace, sort_keys=True)
    for raw_value in ("user-123", "top-001", "top-002", "Linen shirt", "Silk blouse"):
        assert raw_value not in payload
    for role, ranking in trace["ranking_trace_by_role"].items():
        case = next(row for row in trace["cases"] if row["context"]["role"] == role)
        assert case["cirvanna_ranked_look_ids"][0] == ranking[0]["look_id"]
        blocked = set(trace["hard_excluded_candidate_ids_by_role"][role])
        assert blocked.isdisjoint(case["cirvanna_ranked_look_ids"])
        candidates = {row["look_id"]: row for row in case["candidate_outfits"]}
        excluded_token = case["context"]["hard_excluded_item_ids"][0]
        assert any(
            excluded_token in candidate["garment_ids"]
            for look_id in blocked
            for candidate in [candidates[look_id]]
        )


def test_evaluation_trace_is_absent_when_feature_flag_is_disabled():
    result = build_daily_looks(
        request_id="daily-eval-disabled",
        user_id="user-123",
        wardrobe_items=wardrobe(),
        local_date="2026-11-05",
    )
    assert "evaluation_trace" not in result


def test_evaluation_trace_requires_a_sufficient_pseudonymization_secret():
    with pytest.raises(ValueError, match="pseudonymization secret"):
        build_daily_looks(
            request_id="daily-eval-short-secret",
            user_id="user-123",
            wardrobe_items=wardrobe(),
            local_date="2026-11-05",
            evaluation_trace_enabled=True,
            evaluation_secret="short",
        )


def test_evaluation_trace_api_is_server_flagged_and_fails_closed_without_secret(monkeypatch):
    token = "pnelly-evaluation-api-test-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", token)
    monkeypatch.setenv("PNELLY_EVALUATION_TRACE_ENABLED", "true")
    monkeypatch.delenv("PNELLY_EVALUATION_TRACE_HMAC_SECRET", raising=False)
    client = TestClient(app)
    body = {
        "request_id": "daily-eval-api",
        "user_id": "user-123",
        "local_date": "2026-11-05",
        "wardrobe_items": wardrobe(),
    }
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PNELLY_EVALUATION_TRACE_SIGNING_NOT_CONFIGURED"

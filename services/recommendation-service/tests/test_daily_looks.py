from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.daily_looks import build_daily_looks
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
        "/v1/tari/daily-looks",
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
    assert client.post("/v1/tari/daily-looks", json=body).status_code == 401

    body["wardrobe_items"][0]["owner_user_id"] = "another-user"
    response = client.post(
        "/v1/tari/daily-looks",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "WARDROBE_SUBJECT_MISMATCH"


def test_capabilities_report_preview_is_not_enabled():
    data = TestClient(app).get("/capabilities").json()
    assert data["tari_daily_look_orchestration"] is True
    assert data["tari_daily_look_roles"] == ["everyday", "elevated", "explore"]
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

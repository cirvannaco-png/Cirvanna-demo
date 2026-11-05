from app.daily_looks import build_daily_looks


def item(item_id, category, name=None, attributes=None, status="active"):
    return {
        "item_id": item_id,
        "owner_user_id": "user-1",
        "display_name": name or item_id,
        "category": category,
        "attributes": attributes or [],
        "status": status,
    }


def test_daily_looks_returns_three_roles_without_repeating_outfits():
    result = build_daily_looks([
        item("top-1", "tops", "Blue shirt", ["blue"]),
        item("top-2", "tops", "White shirt", ["white"]),
        item("bottom-1", "lower_body", "Black trousers", ["black", "formal"]),
        item("bottom-2", "lower_body", "Jeans", ["blue", "casual"]),
        item("shoe-1", "shoes", "Sneakers"),
    ], occasion="work")
    assert [look["role"] for look in result["looks"]] == ["Everyday", "Elevated", "Explore"]
    assert result["ready_count"] == 3
    combinations = [tuple(sorted(piece["item_id"] for piece in look["items"])) for look in result["looks"]]
    assert len(set(combinations)) == 3
    assert all("work" in look["reason"].lower() for look in result["looks"])


def test_daily_looks_never_use_draft_items_or_invent_missing_pieces():
    result = build_daily_looks([
        item("top-1", "tops", "Draft top", status="draft"),
        item("bottom-1", "lower_body", "Active trousers"),
        item("shoe-1", "shoes", "Active shoes"),
    ])
    assert result["ready_count"] == 0
    assert all(look["status"] == "needs_items" for look in result["looks"])
    assert all(look["items"] == [] for look in result["looks"])
    assert all(look["missing"] for look in result["looks"])


def test_daily_looks_withhold_duplicate_outfits_when_wardrobe_is_small():
    result = build_daily_looks([
        item("dress-1", "dress", "Black dress"),
        item("shoe-1", "shoes", "Black shoes"),
    ])
    assert result["ready_count"] == 1
    assert result["looks"][0]["status"] == "ready"
    assert result["looks"][1]["status"] == "needs_items"
    assert "additional distinct wardrobe pieces for another unique combination" in result["looks"][1]["missing"]


def test_daily_looks_ignore_non_active_and_malformed_records():
    result = build_daily_looks([
        item("dress-1", "dress", "Blue dress"),
        item("shoe-1", "shoes", "Sneakers"),
        {"item_id": "broken", "status": "active"},
        item("archived-top", "tops", "Archived top", status="archived"),
    ])
    assert result["ready_count"] == 1
    assert all(piece["item_id"] not in {"broken", "archived-top"} for look in result["looks"] for piece in look["items"])

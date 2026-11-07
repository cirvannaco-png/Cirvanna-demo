from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.store import Base, WardrobeRow, engine_for_url


def configured_client(monkeypatch, tmp_path):
    database = tmp_path / "wardrobe-rotation.db"
    monkeypatch.setenv("WARDROBE_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("WARDROBE_ALLOW_SQLITE_TESTS", "1")
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "wardrobe-rotation-test-token-more-than-32-bytes")
    engine = engine_for_url(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all([
            WardrobeRow(
                owner_user_id="user-a", item_id="shirt-a", display_name="Linen shirt",
                category="tops", attributes=["linen", "blue"], status="active", version=1,
            ),
            WardrobeRow(
                owner_user_id="user-b", item_id="shirt-b", display_name="Cotton shirt",
                category="tops", attributes=["cotton", "white"], status="active", version=1,
            ),
        ])
    return TestClient(main.app), {"Authorization": "Bearer wardrobe-rotation-test-token-more-than-32-bytes"}


def test_rotation_state_round_trip_is_owner_scoped_and_versioned(monkeypatch, tmp_path):
    client, headers = configured_client(monkeypatch, tmp_path)
    initial = client.get("/v1/rotation-state?owner_user_id=user-a", headers=headers)
    assert initial.status_code == 200
    assert initial.json() == {"state": None, "version": 0}

    payload = {
        "owner_user_id": "user-a", "request_id": "rotation-request-001", "expected_version": 0, "cycle_number": 1,
        "cycle_started_at": "2026-11-07T00:00:00Z", "surfaced_item_ids": ["shirt-a"],
    }
    created = client.put("/v1/rotation-state", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert created.json()["state"]["surfaced_item_ids"] == ["shirt-a"]

    own = client.get("/v1/rotation-state?owner_user_id=user-a", headers=headers)
    other = client.get("/v1/rotation-state?owner_user_id=user-b", headers=headers)
    assert own.json()["state"]["surfaced_item_ids"] == ["shirt-a"]
    assert other.json() == {"state": None, "version": 0}


def test_rotation_state_rejects_stale_writes_and_unowned_items(monkeypatch, tmp_path):
    client, headers = configured_client(monkeypatch, tmp_path)
    payload = {
        "owner_user_id": "user-a", "request_id": "rotation-request-002", "expected_version": 0, "cycle_number": 1,
        "cycle_started_at": "2026-11-07T00:00:00Z", "surfaced_item_ids": ["shirt-a"],
    }
    assert client.put("/v1/rotation-state", headers=headers, json=payload).status_code == 200
    stale = client.put("/v1/rotation-state", headers=headers, json={**payload, "request_id": "rotation-request-stale"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "WARDROBE_ROTATION_VERSION_CONFLICT"

    foreign = {**payload, "request_id": "rotation-request-foreign", "expected_version": 1, "surfaced_item_ids": ["shirt-b"]}
    rejected = client.put("/v1/rotation-state", headers=headers, json=foreign)
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "ROTATION_ITEMS_NOT_ACTIVE_OR_NOT_OWNED"



def test_rotation_put_replays_identical_request_without_incrementing_version(monkeypatch, tmp_path):
    client, headers = configured_client(monkeypatch, tmp_path)
    payload = {
        "owner_user_id": "user-a", "request_id": "rotation-request-replay",
        "expected_version": 0, "cycle_number": 1,
        "cycle_started_at": "2026-11-07T00:00:00Z", "surfaced_item_ids": ["shirt-a"],
    }
    created = client.put("/v1/rotation-state", headers=headers, json=payload)
    replayed = client.put("/v1/rotation-state", headers=headers, json=payload)
    assert created.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "replayed"
    assert replayed.json()["version"] == 1

    changed = {**payload, "surfaced_item_ids": []}
    conflict = client.put("/v1/rotation-state", headers=headers, json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "WARDROBE_ROTATION_IDEMPOTENCY_CONFLICT"


def test_rotation_state_requires_timezone_and_supports_erasure(monkeypatch, tmp_path):
    client, headers = configured_client(monkeypatch, tmp_path)
    payload = {
        "owner_user_id": "user-a", "request_id": "rotation-request-003", "expected_version": 0, "cycle_number": 1,
        "cycle_started_at": "2026-11-07T00:00:00", "surfaced_item_ids": [],
    }
    invalid = client.put("/v1/rotation-state", headers=headers, json=payload)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "ROTATION_TIMESTAMP_REQUIRES_TIMEZONE"

    payload["cycle_started_at"] = "2026-11-07T00:00:00Z"
    assert client.put("/v1/rotation-state", headers=headers, json=payload).status_code == 200
    erased = client.delete("/v1/rotation-state?owner_user_id=user-a", headers=headers)
    assert erased.status_code == 200
    assert client.get("/v1/rotation-state?owner_user_id=user-a", headers=headers).json() == {
        "state": None, "version": 0,
    }

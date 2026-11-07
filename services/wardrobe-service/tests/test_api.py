from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app import main
from app.store import Base, WardrobeDeletionQueue, engine_for_url

TOKEN="wardrobe-test-token-more-than-32-bytes-long"

@pytest.fixture
def client(monkeypatch,tmp_path):
    url=f"sqlite:///{tmp_path / 'wardrobe.sqlite'}"
    monkeypatch.setenv("WARDROBE_DATABASE_URL",url)
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN",TOKEN)
    monkeypatch.setenv("WARDROBE_ALLOW_SQLITE_TESTS","1")
    monkeypatch.setenv("WARDROBE_ASSET_DELETION_READY","true")
    engine=engine_for_url(url)
    Base.metadata.create_all(engine)
    WardrobeDeletionQueue(engine).heartbeat("ci-test-worker")
    with TestClient(main.app) as c:
        yield c
    engine.dispose()

def auth():
    return {"Authorization":f"Bearer {TOKEN}"}

def create(client,**overrides):
    body={"owner_user_id":"user-1","item_id":"item-001","display_name":"Blue shirt","category":"tops","attributes":["blue","cotton"],"image_asset_id":"asset-001","image_storage_consent":True}
    body.update(overrides)
    response=client.post("/v1/items",headers=auth(),json=body)
    assert response.status_code==201,response.text
    return response.json()["item"]

def transition(client,item_id="item-001",**overrides):
    body={"owner_user_id":"user-1","expected_version":1,"target_status":"active","command_id":"command-001"}
    body.update(overrides)
    return client.post(f"/v1/items/{item_id}/transition",headers=auth(),json=body)

def test_readiness_requires_configured_schema_and_asset_deletion_worker(client):
    result=client.get("/ready")
    assert result.status_code==200,result.text
    assert result.json()["ready"] and result.json()["schema_ready"]

def test_api_requires_internal_auth(client):
    assert client.get("/v1/items",params={"owner_user_id":"user-1"}).status_code==401

def test_image_asset_requires_storage_consent(client):
    response=client.post("/v1/items",headers=auth(),json={"owner_user_id":"user-1","item_id":"item-001","display_name":"Blue shirt","category":"tops","image_asset_id":"asset-001","image_storage_consent":False})
    assert response.status_code==422

def test_arbitrary_image_urls_are_not_asset_ids(client):
    response=client.post("/v1/items",headers=auth(),json={"owner_user_id":"user-1","item_id":"item-001","display_name":"Blue shirt","category":"tops","image_asset_id":"https://example.invalid/p.jpg","image_storage_consent":True})
    assert response.status_code==422

def test_items_are_user_scoped(client):
    create(client,owner_user_id="user-1")
    assert client.get("/v1/items",headers=auth(),params={"owner_user_id":"user-2"}).json()["items"]==[]
    assert client.get("/v1/items/item-001",headers=auth(),params={"owner_user_id":"user-2"}).status_code==404

def test_lifecycle_version_check_and_delete_outbox(client):
    create(client)
    activated=transition(client).json()["item"]
    assert activated["status"]=="active" and activated["version"]==2
    stale=transition(client,expected_version=1,target_status="archived",command_id="command-002")
    assert stale.status_code==409
    deleted=transition(client,expected_version=2,target_status="deleted",command_id="command-003")
    assert deleted.status_code==200,deleted.text
    result=deleted.json()
    assert result["item"]["status"]=="deleted" and result["item"]["version"]==3
    assert result["asset_deletion_queued"] is True
    from sqlalchemy import select
    from app.store import AssetDeletionOutboxRow
    from app.main import store
    with store().engine.connect() as conn:
        row=conn.execute(select(AssetDeletionOutboxRow).where(AssetDeletionOutboxRow.item_id=="item-001")).first()
    assert row is not None and row.state=="pending" and row.asset_id=="asset-001"

def test_same_command_is_idempotent(client):
    create(client)
    first=transition(client)
    assert first.status_code==200
    repeated=transition(client,expected_version=1)
    assert repeated.status_code==200
    assert repeated.json()["item"]["version"]==2

def test_readiness_requires_a_recent_worker_heartbeat(client):
    from app.main import store
    from app.store import WorkerHeartbeatRow
    with store().engine.begin() as conn:
        conn.execute(WorkerHeartbeatRow.__table__.delete())
    response=client.get("/ready")
    assert response.status_code==503
    assert response.json()["detail"]["asset_deletion_worker_heartbeat_fresh"] is False


def test_readiness_does_not_accept_sqlite_without_test_override(client,monkeypatch):
    monkeypatch.delenv("WARDROBE_ALLOW_SQLITE_TESTS",raising=False)
    result=client.get("/ready")
    assert result.status_code==503
    assert result.json()["detail"]["ready"] is False


def test_feedback_requires_an_active_wardrobe_item(client, monkeypatch):
    called = []
    monkeypatch.setattr(main, "deliver_learning_event", lambda **kwargs: called.append(kwargs))
    response = client.post("/v1/feedback", headers=auth(), json={
        "owner_user_id": "user-1",
        "item_id": "missing-item",
        "event_id": "feedback-event-001",
        "signal": "like",
        "consent_receipt_id": "receipt-style-001",
        "observed_at": "2026-11-05T03:00:00Z",
    })
    assert response.status_code == 404
    assert called == []


def test_feedback_is_committed_to_tal_and_npl_with_explicit_consent(client, monkeypatch):
    create(client)
    transition(client)
    delivered = []
    def fake_delivery(**kwargs):
        delivered.append(kwargs)
        return {"tal_event_id": kwargs["event_id"], "tal_status": "recorded", "npl": {"hard_veto": False}}
    monkeypatch.setattr(main, "deliver_learning_event", fake_delivery)
    response = client.post("/v1/feedback", headers=auth(), json={
        "owner_user_id": "user-1",
        "item_id": "item-001",
        "event_id": "feedback-event-001",
        "signal": "dislike",
        "consent_receipt_id": "receipt-style-001",
        "target_type": "attribute",
        "target_value": "blue",
        "observed_at": "2026-11-05T03:00:00Z",
    })
    assert response.status_code == 201, response.text
    assert response.json()["delivery_state"] == "delivered"
    assert delivered[0]["owner_user_id"] == "user-1"
    assert delivered[0]["target_value"] == "blue"
    from app.store import WardrobeFeedbackEventRow
    with main.Session(main.store().engine) as session:
        row = session.get(WardrobeFeedbackEventRow, ("user-1", "feedback-event-001"))
        assert row is not None and row.delivery_state == "delivered"


def test_feedback_replay_is_idempotent_and_changed_replay_conflicts(client, monkeypatch):
    create(client)
    transition(client)
    calls = []
    monkeypatch.setattr(main, "deliver_learning_event", lambda **kwargs: calls.append(kwargs) or {"tal_status": "recorded"})
    body = {
        "owner_user_id": "user-1",
        "item_id": "item-001",
        "event_id": "feedback-event-002",
        "signal": "like",
        "consent_receipt_id": "receipt-style-001",
        "observed_at": "2026-11-05T03:00:00Z",
    }
    first = client.post("/v1/feedback", headers=auth(), json=body)
    replay = client.post("/v1/feedback", headers=auth(), json=body)
    conflict = client.post("/v1/feedback", headers=auth(), json={**body, "signal": "wear"})
    assert first.status_code == 201 and replay.status_code == 201
    assert replay.json()["status"] == "replayed"
    assert conflict.status_code == 409
    assert len(calls) == 1


def test_negative_attribute_feedback_must_match_owned_item(client, monkeypatch):
    create(client)
    transition(client)
    called = []
    monkeypatch.setattr(main, "deliver_learning_event", lambda **kwargs: called.append(kwargs))
    response = client.post("/v1/feedback", headers=auth(), json={
        "owner_user_id": "user-1",
        "item_id": "item-001",
        "event_id": "feedback-event-003",
        "signal": "avoid",
        "consent_receipt_id": "receipt-style-001",
        "target_type": "attribute",
        "target_value": "leather",
        "observed_at": "2026-11-05T03:00:00Z",
    })
    assert response.status_code == 422
    assert called == []


def test_feedback_audit_is_user_scoped(client, monkeypatch):
    create(client)
    transition(client)
    monkeypatch.setattr(main, "deliver_learning_event", lambda **kwargs: {"tal_status": "recorded"})
    body = {
        "owner_user_id": "user-1", "item_id": "item-001",
        "event_id": "feedback-event-004", "signal": "like",
        "consent_receipt_id": "receipt-style-001",
        "observed_at": "2026-11-05T03:00:00Z",
    }
    assert client.post("/v1/feedback", headers=auth(), json=body).status_code == 201
    own = client.get("/v1/feedback", headers=auth(), params={"owner_user_id": "user-1"})
    other = client.get("/v1/feedback", headers=auth(), params={"owner_user_id": "user-2"})
    assert len(own.json()["items"]) == 1
    assert other.json()["items"] == []



def test_feedback_audit_deletion_is_user_scoped_and_idempotent(client):
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session
    from app.store import WardrobeFeedbackEventRow
    from app.main import store

    engine = store().engine
    with Session(engine) as session, session.begin():
        session.add_all([
            WardrobeFeedbackEventRow(
                owner_user_id="user-1", event_id="feedback-user-1", item_id="item-1",
                item_version=1, signal="like", target_type=None, target_value=None,
                consent_receipt_id="receipt-style-1", payload_hash="a" * 64,
                delivery_state="delivered", delivery_result={"tal_status": "recorded"},
                error_code=None, observed_at=datetime.now(timezone.utc),
            ),
            WardrobeFeedbackEventRow(
                owner_user_id="user-2", event_id="feedback-user-2", item_id="item-2",
                item_version=1, signal="avoid", target_type="item", target_value="item-2",
                consent_receipt_id="receipt-style-2", payload_hash="b" * 64,
                delivery_state="delivered", delivery_result={"npl": {"hard_veto": True}},
                error_code=None, observed_at=datetime.now(timezone.utc),
            ),
        ])

    deleted = client.delete(
        "/v1/feedback",
        headers=auth(),
        params={"owner_user_id": "user-1"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_feedback_events"] == 1
    repeated = client.delete(
        "/v1/feedback",
        headers=auth(),
        params={"owner_user_id": "user-1"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["deleted_feedback_events"] == 0
    own = client.get("/v1/feedback", headers=auth(), params={"owner_user_id": "user-1"})
    other = client.get("/v1/feedback", headers=auth(), params={"owner_user_id": "user-2"})
    assert own.json()["items"] == []
    assert len(other.json()["items"]) == 1
    assert other.json()["items"][0]["event_id"] == "feedback-user-2"


def test_feedback_audit_deletion_requires_internal_auth(client):
    response = client.delete("/v1/feedback", params={"owner_user_id": "user-1"})
    assert response.status_code == 401


def test_edit_one_wardrobe_item_updates_only_selected_item_and_increments_version(client):
    create(client)
    response = client.patch("/v1/items/item-001", headers=auth(), json={
        "owner_user_id": "user-1", "expected_version": 1, "command_id": "edit-command-001",
        "display_name": "Blue linen shirt", "attributes": ["blue", "linen", "relaxed"],
    })
    assert response.status_code == 200, response.text
    item = response.json()["item"]
    assert item["display_name"] == "Blue linen shirt"
    assert item["attributes"] == ["blue", "linen", "relaxed"]
    assert item["version"] == 2
    assert item["category"] == "tops"
    assert client.get("/v1/items/item-001", headers=auth(), params={"owner_user_id": "user-2"}).status_code == 404


def test_edit_rejects_stale_version_and_supports_exact_idempotent_replay(client):
    create(client)
    body = {"owner_user_id": "user-1", "expected_version": 1, "command_id": "edit-command-002", "category": "outerwear"}
    first = client.patch("/v1/items/item-001", headers=auth(), json=body)
    replay = client.patch("/v1/items/item-001", headers=auth(), json=body)
    conflict = client.patch("/v1/items/item-001", headers=auth(), json={**body, "category": "tops"})
    assert first.status_code == 200
    assert replay.status_code == 200 and replay.json()["status"] == "replayed"
    assert replay.json()["item"]["version"] == 2
    assert conflict.status_code == 409


def test_edit_rejects_empty_duplicate_attributes_and_deleted_items(client):
    create(client)
    empty = client.patch("/v1/items/item-001", headers=auth(), json={
        "owner_user_id": "user-1", "expected_version": 1, "command_id": "edit-command-003"
    })
    duplicate = client.patch("/v1/items/item-001", headers=auth(), json={
        "owner_user_id": "user-1", "expected_version": 1, "command_id": "edit-command-004",
        "attributes": ["blue", " Blue "],
    })
    assert empty.status_code == 422
    assert duplicate.status_code == 422
    assert transition(client).status_code == 200
    assert transition(client, expected_version=2, target_status="deleted", command_id="delete-command-001").status_code == 200
    deleted_edit = client.patch("/v1/items/item-001", headers=auth(), json={
        "owner_user_id": "user-1", "expected_version": 3, "command_id": "edit-command-005",
        "display_name": "Should not edit",
    })
    assert deleted_edit.status_code == 409

 
def test_edit_rejects_whitespace_only_fields(client):
    create(client)
    for field in ("display_name", "category"):
        response = client.patch("/v1/items/item-001", headers=auth(), json={
            "owner_user_id": "user-1", "expected_version": 1,
            "command_id": "edit-empty-" + field, field: "   ",
        })
        assert response.status_code == 422

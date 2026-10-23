from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app import main
from app.store import Base, engine_for_url

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

def test_readiness_does_not_accept_sqlite_without_test_override(client,monkeypatch):
    monkeypatch.delenv("WARDROBE_ALLOW_SQLITE_TESTS",raising=False)
    result=client.get("/ready")
    assert result.status_code==503
    assert result.json()["detail"]["ready"] is False

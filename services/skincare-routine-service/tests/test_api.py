from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import Base, engine_for_url


TOKEN = "skincare-routine-test-token-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'routines.sqlite'}"
    monkeypatch.setenv("SKINCARE_ROUTINE_DATABASE_URL", url)
    monkeypatch.setenv("SKINCARE_ROUTINE_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("SKINCARE_ROUTINE_ALLOW_SQLITE_TESTS", "1")
    engine = engine_for_url(url)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def step(step_id: str, label: str, **overrides):
    value = {"step_id": step_id, "label": label}
    value.update(overrides)
    return value


def payload(**overrides):
    value = {
        "owner_user_id": "user-1",
        "name": "My daily skin routine",
        "description": "A simple, user-curated routine.",
        "morning_steps": [
            step("am-cleanse", "Gentle cleanse"),
            step("am-moisturize", "Moisturizer"),
            step("am-spf", "Broad-spectrum sunscreen"),
        ],
        "evening_steps": [
            step("pm-cleanse", "Cleanse"),
            step("pm-moisturize", "Moisturizer"),
        ],
    }
    value.update(overrides)
    return value


def create(client, **overrides):
    response = client.post("/v1/routines", headers=auth(), json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["routine"]


def test_authentication_is_required(client):
    assert client.get("/v1/routines", params={"owner_user_id": "user-1"}).status_code == 401


def test_readiness_checks_token_and_schema(client):
    response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True


def test_create_and_list_owner_scoped_am_pm_routine(client):
    routine = create(client)
    assert [item["label"] for item in routine["morning_steps"]] == [
        "Gentle cleanse", "Moisturizer", "Broad-spectrum sunscreen",
    ]
    assert [item["label"] for item in routine["evening_steps"]] == ["Cleanse", "Moisturizer"]
    own = client.get("/v1/routines", headers=auth(), params={"owner_user_id": "user-1"})
    other = client.get("/v1/routines", headers=auth(), params={"owner_user_id": "user-2"})
    assert len(own.json()["routines"]) == 1
    assert other.json()["routines"] == []


def test_create_requires_at_least_one_period_and_unique_step_ids(client):
    empty = client.post("/v1/routines", headers=auth(), json=payload(morning_steps=[], evening_steps=[]))
    duplicate = client.post("/v1/routines", headers=auth(), json=payload(morning_steps=[
        step("same-step", "Cleanse"), step("same-step", "Moisturizer"),
    ]))
    assert empty.status_code == 422
    assert duplicate.status_code == 422


def test_product_reference_must_be_catalog_uuid(client):
    response = client.post("/v1/routines", headers=auth(), json=payload(
        morning_steps=[step("am-serum", "Serum", product_id="https://example.invalid/product")]
    ))
    assert response.status_code == 422


def test_update_requires_current_version(client):
    routine = create(client)
    routine_id = routine["routine_id"]
    update = payload(name="Updated AM/PM routine")
    update.pop("owner_user_id")
    first_body = {"owner_user_id": "user-1", "expected_version": 1, **update}
    stale_body = {"owner_user_id": "user-1", "expected_version": 1, **update}
    first = client.put(f"/v1/routines/{routine_id}", headers=auth(), json=first_body)
    stale = client.put(f"/v1/routines/{routine_id}", headers=auth(), json=stale_body)
    assert first.status_code == 200, first.text
    assert first.json()["routine"]["version"] == 2
    assert stale.status_code == 409


def test_share_link_is_read_only_and_does_not_expose_owner_id(client):
    routine = create(client)
    share = client.post(
        f"/v1/routines/{routine['routine_id']}/share",
        headers=auth(),
        json={"owner_user_id": "user-1", "expires_in_days": 7},
    )
    assert share.status_code == 200, share.text
    path = share.json()["share_path"]
    public = client.get(path)
    assert public.status_code == 200, public.text
    assert "owner_user_id" not in public.json()["routine"]
    assert public.json()["routine"]["morning_steps"][0]["label"] == "Gentle cleanse"
    assert public.headers["cache-control"] == "no-store"
    assert public.headers["x-robots-tag"] == "noindex, nofollow, noarchive"


def test_replacing_share_revokes_previous_token(client):
    routine = create(client)
    first = client.post(f"/v1/routines/{routine['routine_id']}/share", headers=auth(), json={"owner_user_id": "user-1"})
    second = client.post(f"/v1/routines/{routine['routine_id']}/share", headers=auth(), json={"owner_user_id": "user-1"})
    assert client.get(first.json()["share_path"]).status_code == 404
    assert client.get(second.json()["share_path"]).status_code == 200


def test_share_can_be_revoked(client):
    routine = create(client)
    share = client.post(f"/v1/routines/{routine['routine_id']}/share", headers=auth(), json={"owner_user_id": "user-1"})
    revoked = client.delete(
        f"/v1/routines/{routine['routine_id']}/share",
        headers=auth(),
        params={"owner_user_id": "user-1"},
    )
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    assert client.get(share.json()["share_path"]).status_code == 404


def test_share_expiration_is_bounded(client):
    routine = create(client)
    too_long = client.post(
        f"/v1/routines/{routine['routine_id']}/share",
        headers=auth(),
        json={"owner_user_id": "user-1", "expires_in_days": 91},
    )
    assert too_long.status_code == 422


def test_delete_revokes_share_and_removes_routine(client):
    routine = create(client)
    share = client.post(f"/v1/routines/{routine['routine_id']}/share", headers=auth(), json={"owner_user_id": "user-1"})
    deleted = client.delete(
        f"/v1/routines/{routine['routine_id']}",
        headers=auth(),
        params={"owner_user_id": "user-1", "expected_version": 1},
    )
    assert deleted.status_code == 200
    assert client.get(share.json()["share_path"]).status_code == 404
    assert client.get(
        f"/v1/routines/{routine['routine_id']}",
        headers=auth(),
        params={"owner_user_id": "user-1"},
    ).status_code == 404


def test_random_share_tokens_do_not_authenticate_internal_routes(client):
    response = client.get("/v1/routines", params={"owner_user_id": "user-1"})
    assert response.status_code == 401


def test_expired_share_token_is_rejected(client):
    from datetime import datetime, timedelta, timezone
    from app.store import RoutineStore

    routine = create(client)
    share = client.post(
        f"/v1/routines/{routine['routine_id']}/share",
        headers=auth(),
        json={"owner_user_id": "user-1", "expires_in_days": 1},
    )
    token = share.json()["share_path"].rsplit("/", 1)[1]
    routine_store = RoutineStore(engine_for_url(
        __import__("os").environ["SKINCARE_ROUTINE_DATABASE_URL"]
    ))
    expired = routine_store.get_shared(token, now=datetime.now(timezone.utc) + timedelta(days=2))
    assert expired is None


def test_step_text_cannot_be_blank(client):
    response = client.post(
        "/v1/routines",
        headers=auth(),
        json=payload(morning_steps=[step("am-cleanse", "   ")]),
    )
    assert response.status_code == 422


def test_owner_identifier_cannot_be_blank(client):
    response = client.post("/v1/routines", headers=auth(), json=payload(owner_user_id="   "))
    assert response.status_code == 422

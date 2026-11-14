import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "identity-service-test-token-that-is-at-least-32-bytes"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "identity.db")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("IDENTITY_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("IDENTITY_CRON_TOKEN", "identity-cron-token-that-is-at-least-32-bytes")
    main._engine.cache_clear()
    main._session_factory.cache_clear()
    main.Base.metadata.create_all(bind=main._engine(url))
    with TestClient(main.app) as test_client:
        yield test_client
    main._session_factory.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def consent(client, subject="user-verified-1", scope="style_learning", receipt="receipt-style-0001"):
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={"receipt_id": receipt, "scope": scope, "consent_version": "2026-11-01", "granted": True},
    )


def event_body(**overrides):
    body = {
        "event_id": "event-0001",
        "idempotency_key": "idem-key-0001",
        "consent_receipt_id": "receipt-style-0001",
        "feature_key": "fragrance.intensity",
        "value": "light",
        "observed_at": "2026-11-02T08:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
    }
    body.update(overrides)
    return body


def test_internal_auth_is_required(client):
    assert client.get("/ready").status_code == 401
    assert client.get("/v1/profiles/user-verified-1", headers=auth()).status_code == 403
    assert client.post(
        "/internal/v1/consents/verify",
        json={"subject_id": "user-verified-1", "consent_id": "bundle-0001", "required_scopes": ["image_processing"]},
    ).status_code == 401


def test_usi_profile_requires_consent_and_uses_optimistic_version(client):
    assert consent(client, scope="profile_storage", receipt="receipt-profile-0001").status_code == 200
    body = {"expected_version": 0, "preferences": [{"preference_id": "p1", "attribute": "minimalist", "weight": 0.8}]}
    created = client.put("/v1/profiles/user-verified-1", headers=auth(), json=body)
    assert created.status_code == 200
    assert created.json()["profile_version"] == 1
    assert client.get("/v1/profiles/user-verified-1", headers=auth()).json()["preferences"][0]["attribute"] == "minimalist"
    conflict = client.put("/v1/profiles/user-verified-1", headers=auth(), json=body)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "USI_PROFILE_VERSION_CONFLICT"


def test_usi_profile_versions_increment_without_lost_updates(client):
    consent(client, scope="profile_storage", receipt="receipt-profile-0001")
    first = client.put(
        "/v1/profiles/user-verified-1",
        headers=auth(),
        json={
            "expected_version": 0,
            "preferences": [{"preference_id": "p1", "attribute": "classic", "weight": 0.8}],
        },
    )
    second = client.put(
        "/v1/profiles/user-verified-1",
        headers=auth(),
        json={
            "preferences": [{"preference_id": "p1", "attribute": "minimal", "weight": 0.9}],
        },
    )
    assert first.status_code == 200
    assert first.json()["profile_version"] == 1
    assert second.status_code == 200
    assert second.json()["profile_version"] == 2
    assert second.json()["preferences"][0]["attribute"] == "minimal"


def test_tal_requires_active_explicit_consent_and_is_idempotent(client):
    denied = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    assert denied.status_code == 403
    assert consent(client).status_code == 200
    first = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    replay = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    assert first.status_code == 200
    assert first.json()["status"] == "recorded"
    assert replay.json()["status"] == "replayed"


def test_tal_rejects_changed_idempotency_payload(client):
    consent(client)
    assert client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body()).status_code == 200
    changed = event_body(event_id="event-0002", value="bold")
    response = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=changed)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TAL_IDEMPOTENCY_CONFLICT"


def test_tal_correction_is_append_only_and_exportable(client):
    consent(client)
    client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    correction = event_body(
        event_id="event-0002", idempotency_key="idem-key-0002", event_kind="correction",
        supersedes_event_id="event-0001", value="moderate",
    )
    response = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=correction)
    assert response.status_code == 200
    exported = client.get("/v1/tal/export/user-verified-1", headers=auth()).json()
    assert len(exported["events"]) == 2
    assert exported["events"][1]["supersedes_event_id"] == "event-0001"


def test_revoked_consent_blocks_future_events(client):
    consent(client)
    revoked = client.post(
        "/v1/tal/consents/receipt-style-0001/revoke?subject_id=user-verified-1", headers=auth()
    )
    assert revoked.status_code == 200
    denied = client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    assert denied.status_code == 403


def test_retention_purge_removes_expired_events(client):
    consent(client)
    expired = event_body(
        event_id="event-expired", idempotency_key="idem-expired",
        observed_at="2025-01-01T00:00:00Z", expires_at="2025-01-02T00:00:00Z",
    )
    assert client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=expired).status_code == 200
    purged = client.post(
        "/internal/retention/purge", headers={**auth(), "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes"}
    )
    assert purged.status_code == 200
    assert purged.json()["purged_events"] == 1


def test_scope_revocation_revokes_every_active_grant(client):
    consent(client, receipt="receipt-style-0001")
    consent(client, receipt="receipt-style-0002")

    revoked = client.post(
        "/v1/tal/consents/receipt-style-0001/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200

    first = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(),
    )
    second = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(
            event_id="event-0002",
            idempotency_key="idem-key-0002",
            consent_receipt_id="receipt-style-0002",
        ),
    )
    assert first.status_code == 403
    assert second.status_code == 403

    receipts = client.get(
        "/v1/tal/consents/user-verified-1", headers=auth()
    ).json()
    active = [item for item in receipts if item["scope"] == "style_learning" and item["granted"]]
    assert len(active) == 2
    assert all(item["revoked_at"] for item in active)



def _grant_resource_consent(client, *, subject, bundle, resource, scope, receipt, expires_at=None):
    payload = {
        "receipt_id": receipt,
        "consent_id": bundle,
        "resource_id": resource,
        "scope": scope,
        "consent_version": "media-2026-11-v1",
        "granted": True,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json=payload,
    )


def _verify_resource_consent(client, *, subject, bundle, resource, scopes=None, version="media-2026-11-v1"):
    return client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": subject,
            "consent_id": bundle,
            "consent_version": version,
            "resource_id": resource,
            "required_scopes": scopes or ["image_processing", "body_measurements", "virtual_twin_storage"],
        },
    )


def _create_pnelly_conversation(client, *, subject="user-verified-1", conversation_id=None, receipt_id=None, expires_at=None):
    conversation_id = conversation_id or str(__import__("uuid").uuid4())
    receipt_id = receipt_id or "pnelly-context-receipt-0001"
    expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    granted = client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={
            "receipt_id": receipt_id,
            "consent_id": conversation_id,
            "resource_id": conversation_id,
            "scope": "pnelly_conversation",
            "consent_version": "pnelly-context-v1",
            "granted": True,
            "expires_at": expires_at,
        },
    )
    assert granted.status_code == 200, granted.text
    created = client.post(
        f"/v1/pnelly/conversations?subject_id={subject}",
        headers=auth(),
        json={"conversation_id": conversation_id, "consent_receipt_id": receipt_id},
    )
    return conversation_id, receipt_id, created


def test_pnelly_conversation_context_requires_exact_resource_bound_24_hour_consent(client):
    conversation_id = str(__import__("uuid").uuid4())
    no_consent = client.post(
        f"/v1/pnelly/conversations?subject_id=user-verified-1",
        headers=auth(),
        json={"conversation_id": conversation_id, "consent_receipt_id": "missing-receipt-0001"},
    )
    assert no_consent.status_code == 403
    assert no_consent.json()["detail"]["code"] == "ACTIVE_PNELLY_CONVERSATION_CONSENT_REQUIRED"

    too_long = datetime.now(timezone.utc) + timedelta(days=2)
    _, _, created = _create_pnelly_conversation(
        client,
        conversation_id=conversation_id,
        receipt_id="pnelly-context-too-long",
        expires_at=too_long.isoformat(),
    )
    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "PNELLY_CONVERSATION_EXPIRY_MUST_BE_WITHIN_24_HOURS"


def test_pnelly_conversation_turns_are_versioned_idempotent_and_transcript_free(client):
    conversation_id, receipt_id, created = _create_pnelly_conversation(client)
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "created"
    assert created.json()["state_version"] == 0

    turn = {
        "expected_version": 0,
        "turn_id": "pnelly-turn-0001",
        "context": {
            "query": "modest dark green linen dress",
            "category": "dress",
            "currency": "KES",
            "occasion": "work",
            "constraints": ["long sleeves", "breathable fabric"],
            "exclude_owned_products": True,
        },
    }
    updated = client.put(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
        json=turn,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["state_version"] == 1
    assert updated.json()["context"]["currency"] == "KES"
    assert updated.json()["context"]["constraints"] == ["long sleeves", "breathable fabric"]
    assert "messages" not in updated.json()
    assert "transcript" not in updated.json()

    replay = client.put(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
        json=turn,
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    assert replay.json()["state_version"] == 1

    changed_replay = {**turn, "context": {**turn["context"], "occasion": "evening"}}
    conflict = client.put(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
        json=changed_replay,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "PNELLY_CONVERSATION_TURN_CONFLICT"

    second_turn = {
        "expected_version": 1,
        "turn_id": "pnelly-turn-0002",
        "context": {**turn["context"], "occasion": "evening", "query": "same dress, more formal"},
    }
    stale = client.put(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
        json={**second_turn, "expected_version": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PNELLY_CONVERSATION_VERSION_CONFLICT"

    saved = client.put(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
        json=second_turn,
    )
    assert saved.status_code == 200
    assert saved.json()["state_version"] == 2

    replay_create = client.post(
        "/v1/pnelly/conversations?subject_id=user-verified-1",
        headers=auth(),
        json={"conversation_id": conversation_id, "consent_receipt_id": receipt_id},
    )
    assert replay_create.status_code == 200
    assert replay_create.json()["status"] == "replayed"


def test_pnelly_conversation_is_owner_scoped_and_revocation_deletes_context(client):
    conversation_id, receipt_id, created = _create_pnelly_conversation(client)
    assert created.status_code == 200
    foreign = client.get(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=another-user",
        headers=auth(),
    )
    assert foreign.status_code == 404

    revoked = client.post(
        f"/v1/tal/consents/{receipt_id}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    missing = client.get(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
    )
    assert missing.status_code == 404


def test_pnelly_conversation_delete_revokes_its_receipt(client):
    conversation_id, receipt_id, created = _create_pnelly_conversation(client)
    assert created.status_code == 200
    deleted = client.delete(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
    )
    assert deleted.status_code == 200
    assert deleted.json()["consent_inactive"] is True
    receipts = client.get("/v1/tal/consents/user-verified-1", headers=auth()).json()
    receipt = next(item for item in receipts if item["receipt_id"] == receipt_id)
    assert receipt["revoked_at"] is not None


def test_pnelly_conversation_expiry_and_retention_purge_remove_context(client):
    conversation_id, _, created = _create_pnelly_conversation(client)
    assert created.status_code == 200
    url = os.environ["IDENTITY_DATABASE_URL"]
    db = main._session_factory(url)()
    row = db.get(main.PnellyConversation, conversation_id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()

    denied = client.get(
        f"/v1/pnelly/conversations/{conversation_id}?subject_id=user-verified-1",
        headers=auth(),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ACTIVE_PNELLY_CONVERSATION_CONSENT_REQUIRED"

    # Recreate a second active row and expire it through the retention job.
    conversation_id_2, _, created_2 = _create_pnelly_conversation(
        client, receipt_id="pnelly-context-retention-0002"
    )
    assert created_2.status_code == 200
    db = main._session_factory(url)()
    row = db.get(main.PnellyConversation, conversation_id_2)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()
    purged = client.post(
        "/internal/retention/purge",
        headers={**auth(), "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes"},
    )
    assert purged.status_code == 200
    assert purged.json()["purged_pnelly_conversations"] == 1
    gone = client.get(
        f"/v1/pnelly/conversations/{conversation_id_2}?subject_id=user-verified-1",
        headers=auth(),
    )
    assert gone.status_code == 404


def test_resource_bound_verifier_requires_complete_subject_and_resource_bundle(client):
    scopes = ["image_processing", "body_measurements", "virtual_twin_storage"]
    for index, scope in enumerate(scopes):
        response = _grant_resource_consent(
            client, subject="user-verified-1", bundle="bundle-twin-a",
            resource="twin-resource-a", scope=scope, receipt=f"media-receipt-{index:02d}",
        )
        assert response.status_code == 200, response.text

    verified = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-twin-a", resource="twin-resource-a",
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True
    assert verified.json()["active"] is True
    assert set(verified.json()["granted_scopes"]) == set(scopes)

    wrong_resource = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-twin-a", resource="twin-resource-b",
    )
    wrong_subject = _verify_resource_consent(
        client, subject="another-user", bundle="bundle-twin-a", resource="twin-resource-a",
    )
    wrong_version = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-twin-a",
        resource="twin-resource-a", version="older-version",
    )
    missing_resource = client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={"subject_id": "user-verified-1", "consent_id": "bundle-twin-a", "required_scopes": scopes},
    )
    assert wrong_resource.status_code == 403
    assert wrong_subject.status_code == 403
    assert wrong_version.status_code == 403
    assert missing_resource.status_code == 403


def test_resource_bound_receipt_replay_cannot_change_resource_or_bundle(client):
    created = _grant_resource_consent(
        client, subject="user-verified-1", bundle="bundle-immutable",
        resource="twin-resource-immutable", scope="image_processing",
        receipt="receipt-immutable-01",
    )
    assert created.status_code == 200
    changed = client.post(
        "/v1/tal/consents", params={"subject_id": "user-verified-1"},
        headers=auth(), json={
            "receipt_id": "receipt-immutable-01", "consent_id": "bundle-immutable",
            "resource_id": "twin-resource-other", "scope": "image_processing",
            "consent_version": "media-2026-11-v1", "granted": True,
        },
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "CONSENT_RECEIPT_IMMUTABLE"


def test_resource_bound_verifier_fails_closed_when_any_scope_is_missing(client):
    for index, scope in enumerate(["image_processing", "body_measurements"]):
        assert _grant_resource_consent(
            client, subject="user-verified-1", bundle="bundle-incomplete",
            resource="twin-incomplete", scope=scope, receipt=f"incomplete-receipt-{index:02d}",
        ).status_code == 200
    response = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-incomplete", resource="twin-incomplete",
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_BUNDLE_INCOMPLETE"
    assert response.json()["detail"]["missing_scopes"] == ["virtual_twin_storage"]


def test_resource_specific_revocation_does_not_revoke_another_twin_bundle(client):
    scopes = ["image_processing", "body_measurements", "virtual_twin_storage"]
    receipts_a = []
    for index, scope in enumerate(scopes):
        receipt = f"twin-a-receipt-{index:02d}"
        receipts_a.append(receipt)
        assert _grant_resource_consent(
            client, subject="user-verified-1", bundle="bundle-twin-a",
            resource="twin-resource-a", scope=scope, receipt=receipt,
        ).status_code == 200
        assert _grant_resource_consent(
            client, subject="user-verified-1", bundle="bundle-twin-b",
            resource="twin-resource-b", scope=scope, receipt=f"twin-b-receipt-{index:02d}",
        ).status_code == 200

    revoked = client.post(
        f"/v1/tal/consents/{receipts_a[0]}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    denied = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-twin-a", resource="twin-resource-a",
    )
    allowed = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-twin-b", resource="twin-resource-b",
    )
    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_resource_bound_twin_consent_revocation_dispatches_asset_cleanup(client, monkeypatch):
    scopes = ["image_processing", "body_measurements", "virtual_twin_storage"]
    receipts = []
    for index, scope in enumerate(scopes):
        receipt = f"twin-cleanup-receipt-{index:02d}"
        receipts.append(receipt)
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-twin-cleanup",
            resource="twin-resource-cleanup",
            scope=scope,
            receipt=receipt,
        ).status_code == 200

    observed = {}
    async def notify(item):
        observed.update(
            subject_id=item.subject_id,
            consent_id=item.consent_id,
            resource_id=item.resource_id,
            receipt_id=item.receipt_id,
            command_id=item.command_id,
        )
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", notify)
    revoked = client.post(
        f"/v1/tal/consents/{receipts[0]}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["twin_cleanup_status"] == "complete"
    assert observed["subject_id"] == "user-verified-1"
    assert observed["consent_id"] == "bundle-twin-cleanup"
    assert observed["resource_id"] == "twin-resource-cleanup"
    assert observed["receipt_id"] == receipts[0]
    assert observed["command_id"].startswith("twin-consent-revocation:")

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        outbox = db.get(main.ConsentRevocationOutbox, observed["command_id"])
        assert outbox is not None
        assert outbox.status == "delivered"
        assert outbox.attempts == 0
        assert outbox.completed_at is not None
    finally:
        db.close()


def test_twin_consent_cleanup_failure_is_durable_and_retryable(client, monkeypatch):
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-twin-retry",
            resource="twin-resource-retry",
            scope=scope,
            receipt=f"twin-retry-receipt-{index:02d}",
        ).status_code == 200

    async def unavailable(_item):
        raise RuntimeError("TWIN_REGISTRY_UNAVAILABLE")

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", unavailable)
    revoked = client.post(
        "/v1/tal/consents/twin-retry-receipt-00/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["twin_cleanup_status"] == "pending"

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        pending = db.query(main.ConsentRevocationOutbox).one()
        command_id = pending.command_id
        assert pending.status == "pending"
        assert pending.attempts == 1
        assert pending.last_error_code == "TWIN_REGISTRY_UNAVAILABLE"
    finally:
        db.close()

    calls = []
    async def recovered(item):
        calls.append(item.command_id)
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", recovered)
    retry = client.post("/internal/v1/consent-revocations/dispatch?limit=10", headers=auth())
    assert retry.status_code == 200, retry.text
    assert retry.json() == {"processed": 1, "completed": 1, "failed": 0, "pending": False}
    assert calls == [command_id]

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        completed = db.get(main.ConsentRevocationOutbox, command_id)
        assert completed.status == "delivered"
        assert completed.last_error_code is None
        assert completed.completed_at is not None
    finally:
        db.close()


def test_withdrawing_non_twin_scope_in_twin_bundle_still_queues_resource_cleanup(client, monkeypatch):
    receipts = {}
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage", "profile_storage"]):
        receipt = f"mixed-twin-bundle-receipt-{index:02d}"
        receipts[scope] = receipt
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="mixed-twin-consent-bundle",
            resource="twin-mixed-bundle",
            scope=scope,
            receipt=receipt,
        ).status_code == 200

    observed = []
    async def notify(item):
        observed.append((item.consent_id, item.resource_id, item.receipt_id))
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", notify)
    revoked = client.post(
        f"/v1/tal/consents/{receipts['profile_storage']}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["twin_cleanup_status"] == "delivered"
    assert observed == [(
        "mixed-twin-consent-bundle",
        "twin-mixed-bundle",
        receipts["profile_storage"],
    )]


def test_non_twin_consent_revocation_does_not_create_twin_cleanup_command(client):
    assert consent(client).status_code == 200
    revoked = client.post(
        "/v1/tal/consents/receipt-style-0001/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    assert revoked.json()["twin_cleanup_status"] == "not_applicable"
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        assert db.query(main.ConsentRevocationOutbox).count() == 0
    finally:
        db.close()


def test_full_user_deletion_preserves_twin_cleanup_outbox_after_consent_rows_are_removed(client, monkeypatch):
    scopes = ["image_processing", "body_measurements", "virtual_twin_storage"]
    for index, scope in enumerate(scopes):
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-user-delete",
            resource="twin-user-delete",
            scope=scope,
            receipt=f"user-delete-twin-receipt-{index:02d}",
        ).status_code == 200

    observed = []
    async def notify(item):
        observed.append((item.subject_id, item.consent_id, item.resource_id))
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", notify)
    deleted = client.delete("/v1/tal/users/user-verified-1", headers=auth())
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["twin_cleanup_commands"] == 1
    assert deleted.json()["twin_cleanup_delivered"] == 1
    assert deleted.json()["twin_cleanup_pending"] is False
    assert client.get("/v1/tal/consents/user-verified-1", headers=auth()).json() == []
    assert observed == [("user-verified-1", "bundle-user-delete", "twin-user-delete")]

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        rows = db.query(main.ConsentRevocationOutbox).all()
        assert len(rows) == 1
        assert rows[0].status == "delivered"
        assert rows[0].receipt_id == "user-delete-twin-receipt-00"
    finally:
        db.close()


def test_retention_expiry_queues_twin_cleanup_before_consent_becomes_inactive(client, monkeypatch):
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-expired-twin",
            resource="twin-expired-retention",
            scope=scope,
            receipt=f"expired-twin-retention-{index:02d}",
            expires_at=expires,
        ).status_code == 200

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        db.query(main.ConsentReceipt).filter(
            main.ConsentReceipt.consent_id == "bundle-expired-twin",
        ).update({
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)
        }, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    observed = []
    async def notify(item):
        observed.append((item.subject_id, item.consent_id, item.resource_id))
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", notify)
    purged = client.post(
        "/internal/retention/purge",
        headers={
            **auth(),
            "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes",
        },
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["twin_cleanup_commands"] == 1
    assert purged.json()["twin_cleanup_delivered"] == 1
    assert purged.json()["twin_cleanup_pending"] is False
    assert observed == [("user-verified-1", "bundle-expired-twin", "twin-expired-retention")]
    assert _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle="bundle-expired-twin",
        resource="twin-expired-retention",
    ).status_code == 403


def test_denial_receipt_withdraws_prior_scope_grants(client):
    consent(client, receipt="receipt-style-granted")
    denied = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "receipt-style-denied",
            "scope": "style_learning",
            "consent_version": "2026-11-02",
            "granted": False,
        },
    )
    assert denied.status_code == 200
    assert denied.json()["granted"] is False

    event = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(),
    )
    assert event.status_code == 403


def test_new_grant_after_withdrawal_does_not_reactivate_old_receipt(client):
    consent(client, receipt="receipt-style-old")
    client.post(
        "/v1/tal/consents/receipt-style-old/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    consent(client, receipt="receipt-style-new")

    old_event = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(consent_receipt_id="receipt-style-old"),
    )
    new_event = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(
            event_id="event-new-grant",
            idempotency_key="idem-new-grant",
            consent_receipt_id="receipt-style-new",
        ),
    )
    assert old_event.status_code == 403
    assert new_event.status_code == 200


def test_tal_correction_must_target_the_same_feature(client):
    consent(client)
    client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(feature_key="colour.accent"),
    )
    correction = event_body(
        event_id="event-0002",
        idempotency_key="idem-key-0002",
        event_kind="correction",
        supersedes_event_id="event-0001",
        feature_key="fragrance.intensity",
        value="moderate",
    )
    response = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=correction,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TAL_CORRECTION_FEATURE_MISMATCH"


def test_delete_user_data_removes_profile_consents_and_events(client):
    consent(client, scope="profile_storage", receipt="receipt-profile-0001")
    consent(client)
    client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0, "preferences": [{"preference_id": "p1", "attribute": "classic"}]
    })
    client.post("/v1/tal/events?subject_id=user-verified-1", headers=auth(), json=event_body())
    conversation_id, _, created = _create_pnelly_conversation(client)
    assert created.status_code == 200
    before_delete = client.get("/v1/tal/export/user-verified-1", headers=auth()).json()
    assert len(before_delete["pnelly_conversations"]) == 1
    deleted = client.delete("/v1/tal/users/user-verified-1", headers=auth())
    assert deleted.status_code == 200
    assert deleted.json()["deleted_events"] == 1
    assert deleted.json()["deleted_pnelly_conversations"] == 1
    after_delete = client.get("/v1/tal/export/user-verified-1", headers=auth()).json()
    assert after_delete["profile"] is None
    assert after_delete["pnelly_conversations"] == []
    assert client.get("/v1/tal/consents/user-verified-1", headers=auth()).json() == []


def test_personal_color_profile_is_user_declared_versioned_and_consent_gated(client):
    denied = client.get("/v1/color-profiles/user-verified-1", headers=auth())
    assert denied.status_code == 403
    consent(client, scope="profile_storage", receipt="receipt-color-profile")
    empty = client.get("/v1/color-profiles/user-verified-1", headers=auth())
    assert empty.status_code == 200
    assert empty.json()["profile_version"] == 0
    assert empty.json()["analysis"]["status"] == "unavailable"
    assert empty.json()["analysis"]["reason_code"] == "NO_VALIDATED_COLOR_ANALYSIS_MODEL"

    body = {
        "expected_version": 0,
        "liked_colors": [" Emerald ", "Cobalt"],
        "disliked_colors": ["Neon Yellow"],
        "best_version_colors": ["Burgundy", "emerald"],
    }
    saved = client.put("/v1/color-profiles/user-verified-1", headers=auth(), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["profile_version"] == 1
    assert saved.json()["liked_colors"] == ["emerald", "cobalt"]
    assert saved.json()["disliked_colors"] == ["neon yellow"]
    assert saved.json()["best_version_colors"] == ["burgundy", "emerald"]
    assert saved.json()["analysis"]["status"] == "unavailable"

    conflict = client.put("/v1/color-profiles/user-verified-1", headers=auth(), json=body)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "COLOR_PROFILE_VERSION_CONFLICT"


def test_personal_color_profile_rejects_duplicate_values_and_revoked_consent(client):
    consent(client, scope="profile_storage", receipt="receipt-color-profile")
    duplicate = client.put("/v1/color-profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0,
        "liked_colors": ["Emerald", " emerald "],
    })
    assert duplicate.status_code == 422
    revoked = client.post(
        "/v1/tal/consents/receipt-color-profile/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    denied = client.put("/v1/color-profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0, "liked_colors": ["emerald"],
    })
    assert denied.status_code == 403


def test_personal_color_profile_is_included_in_export_and_deleted_with_user_data(client):
    consent(client, scope="profile_storage", receipt="receipt-color-profile")
    saved = client.put("/v1/color-profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0,
        "liked_colors": ["teal"],
        "disliked_colors": ["neon pink"],
        "best_version_colors": ["deep plum"],
    })
    assert saved.status_code == 200
    exported = client.get("/v1/tal/export/user-verified-1", headers=auth()).json()
    assert exported["color_profile"]["liked_colors"] == ["teal"]
    deleted = client.delete("/v1/tal/users/user-verified-1", headers=auth())
    assert deleted.status_code == 200
    assert deleted.json()["deleted_color_profile"] is True
    assert client.get("/v1/color-profiles/user-verified-1", headers=auth()).status_code == 403


def test_resource_bound_consent_expiry_is_returned_and_enforced(client):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        response = _grant_resource_consent(
            client, subject="user-verified-1", bundle="bundle-expiring",
            resource="twin-expiring", scope=scope,
            receipt=f"expiry-receipt-{index:02d}", expires_at=expiry,
        )
        assert response.status_code == 200, response.text
        assert response.json()["expires_at"] is not None
    verified = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-expiring", resource="twin-expiring",
    )
    assert verified.status_code == 200, verified.text
    listed = client.get("/v1/tal/consents/user-verified-1", headers=auth()).json()
    assert all(item["expires_at"] is not None for item in listed if item["consent_id"] == "bundle-expiring")
    exported = client.get("/v1/tal/export/user-verified-1", headers=auth()).json()
    assert all(item["expires_at"] is not None for item in exported["consent_receipts"] if item["consent_id"] == "bundle-expiring")


def test_expired_resource_bound_consent_cannot_authorize_a_twin(client):
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        db.add(main.ConsentReceipt(
            receipt_id=f"expired-twin-{index:02d}",
            subject_id="user-verified-1",
            consent_id="bundle-expired",
            resource_id="twin-expired",
            scope=scope,
            consent_version="media-2026-11-v1",
            granted=True,
            granted_at=expired - timedelta(hours=1),
            revoked_at=None,
            expires_at=expired,
        ))
    db.commit()
    db.close()
    response = _verify_resource_consent(
        client, subject="user-verified-1", bundle="bundle-expired", resource="twin-expired",
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_BUNDLE_INCOMPLETE"


def test_expired_consent_receipt_cannot_authorize_tal_event(client):
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(main.ConsentReceipt(
        receipt_id="expired-style-receipt",
        subject_id="user-verified-1",
        consent_id="expired-style-bundle",
        resource_id=None,
        scope="style_learning",
        consent_version="2026-11-01",
        granted=True,
        granted_at=expired - timedelta(hours=1),
        revoked_at=None,
        expires_at=expired,
    ))
    db.commit()
    db.close()
    event = client.post(
        "/v1/tal/events?subject_id=user-verified-1",
        headers=auth(),
        json=event_body(consent_receipt_id="expired-style-receipt"),
    )
    assert event.status_code == 403
    assert event.json()["detail"]["code"] == "ACTIVE_TAL_CONSENT_REQUIRED"


def test_consent_expiry_must_be_future_and_timezone_aware(client):
    naive = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "naive-expiry-01", "scope": "virtual_twin_storage",
            "consent_version": "media-2026-11-v1", "granted": True,
            "consent_id": "bundle-naive", "resource_id": "twin-naive",
            "expires_at": "2027-01-01T00:00:00",
        },
    )
    past = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "past-expiry-01", "scope": "virtual_twin_storage",
            "consent_version": "media-2026-11-v1", "granted": True,
            "consent_id": "bundle-past", "resource_id": "twin-past",
            "expires_at": "2020-01-01T00:00:00Z",
        },
    )
    assert naive.status_code == 422
    assert past.status_code == 422


def test_expiring_consent_receipt_replay_is_idempotent_and_immutable(client):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    created = _grant_resource_consent(
        client, subject="user-verified-1", bundle="bundle-replay-expiry",
        resource="twin-replay-expiry", scope="virtual_twin_storage",
        receipt="receipt-replay-expiry", expires_at=expiry,
    )
    assert created.status_code == 200, created.text
    replay = _grant_resource_consent(
        client, subject="user-verified-1", bundle="bundle-replay-expiry",
        resource="twin-replay-expiry", scope="virtual_twin_storage",
        receipt="receipt-replay-expiry", expires_at=expiry,
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    changed = _grant_resource_consent(
        client, subject="user-verified-1", bundle="bundle-replay-expiry",
        resource="twin-replay-expiry", scope="virtual_twin_storage",
        receipt="receipt-replay-expiry",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    )
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "CONSENT_RECEIPT_IMMUTABLE"


def test_expired_profile_storage_consent_blocks_profile_and_color_operations(client):
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(main.ConsentReceipt(
        receipt_id="expired-profile-storage",
        subject_id="user-verified-1",
        consent_id="expired-profile-bundle",
        resource_id=None,
        scope="profile_storage",
        consent_version="profile-v1",
        granted=True,
        granted_at=expired - timedelta(hours=1),
        revoked_at=None,
        expires_at=expired,
    ))
    db.commit()
    db.close()
    assert client.get("/v1/profiles/user-verified-1", headers=auth()).status_code == 403
    assert client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "preferences": [{"preference_id": "p1", "attribute": "classic"}],
    }).status_code == 403
    assert client.get("/v1/color-profiles/user-verified-1", headers=auth()).status_code == 403
    assert client.put("/v1/color-profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0, "liked_colors": ["emerald"],
    }).status_code == 403

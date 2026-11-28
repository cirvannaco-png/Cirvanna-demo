import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "identity-service-test-token-that-is-at-least-32-bytes"
DSI_CAPTURE_TOKEN = "identity-dsi-capture-verifier-token-at-least-32-bytes"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "identity.db")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", DSI_CAPTURE_TOKEN)
    monkeypatch.setenv("IDENTITY_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("IDENTITY_CRON_TOKEN", "identity-cron-token-that-is-at-least-32-bytes")
    monkeypatch.setenv("CIL_CONTRIBUTOR_TOKEN_HMAC_SECRET", "identity-cil-contributor-pseudonym-key-at-least-32-bytes")
    monkeypatch.setenv("CIL_SKIN_ANALYSIS_CONSENT_KEY", "shared-cil-skin-analysis-consent-key-at-least-32-bytes")
    monkeypatch.setenv("IDENTITY_CIL_CONSENT_ISSUER_TOKEN", "identity-cil-consent-issuer-token-at-least-32-bytes")
    monkeypatch.setenv("IDENTITY_CIL_CONSENT_VERIFIER_TOKEN", "identity-cil-consent-verifier-token-at-least-32-bytes")
    main._engine.cache_clear()
    main._session_factory.cache_clear()
    main.Base.metadata.create_all(bind=main._engine(url))
    with TestClient(main.app) as test_client:
        yield test_client
    main._session_factory.cache_clear()
    main._engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def dsi_capture_auth():
    return {"Authorization": f"Bearer {DSI_CAPTURE_TOKEN}"}


def cil_consent_issuer_auth():
    return {"Authorization": "Bearer identity-cil-consent-issuer-token-at-least-32-bytes"}


def cil_consent_verifier_auth():
    return {"Authorization": "Bearer identity-cil-consent-verifier-token-at-least-32-bytes"}


def consent(client, subject="user-verified-1", scope="style_learning", receipt="receipt-style-0001"):
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={"receipt_id": receipt, "scope": scope, "consent_version": "2026-11-01", "granted": True},
    )


def skin_analysis_consent(
    client,
    *,
    subject="user-verified-1",
    bundle="skin-analysis-bundle-001",
    resource="skin-analysis-resource-001",
    receipt="skin-analysis-receipt-001",
    expires_at=None,
):
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={
            "receipt_id": receipt,
            "scope": "skin_analysis",
            "consent_id": bundle,
            "resource_id": resource,
            "consent_version": "skin-analysis-v1",
            "granted": True,
            "expires_at": expires_at or (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        },
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


def test_identity_accepts_resource_scoped_look_it_photographed_person_attestations(client):
    scopes = ("photographed_no_people_attestation",)
    for index, scope in enumerate(scopes, start=1):
        response = client.post(
            "/v1/tal/consents",
            params={"subject_id": "user-verified-1"},
            headers=auth(),
            json={
                "receipt_id": f"look-it-declaration-receipt-{index:02d}",
                "consent_id": "look-it-consent-bundle-001",
                "resource_id": "look-it-resource-001",
                "scope": scope,
                "consent_version": "pnelly-look-it-2026-11-v1",
                "granted": True,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            },
        )
        assert response.status_code == 200, response.text


def test_readiness_requires_pnelly_context_and_twin_cleanup_schema(client):
    ready = client.get("/ready", headers=auth())
    assert ready.status_code == 200
    assert ready.json()["pnelly_conversation_context"] is True
    assert ready.json()["twin_consent_cleanup_outbox"] is True

    main.ConsentRevocationOutbox.__table__.drop(
        bind=main._engine(os.environ["IDENTITY_DATABASE_URL"])
    )
    unavailable = client.get("/ready", headers=auth())
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "IDENTITY_SCHEMA_NOT_READY"
    main.ConsentRevocationOutbox.__table__.create(
        bind=main._engine(os.environ["IDENTITY_DATABASE_URL"])
    )


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


def test_pnelly_confirmed_usi_preferences_require_allowlisted_value_and_request_provenance(client):
    assert consent(client, scope="profile_storage", receipt="receipt-pnelly-profile-0001").status_code == 200
    valid = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0,
        "preferences": [{
            "preference_id": "pnelly-pref-0001",
            "attribute": "style:minimalist",
            "weight": 0.8,
            "active": True,
            "source": "pnelly_user_confirmed",
            "source_request_id": "complementer-request-0001",
        }],
    })
    assert valid.status_code == 200, valid.text
    stored = valid.json()["preferences"][0]
    assert stored["source"] == "pnelly_user_confirmed"
    assert stored["source_request_id"] == "complementer-request-0001"

    invalid_value = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 1,
        "preferences": [{
            "preference_id": "pnelly-pref-0002", "attribute": "style:unbounded-free-text",
            "source": "pnelly_user_confirmed", "source_request_id": "complementer-request-0002",
        }],
    })
    missing_provenance = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 1,
        "preferences": [{
            "preference_id": "pnelly-pref-0003", "attribute": "style:elegant",
            "source": "pnelly_user_confirmed",
        }],
    })
    forged_provenance = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 1,
        "preferences": [{
            "preference_id": "pnelly-pref-0004", "attribute": "style:elegant",
            "source": "user_declared", "source_request_id": "complementer-request-0004",
        }],
    })
    assert invalid_value.status_code == 422
    assert missing_provenance.status_code == 422
    assert forged_provenance.status_code == 422


def test_usi_profile_update_can_be_bound_to_the_exact_active_consent_receipt(client):
    consent(client, scope="profile_storage", receipt="receipt-profile-current-0001")
    consent(client, scope="profile_storage", receipt="receipt-profile-stale-0001")
    # The second receipt is revoked while the first remains active. A stale client
    # must not be able to rely on some other profile-storage grant.
    revoked = client.post(
        "/v1/tal/consents/receipt-profile-stale-0001/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    response = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0,
        "consent_receipt_id": "receipt-profile-stale-0001",
        "preferences": [{"preference_id": "p1", "attribute": "style:elegant"}],
    })
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"


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


def test_appearance_session_storage_is_explicit_expiring_and_resource_bound(client):
    look_id = str(__import__("uuid").uuid4())
    expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    assert _grant_resource_consent(
        client, subject="user-verified-1", bundle=look_id, resource=look_id,
        scope="appearance_session_storage", receipt="appearance-session-storage-001", expires_at=expiry,
    ).status_code == 200
    assert _grant_resource_consent(
        client, subject="user-verified-1", bundle=look_id, resource=look_id,
        scope="appearance_source_storage", receipt="appearance-source-storage-001", expires_at=expiry,
    ).status_code == 200
    assert _grant_resource_consent(
        client, subject="user-verified-1", bundle=look_id, resource=look_id,
        scope="image_processing", receipt="appearance-session-image-001", expires_at=expiry,
    ).status_code == 200
    verified = client.post(
        "/internal/v1/consents/verify", headers=auth(), json={
            "subject_id": "user-verified-1", "consent_id": look_id,
            "resource_id": look_id,
            "required_scopes": ["appearance_session_storage", "appearance_source_storage", "image_processing"],
            "require_expiring": True,
        },
    )
    wrong_resource = client.post(
        "/internal/v1/consents/verify", headers=auth(), json={
            "subject_id": "user-verified-1", "consent_id": look_id,
            "resource_id": "another-look-0001",
            "required_scopes": ["appearance_session_storage"],
            "require_expiring": True,
        },
    )
    assert verified.status_code == 200, verified.text
    assert set(verified.json()["granted_scopes"]) >= {"appearance_session_storage", "appearance_source_storage", "image_processing"}
    assert wrong_resource.status_code == 403


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
    assert revoked.json()["twin_cleanup_status"] == "delivered"
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
    assert retry.json() == {"processed": 1, "completed": 1, "already_delivered": 0, "delivered": 1, "failed": 0, "pending": False}
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


def test_retention_worker_retries_preexisting_failed_twin_cleanup_without_new_expiry(client, monkeypatch):
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-twin-retry-by-retention",
            resource="twin-resource-retry-by-retention",
            scope=scope,
            receipt=f"twin-retention-retry-{index:02d}",
        ).status_code == 200

    async def unavailable(_item):
        raise RuntimeError("TWIN_REGISTRY_UNAVAILABLE")

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", unavailable)
    revoked = client.post(
        "/v1/tal/consents/twin-retention-retry-00/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    assert revoked.json()["twin_cleanup_status"] == "pending"

    delivered = []
    async def recovered(item):
        delivered.append(item.command_id)
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", recovered)
    purged = client.post(
        "/internal/retention/purge",
        headers={
            **auth(),
            "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes",
        },
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["twin_cleanup_commands"] == 0
    assert purged.json()["twin_cleanup_processed"] == 1
    assert purged.json()["twin_cleanup_delivered"] == 1
    assert purged.json()["twin_cleanup_failed"] == 0
    assert purged.json()["twin_cleanup_pending"] is False
    assert len(delivered) == 1

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        row = db.get(main.ConsentRevocationOutbox, delivered[0])
        assert row is not None
        assert row.status == "delivered"
        assert row.attempts == 1
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



@pytest.mark.parametrize(
    "scope",
    [
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
        "global_model_training",
    ],
)
def test_dsi_purpose_scopes_are_explicitly_granted_and_resource_bound(client, scope):
    resource = "dsi-resource-0001"
    bundle = "dsi-purpose-bundle-0001"
    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    granted = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": f"receipt-{scope}-0001",
            "consent_id": bundle,
            "resource_id": resource,
            "scope": scope,
            "consent_version": "dsi-v1",
            "granted": True,
            "expires_at": expiry,
        },
    )
    assert granted.status_code == 200, granted.text

    verified = _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle=bundle,
        resource=resource,
        scopes=[scope],
        version="dsi-v1",
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True
    assert verified.json()["granted_scopes"] == [scope]
    assert verified.json()["resource_id"] == resource
    assert verified.json()["consent_version"] == "dsi-v1"

    wrong_resource = _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle=bundle,
        resource="different-dsi-resource",
        scopes=[scope],
        version="dsi-v1",
    )
    assert wrong_resource.status_code == 403


def test_dsi_purpose_scopes_are_not_implicitly_granted_by_image_processing(client):
    granted = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "receipt-image-only-0001",
            "consent_id": "dsi-image-only-bundle",
            "resource_id": "dsi-image-only-resource",
            "scope": "image_processing",
            "consent_version": "dsi-v1",
            "granted": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        },
    )
    assert granted.status_code == 200, granted.text
    denied = _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle="dsi-image-only-bundle",
        resource="dsi-image-only-resource",
        scopes=["image_processing", "facial_geometry_analysis"],
        version="dsi-v1",
    )
    assert denied.status_code == 403



def test_dsi_strict_expiry_rejects_legacy_null_expiry_without_breaking_legacy_verification(client):
    created = _grant_resource_consent(
        client,
        subject="user-verified-1",
        bundle="dsi-legacy-expiry-bundle",
        resource="dsi-legacy-expiry-resource",
        scope="facial_geometry_analysis",
        receipt="dsi-legacy-expiry-receipt",
        expires_at=None,
    )
    assert created.status_code == 200, created.text

    strict = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": "dsi-legacy-expiry-bundle",
            "consent_version": "media-2026-11-v1",
            "resource_id": "dsi-legacy-expiry-resource",
            "required_scopes": ["facial_geometry_analysis"],
            "require_expiring": True,
        },
    )
    assert strict.status_code == 403
    assert strict.json()["detail"]["code"] == "CONSENT_EXPIRY_REQUIRED"

    legacy_compatible = _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle="dsi-legacy-expiry-bundle",
        resource="dsi-legacy-expiry-resource",
        scopes=["facial_geometry_analysis"],
    )
    assert legacy_compatible.status_code == 200, legacy_compatible.text
    assert legacy_compatible.json()["expires_at"] is None


def test_dsi_strict_expiry_requires_every_scope_in_bundle_to_expire(client):
    _grant_resource_consent(
        client,
        subject="user-verified-1",
        bundle="dsi-mixed-expiry-bundle",
        resource="dsi-mixed-expiry-resource",
        scope="image_processing",
        receipt="dsi-mixed-expiry-image",
        expires_at=None,
    )
    _grant_resource_consent(
        client,
        subject="user-verified-1",
        bundle="dsi-mixed-expiry-bundle",
        resource="dsi-mixed-expiry-resource",
        scope="facial_geometry_analysis",
        receipt="dsi-mixed-expiry-face",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    )
    response = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": "dsi-mixed-expiry-bundle",
            "consent_version": "media-2026-11-v1",
            "resource_id": "dsi-mixed-expiry-resource",
            "required_scopes": ["image_processing", "facial_geometry_analysis"],
            "require_expiring": True,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_EXPIRY_REQUIRED"



DSI_CHALLENGE_SCOPES = {
    "cosmetic_skin_analysis": ["image_processing", "skin_analysis"],
    "facial_geometry_analysis": ["image_processing", "facial_geometry_analysis"],
    "body_tone_analysis": ["image_processing", "body_tone_analysis"],
    "appearance_correction": ["image_processing", "appearance_correction"],
}


def _grant_dsi_capture_bundle(client, *, purpose="facial_geometry_analysis", subject="user-verified-1",
                              bundle="dsi-capture-bundle-0001", resource="dsi-capture-resource-0001",
                              expires_at=None):
    expiry = expires_at or (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    receipt_ids = []
    for scope in DSI_CHALLENGE_SCOPES[purpose]:
        receipt_id = f"{bundle}-{scope}"
        response = client.post(
            "/v1/tal/consents",
            params={"subject_id": subject},
            headers=auth(),
            json={
                "receipt_id": receipt_id,
                "consent_id": bundle,
                "resource_id": resource,
                "scope": scope,
                "consent_version": "dsi-capture-v1",
                "granted": True,
                "expires_at": expiry,
            },
        )
        assert response.status_code == 200, response.text
        receipt_ids.append(receipt_id)
    return receipt_ids


def _issue_dsi_capture_challenge(client, *, purpose="facial_geometry_analysis", subject="user-verified-1",
                                 bundle="dsi-capture-bundle-0001", resource="dsi-capture-resource-0001",
                                 headers=None):
    return client.post(
        "/internal/v1/dsi/capture-challenges",
        headers=headers or dsi_capture_auth(),
        json={
            "subject_id": subject,
            "consent_id": bundle,
            "consent_version": "dsi-capture-v1",
            "resource_id": resource,
            "purpose": purpose,
        },
    )


def _capture_verification_payload(challenge, **overrides):
    nonce = challenge["nonce_b64url"]
    digest = __import__("hashlib").sha256(__import__("base64").urlsafe_b64decode(nonce + "=")).hexdigest()
    manifest = "a" * 64
    payload = {
        "nonce_b64url": nonce,
        "manifest_sha256": manifest,
        "image_sha256": "b" * 64,
        "device_pipeline_fingerprint_sha256": "c" * 64,
        "key_attestation_challenge_sha256": digest,
        "play_integrity_request_hash": manifest,
        "package_name": "com.cirvanna.app",
        "package_certificate_sha256": "d" * 64,
        "app_version": "1.2.3",
        "sdk_version": "0.1.0",
        "verifier_policy_version": "dsi-android-policy-v1",
        "key_security_level": "trusted_environment",
        "verified_boot_state": "verified",
        "app_recognition_verdict": "PLAY_RECOGNIZED",
        "account_licensing_verdict": "LICENSED",
        "device_integrity_verdicts": ["MEETS_DEVICE_INTEGRITY"],
    }
    payload.update(overrides)
    return payload


def test_dsi_capture_challenge_requires_separate_service_credential_and_exact_expiring_consent(client):
    no_auth = _issue_dsi_capture_challenge(client, headers=auth())
    assert no_auth.status_code == 401
    assert no_auth.json()["detail"]["code"] == "DSI_CAPTURE_INTERNAL_AUTH_REQUIRED"

    not_configured = client.post(
        "/internal/v1/dsi/capture-challenges",
        headers={"Authorization": "Bearer " + TOKEN},
        json={
            "subject_id": "user-verified-1",
            "consent_id": "missing-dsi-bundle",
            "consent_version": "dsi-capture-v1",
            "resource_id": "dsi-capture-resource-0001",
            "purpose": "facial_geometry_analysis",
        },
    )
    assert not_configured.status_code == 401

    denied = _issue_dsi_capture_challenge(client)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "DSI_CAPTURE_CONSENT_INCOMPLETE"

    expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _grant_dsi_capture_bundle(client, expires_at=expiry)
    issued = _issue_dsi_capture_challenge(client)
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["status"] == "issued"
    assert body["nonce_bytes"] == 32
    assert len(__import__("base64").urlsafe_b64decode(body["nonce_b64url"] + "=")) == 32
    assert body["required_scopes"] == ["image_processing", "facial_geometry_analysis"]
    assert set(body["consent_receipt_ids"]) == {
        "dsi-capture-bundle-0001-image_processing",
        "dsi-capture-bundle-0001-facial_geometry_analysis",
    }
    issued_at = datetime.fromisoformat(body["issued_at"])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(0) < expires_at - issued_at <= timedelta(seconds=main.DSI_CAPTURE_CHALLENGE_TTL_SECONDS)

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    row = db.get(main.DSICaptureChallengeRow, body["challenge_id"])
    assert row is not None
    assert row.nonce_sha256 == body["nonce_sha256"]
    assert body["nonce_b64url"] not in row.nonce_sha256
    assert not hasattr(row, "nonce_b64url")
    db.close()


def test_dsi_capture_challenge_refuses_unbound_resource_subject_and_expiryless_legacy_consent(client):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _grant_dsi_capture_bundle(
        client, bundle="dsi-capture-bound", resource="resource-bound", expires_at=expiry,
    )
    wrong_resource = _issue_dsi_capture_challenge(
        client, bundle="dsi-capture-bound", resource="resource-other",
    )
    assert wrong_resource.status_code == 403
    wrong_subject = _issue_dsi_capture_challenge(
        client, bundle="dsi-capture-bound", resource="resource-bound", subject="another-subject",
    )
    assert wrong_subject.status_code == 403

    for scope in DSI_CHALLENGE_SCOPES["facial_geometry_analysis"]:
        created = client.post(
            "/v1/tal/consents",
            params={"subject_id": "user-verified-1"},
            headers=auth(),
            json={
                "receipt_id": f"dsi-legacy-{scope}",
                "consent_id": "dsi-legacy-no-expiry",
                "resource_id": "dsi-legacy-resource",
                "scope": scope,
                "consent_version": "dsi-capture-v1",
                "granted": True,
            },
        )
        assert created.status_code == 200, created.text
    legacy = _issue_dsi_capture_challenge(
        client, bundle="dsi-legacy-no-expiry", resource="dsi-legacy-resource",
    )
    assert legacy.status_code == 403
    assert legacy.json()["detail"]["code"] == "DSI_CAPTURE_CONSENT_INCOMPLETE"


def test_dsi_capture_challenge_is_consumed_once_and_receipt_checks_exact_digests(client):
    _grant_dsi_capture_bundle(client)
    challenge_response = _issue_dsi_capture_challenge(client)
    assert challenge_response.status_code == 200, challenge_response.text
    challenge = challenge_response.json()
    payload = _capture_verification_payload(challenge)
    consumed = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=payload,
    )
    assert consumed.status_code == 200, consumed.text
    receipt = consumed.json()["receipt"]
    assert consumed.json()["status"] == "verified_receipt_created"
    assert receipt["verification_status"] == "verified_by_trusted_vision_service"
    assert receipt["purpose"] == "facial_geometry_analysis"
    assert receipt["image_sha256"] == payload["image_sha256"]
    assert receipt["manifest_sha256"] == payload["manifest_sha256"]
    assert receipt["expires_at"]

    replay = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=payload,
    )
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "DSI_CAPTURE_CHALLENGE_ALREADY_CONSUMED"

    verified = client.post(
        "/internal/v1/dsi/capture-receipts/verify",
        headers=dsi_capture_auth(),
        json={
            "receipt_id": receipt["receipt_id"],
            "subject_id": "user-verified-1",
            "resource_id": "dsi-capture-resource-0001",
            "purpose": "facial_geometry_analysis",
            "manifest_sha256": payload["manifest_sha256"],
            "image_sha256": payload["image_sha256"],
            "device_pipeline_fingerprint_sha256": payload["device_pipeline_fingerprint_sha256"],
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True

    changed_digest = client.post(
        "/internal/v1/dsi/capture-receipts/verify",
        headers=dsi_capture_auth(),
        json={
            "receipt_id": receipt["receipt_id"],
            "subject_id": "user-verified-1",
            "resource_id": "dsi-capture-resource-0001",
            "purpose": "facial_geometry_analysis",
            "manifest_sha256": "e" * 64,
            "image_sha256": payload["image_sha256"],
            "device_pipeline_fingerprint_sha256": payload["device_pipeline_fingerprint_sha256"],
        },
    )
    assert changed_digest.status_code == 403
    assert changed_digest.json()["detail"]["code"] == "DSI_CAPTURE_RECEIPT_SCOPE_OR_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    "overrides,expected_code",
    [
        ({"key_attestation_challenge_sha256": "f" * 64}, "validation"),
        ({"play_integrity_request_hash": "f" * 64}, "validation"),
        ({"key_security_level": "software"}, "validation"),
        ({"verified_boot_state": "unverified"}, "validation"),
        ({"app_recognition_verdict": "UNRECOGNIZED_VERSION"}, "validation"),
        ({"account_licensing_verdict": "UNLICENSED"}, "validation"),
        ({"device_integrity_verdicts": ["MEETS_BASIC_INTEGRITY"]}, "validation"),
    ],
)
def test_dsi_capture_receipt_rejects_unqualified_verifier_claims(client, overrides, expected_code):
    _grant_dsi_capture_bundle(client)
    challenge = _issue_dsi_capture_challenge(client).json()
    payload = _capture_verification_payload(challenge, **overrides)
    response = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=payload,
    )
    assert response.status_code == 422


def test_dsi_capture_challenge_cannot_be_consumed_after_consent_revocation(client):
    receipt_ids = _grant_dsi_capture_bundle(client)
    challenge = _issue_dsi_capture_challenge(client).json()
    revoked = client.post(
        f"/v1/tal/consents/{receipt_ids[0]}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    response = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=_capture_verification_payload(challenge),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DSI_CAPTURE_CONSENT_INCOMPLETE"


def test_dsi_capture_receipt_is_denied_after_consent_revocation(client):
    receipt_ids = _grant_dsi_capture_bundle(client)
    challenge = _issue_dsi_capture_challenge(client).json()
    payload = _capture_verification_payload(challenge)
    consumed = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=payload,
    )
    assert consumed.status_code == 200
    receipt = consumed.json()["receipt"]
    revoked = client.post(
        f"/v1/tal/consents/{receipt_ids[0]}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    verification = client.post(
        "/internal/v1/dsi/capture-receipts/verify",
        headers=dsi_capture_auth(),
        json={
            "receipt_id": receipt["receipt_id"],
            "subject_id": "user-verified-1",
            "resource_id": "dsi-capture-resource-0001",
            "purpose": "facial_geometry_analysis",
            "manifest_sha256": payload["manifest_sha256"],
            "image_sha256": payload["image_sha256"],
            "device_pipeline_fingerprint_sha256": payload["device_pipeline_fingerprint_sha256"],
        },
    )
    assert verification.status_code == 403
    assert verification.json()["detail"]["code"] == "DSI_CAPTURE_CONSENT_INCOMPLETE"


def test_dsi_capture_challenge_rejects_invalid_or_expired_nonce_and_user_deletion_removes_receipts(client):
    _grant_dsi_capture_bundle(client)
    challenge = _issue_dsi_capture_challenge(client).json()
    wrong_nonce_payload = _capture_verification_payload(
        challenge,
        nonce_b64url=__import__("base64").urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii"),
        key_attestation_challenge_sha256=__import__("hashlib").sha256(b"x" * 32).hexdigest(),
    )
    mismatch = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=wrong_nonce_payload,
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"]["code"] == "DSI_CAPTURE_CHALLENGE_NONCE_MISMATCH"

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    row = db.get(main.DSICaptureChallengeRow, challenge["challenge_id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    db.close()
    expired = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=_capture_verification_payload(challenge),
    )
    assert expired.status_code == 410

    # Create and consume a fresh challenge, then prove user deletion removes
    # the challenge and receipt records together with the canonical consent.
    _grant_dsi_capture_bundle(
        client, bundle="dsi-delete-bundle", resource="dsi-delete-resource",
    )
    fresh = _issue_dsi_capture_challenge(
        client, bundle="dsi-delete-bundle", resource="dsi-delete-resource",
    ).json()
    consumed = client.post(
        f"/internal/v1/dsi/capture-challenges/{fresh['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=_capture_verification_payload(fresh),
    )
    assert consumed.status_code == 200
    deleted = client.delete("/v1/tal/users/user-verified-1", headers=auth())
    assert deleted.status_code == 200
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    assert db.query(main.DSICaptureChallengeRow).filter_by(subject_id="user-verified-1").count() == 0
    assert db.query(main.DSICaptureVerificationReceiptRow).filter_by(subject_id="user-verified-1").count() == 0
    db.close()


def test_dsi_capture_retention_purges_expired_challenge_and_receipt_state(client):
    _grant_dsi_capture_bundle(client)
    challenge = _issue_dsi_capture_challenge(client).json()
    payload = _capture_verification_payload(challenge)
    consumed = client.post(
        f"/internal/v1/dsi/capture-challenges/{challenge['challenge_id']}/consume",
        headers=dsi_capture_auth(),
        json=payload,
    )
    assert consumed.status_code == 200
    receipt_id = consumed.json()["receipt"]["receipt_id"]

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    challenge_row = db.get(main.DSICaptureChallengeRow, challenge["challenge_id"])
    receipt_row = db.get(main.DSICaptureVerificationReceiptRow, receipt_id)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    challenge_row.expires_at = past
    receipt_row.expires_at = past
    db.commit()
    db.close()

    purged = client.post(
        "/internal/retention/purge",
        headers={**auth(), "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes"},
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["purged_dsi_capture_challenges"] == 1
    assert purged.json()["purged_dsi_capture_receipts"] == 1



def test_skin_analysis_consent_derives_subject_pseudonym_and_issues_digest_bound_cil_receipt(client):
    granted = skin_analysis_consent(client)
    assert granted.status_code == 200, granted.text
    assert "provider_contributor_token" not in granted.json()

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        row = db.get(main.ConsentReceipt, "skin-analysis-receipt-001")
        assert row is not None
        token = row.provider_contributor_token
        assert token is not None and token.startswith("hmac-sha256:")
        assert len(token) == len("hmac-sha256:") + 64
    finally:
        db.close()

    image_digest = "a" * 64
    issued = client.post(
        "/internal/v1/consents/skin-analysis-provider-receipts?subject_id=user-verified-1",
        headers=cil_consent_issuer_auth(),
        json={
            "receipt_id": "skin-analysis-receipt-001",
            "image_sha256": image_digest,
            "verified_subject_age_years": 24,
        },
    )
    assert issued.status_code == 200, issued.text
    parts = issued.json()["receipt"].split(".")
    assert len(parts) == 2
    encoded, signature = parts
    expected = hmac.new(
        b"shared-cil-skin-analysis-consent-key-at-least-32-bytes",
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(signature, expected)
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert payload["type"] == "consent"
    assert payload["purpose"] == "perfectcorp_skin_analysis"
    assert payload["provider"] == "perfectcorp"
    assert payload["subject_token"] == token
    assert payload["consent_id"] == "skin-analysis-bundle-001"
    assert payload["consent_receipt_id"] == "skin-analysis-receipt-001"
    assert payload["resource_id"] == "skin-analysis-resource-001"
    assert payload["consent_expires_at"] > payload["expires_at"]
    assert payload["image_sha256"] == image_digest
    assert payload["subject_age_years"] == 24
    assert payload["single_subject"] is True
    assert "subject_id" not in payload


def test_skin_analysis_receipt_issuer_rejects_general_internal_service_token(client):
    assert skin_analysis_consent(client).status_code == 200
    response = client.post(
        "/internal/v1/consents/skin-analysis-provider-receipts?subject_id=user-verified-1",
        headers=auth(),
        json={
            "receipt_id": "skin-analysis-receipt-001",
            "image_sha256": "c" * 64,
            "verified_subject_age_years": 24,
        },
    )
    assert response.status_code == 401


def test_skin_analysis_provider_receipt_rejects_non_owner_and_non_adult(client):
    assert skin_analysis_consent(client).status_code == 200
    wrong_owner = client.post(
        "/internal/v1/consents/skin-analysis-provider-receipts?subject_id=another-user",
        headers=cil_consent_issuer_auth(),
        json={
            "receipt_id": "skin-analysis-receipt-001",
            "image_sha256": "b" * 64,
            "verified_subject_age_years": 24,
        },
    )
    assert wrong_owner.status_code == 403

    underage = client.post(
        "/internal/v1/consents/skin-analysis-provider-receipts?subject_id=user-verified-1",
        headers=cil_consent_issuer_auth(),
        json={
            "receipt_id": "skin-analysis-receipt-001",
            "image_sha256": "b" * 64,
            "verified_subject_age_years": 17,
        },
    )
    assert underage.status_code == 422


def test_skin_analysis_consent_id_cannot_be_reused_by_another_subject(client):
    assert skin_analysis_consent(client, subject="user-verified-1", bundle="globally-unique-skin-consent").status_code == 200
    duplicate = skin_analysis_consent(
        client,
        subject="user-verified-2",
        bundle="globally-unique-skin-consent",
        resource="skin-analysis-resource-other",
        receipt="skin-analysis-receipt-other",
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "SKIN_ANALYSIS_CONSENT_ID_MUST_BE_UNIQUE"


def test_skin_analysis_revocation_dispatches_exact_cil_provider_cleanup(client, monkeypatch):
    assert skin_analysis_consent(client).status_code == 200
    image_bundle_scope = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "skin-analysis-image-processing-001",
            "scope": "image_processing",
            "consent_id": "skin-analysis-bundle-001",
            "resource_id": "skin-analysis-resource-001",
            "consent_version": "image-processing-v1",
            "granted": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        },
    )
    assert image_bundle_scope.status_code == 200, image_bundle_scope.text

    observed = []
    async def notify(item):
        observed.append({
            "consent_id": item.consent_id,
            "resource_id": item.resource_id,
            "receipt_id": item.receipt_id,
            "contributor_token": item.contributor_token,
            "command_id": item.command_id,
        })
        return {
            "revoked": True,
            "consent_id": item.consent_id,
            "revocation_reference": item.command_id,
            "matched_tasks": 2,
            "deleted_tasks": 1,
            "waiting_for_terminal": 1,
        }

    monkeypatch.setattr(main, "_notify_cil_provider_of_consent_revocation", notify)
    revoked = client.post(
        "/v1/tal/consents/skin-analysis-image-processing-001/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["cil_provider_cleanup_status"] == "delivered"
    assert revoked.json()["twin_cleanup_status"] == "not_applicable"
    assert len(observed) == 1
    event = observed[0]
    assert "subject_id" not in event
    assert event["consent_id"] == "skin-analysis-bundle-001"
    assert event["resource_id"] == "skin-analysis-resource-001"
    assert event["receipt_id"] == "skin-analysis-receipt-001"
    assert event["contributor_token"].startswith("hmac-sha256:")
    assert event["command_id"].startswith("cil-provider-consent-revocation:")

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        outbox = db.get(main.CILProviderConsentRevocationOutbox, event["command_id"])
        assert outbox is not None
        assert outbox.status == "delivered"
        assert outbox.matched_tasks == 2
        assert outbox.deleted_tasks == 1
        assert outbox.waiting_for_terminal == 1
        assert outbox.attempts == 0
    finally:
        db.close()


def test_denied_skin_analysis_consent_replay_reports_delivered_cil_cleanup(client, monkeypatch):
    bundle = "skin-analysis-denied-replay-bundle"
    resource = "skin-analysis-denied-replay-resource"
    grant = skin_analysis_consent(
        client,
        bundle=bundle,
        resource=resource,
        receipt="skin-analysis-denied-replay-grant",
    )
    assert grant.status_code == 200, grant.text

    calls = []
    async def notify(item):
        calls.append(item.command_id)
        return {
            "revoked": True,
            "consent_id": item.consent_id,
            "revocation_reference": item.command_id,
            "matched_tasks": 1,
            "deleted_tasks": 1,
            "waiting_for_terminal": 0,
        }

    monkeypatch.setattr(main, "_notify_cil_provider_of_consent_revocation", notify)
    payload = {
        "receipt_id": "skin-analysis-denied-replay-event",
        "scope": "skin_analysis",
        "consent_id": bundle,
        "resource_id": resource,
        "consent_version": "skin-analysis-v1",
        "granted": False,
    }
    first = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["cil_provider_cleanup_status"] == "delivered"
    assert len(calls) == 1

    replay = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "replayed"
    assert replay.json()["cil_provider_cleanup_status"] == "delivered"
    assert calls == [calls[0]]

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        outbox = db.query(main.CILProviderConsentRevocationOutbox).filter_by(
            revocation_receipt_id=payload["receipt_id"]
        ).one()
        assert outbox.status == "delivered"
        assert outbox.completed_at is not None
    finally:
        db.close()


def test_cil_provider_revocation_command_uses_unambiguous_field_framing(client):
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    token = "hmac-sha256:" + "c" * 64
    now = datetime.now(timezone.utc)
    first = main.ConsentReceipt(
        receipt_id="skin-colon-receipt-0001",
        subject_id="user-verified-1",
        consent_id="bundle-0001:resource-0002",
        resource_id="xxx",
        scope="skin_analysis",
        consent_version="skin-analysis-v1",
        granted=True,
        granted_at=now,
        expires_at=now + timedelta(minutes=30),
        provider_contributor_token=token,
    )
    second = main.ConsentReceipt(
        receipt_id="skin-colon-receipt-0002",
        subject_id="user-verified-1",
        consent_id="bundle-0001",
        resource_id="resource-0002:xxx",
        scope="skin_analysis",
        consent_version="skin-analysis-v1",
        granted=True,
        granted_at=now,
        expires_at=now + timedelta(minutes=30),
        provider_contributor_token=token,
    )
    try:
        db.add_all([first, second])
        db.flush()
        event_receipt = "skin-revoke-event-colon-0001"
        first_command = main._queue_cil_provider_consent_cleanup(
            db, first, revocation_receipt_id=event_receipt
        )[0]
        second_command = main._queue_cil_provider_consent_cleanup(
            db, second, revocation_receipt_id=event_receipt
        )[0]
        assert first_command.command_id != second_command.command_id
        assert first_command.consent_id == first.consent_id
        assert second_command.consent_id == second.consent_id
        assert first_command.revocation_receipt_id == event_receipt
        assert second_command.revocation_receipt_id == event_receipt
    finally:
        db.rollback()
        db.close()


def test_cil_provider_revocation_failure_is_durable_and_retryable(client, monkeypatch):
    assert skin_analysis_consent(
        client,
        bundle="skin-analysis-retry-bundle",
        resource="skin-analysis-retry-resource",
        receipt="skin-analysis-retry-receipt",
    ).status_code == 200

    async def unavailable(_item):
        raise RuntimeError("CIL_PROVIDER_REVOCATION_UNAVAILABLE")

    monkeypatch.setattr(main, "_notify_cil_provider_of_consent_revocation", unavailable)
    revoked = client.post(
        "/v1/tal/consents/skin-analysis-retry-receipt/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["cil_provider_cleanup_status"] == "pending"

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        pending = db.query(main.CILProviderConsentRevocationOutbox).one()
        command_id = pending.command_id
        assert pending.status == "pending"
        assert pending.attempts == 1
        assert pending.last_error_code == "CIL_PROVIDER_REVOCATION_UNAVAILABLE"
    finally:
        db.close()

    delivered = []
    async def recovered(item):
        delivered.append(item.command_id)
        return {
            "revoked": True,
            "consent_id": item.consent_id,
            "revocation_reference": item.command_id,
            "matched_tasks": 1,
            "deleted_tasks": 1,
            "waiting_for_terminal": 0,
        }

    monkeypatch.setattr(main, "_notify_cil_provider_of_consent_revocation", recovered)
    retry = client.post(
        "/internal/v1/cil/provider-consent-revocations/dispatch?limit=10",
        headers=auth(),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json() == {"processed": 1, "completed": 1, "already_delivered": 0, "delivered": 1, "failed": 0, "pending": False}
    assert delivered == [command_id]

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        completed = db.get(main.CILProviderConsentRevocationOutbox, command_id)
        assert completed.status == "delivered"
        assert completed.attempts == 1
        assert completed.waiting_for_terminal == 0
    finally:
        db.close()


def test_expired_skin_analysis_consent_queues_provider_cleanup(client, monkeypatch):
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    assert skin_analysis_consent(
        client,
        bundle="skin-analysis-expired-bundle",
        resource="skin-analysis-expired-resource",
        receipt="skin-analysis-expired-receipt",
        expires_at=expires_at,
    ).status_code == 200
    image_scope = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "skin-analysis-expired-image-scope",
            "scope": "image_processing",
            "consent_id": "skin-analysis-expired-bundle",
            "resource_id": "skin-analysis-expired-resource",
            "consent_version": "image-processing-v1",
            "granted": True,
            "expires_at": expires_at,
        },
    )
    assert image_scope.status_code == 200, image_scope.text

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        db.query(main.ConsentReceipt).filter(
            main.ConsentReceipt.receipt_id == "skin-analysis-expired-receipt"
        ).update({
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)
        }, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    observed = []
    async def notify(item):
        observed.append(item.command_id)
        return {
            "revoked": True,
            "consent_id": item.consent_id,
            "revocation_reference": item.command_id,
            "matched_tasks": 1,
            "deleted_tasks": 0,
            "waiting_for_terminal": 1,
        }

    monkeypatch.setattr(main, "_notify_cil_provider_of_consent_revocation", notify)
    purged = client.post(
        "/internal/retention/purge",
        headers={
            **auth(),
            "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes",
        },
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["cil_provider_cleanup_commands"] == 1
    assert purged.json()["cil_provider_cleanup_delivered"] == 1
    assert purged.json()["cil_provider_cleanup_pending"] is False
    assert len(observed) == 1

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        receipt = db.get(main.ConsentReceipt, "skin-analysis-expired-receipt")
        image_receipt = db.get(main.ConsentReceipt, "skin-analysis-expired-image-scope")
        assert receipt.revoked_at is not None
        assert image_receipt.revoked_at is not None
    finally:
        db.close()


def test_cil_live_consent_verifier_requires_dedicated_token_and_returns_canonical_expiry(client):
    expiry = datetime.now(timezone.utc) + timedelta(hours=2)
    assert skin_analysis_consent(client, expires_at=expiry.isoformat()).status_code == 200
    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        consent_row = db.get(main.ConsentReceipt, "skin-analysis-receipt-001")
        contributor_token = consent_row.provider_contributor_token
    finally:
        db.close()
    payload = {
        "receipt_id": "skin-analysis-receipt-001",
        "consent_id": "skin-analysis-bundle-001",
        "resource_id": "skin-analysis-resource-001",
        "contributor_token": contributor_token,
        "image_sha256": "f" * 64,
    }
    url = "/internal/v1/consents/skin-analysis-provider-receipts/verify"
    wrong = client.post(url, headers=auth(), json=payload)
    assert wrong.status_code == 401

    verified = client.post(url, headers=cil_consent_verifier_auth(), json=payload)
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["status"] == "active"
    assert body["consent_receipt_id"] == payload["receipt_id"]
    assert body["consent_id"] == payload["consent_id"]
    assert body["resource_id"] == payload["resource_id"]
    assert body["contributor_token"] == payload["contributor_token"]
    assert body["image_sha256"] == payload["image_sha256"]
    assert body["consent_expires_at"] > int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    revoked = client.post(
        "/v1/tal/consents/skin-analysis-receipt-001/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200
    denied = client.post(url, headers=cil_consent_verifier_auth(), json=payload)
    assert denied.status_code == 403


def test_stale_revocation_retry_does_not_withdraw_a_later_grant(client):
    first = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "profile-consent-old",
            "scope": "profile_storage",
            "consent_id": "profile-bundle-reused",
            "resource_id": "profile-resource-1",
            "consent_version": "v1",
            "granted": True,
        },
    )
    assert first.status_code == 200
    revoked = client.post(
        "/v1/tal/consents/profile-consent-old/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200

    second = client.post(
        "/v1/tal/consents",
        params={"subject_id": "user-verified-1"},
        headers=auth(),
        json={
            "receipt_id": "profile-consent-new",
            "scope": "profile_storage",
            "consent_id": "profile-bundle-reused",
            "resource_id": "profile-resource-1",
            "consent_version": "v2",
            "granted": True,
        },
    )
    assert second.status_code == 200
    retry = client.post(
        "/v1/tal/consents/profile-consent-old/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "already_revoked"
    active = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": "profile-bundle-reused",
            "required_scopes": ["profile_storage"],
            "resource_id": "profile-resource-1",
        },
    )
    assert active.status_code == 200
    assert active.json()["active"] is True


def test_expired_legacy_skin_analysis_receipt_cannot_revoke_new_active_bundle(client):
    active = _grant_resource_consent(
        client,
        subject="user-verified-1",
        bundle="skin-analysis-new-active-bundle",
        resource="skin-analysis-new-active-resource",
        scope="skin_analysis",
        receipt="skin-analysis-new-active-receipt",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    )
    assert active.status_code == 200

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        db.add(main.ConsentReceipt(
            receipt_id="skin-analysis-legacy-expired",
            subject_id="user-verified-1",
            consent_id="legacy-skin-analysis-consent",
            resource_id=None,
            scope="skin_analysis",
            consent_version="legacy-v1",
            granted=True,
            granted_at=datetime.now(timezone.utc) - timedelta(days=3),
            revoked_at=None,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            provider_contributor_token=None,
        ))
        db.commit()
    finally:
        db.close()

    stale_revoke = client.post(
        "/v1/tal/consents/skin-analysis-legacy-expired/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert stale_revoke.status_code == 200
    assert stale_revoke.json()["status"] == "already_expired"

    verified = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": "skin-analysis-new-active-bundle",
            "required_scopes": ["skin_analysis"],
            "resource_id": "skin-analysis-new-active-resource",
            "require_expiring": True,
        },
    )
    assert verified.status_code == 200
    assert verified.json()["active"] is True


def test_image_processing_expiry_in_twin_bundle_queues_twin_asset_cleanup(client, monkeypatch):
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    for index, scope in enumerate(["image_processing", "body_measurements", "virtual_twin_storage"]):
        assert _grant_resource_consent(
            client,
            subject="user-verified-1",
            bundle="bundle-twin-image-expiry",
            resource="twin-image-expiry",
            scope=scope,
            receipt=f"twin-image-expiry-{index:02d}",
            expires_at=expires,
        ).status_code == 200

    db = main._session_factory(os.environ["IDENTITY_DATABASE_URL"])()
    try:
        db.query(main.ConsentReceipt).filter(
            main.ConsentReceipt.receipt_id == "twin-image-expiry-00"
        ).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    observed = []
    async def notify(item):
        observed.append((item.consent_id, item.resource_id))
        return {"status": "pending", "twins_queued": 1}

    monkeypatch.setattr(main, "_notify_twin_registry_of_revocation", notify)
    purge = client.post(
        "/internal/retention/purge",
        headers={**auth(), "X-Identity-Cron-Token": "identity-cron-token-that-is-at-least-32-bytes"},
    )
    assert purge.status_code == 200, purge.text
    assert purge.json()["twin_cleanup_commands"] == 1
    assert purge.json()["twin_cleanup_delivered"] == 1
    assert observed == [("bundle-twin-image-expiry", "twin-image-expiry")]
    # Expiry of the image-processing scope withdraws the exact resource bundle,
    # not merely the expired row, so sibling Twin scopes cannot remain active.
    assert _verify_resource_consent(
        client,
        subject="user-verified-1",
        bundle="bundle-twin-image-expiry",
        resource="twin-image-expiry",
    ).status_code == 403


def test_cil_and_twin_cleanup_dispatch_batch_more_than_one_hundred_commands(monkeypatch):
    cil_batches = []
    twin_batches = []

    async def fake_cil(_db, *, limit, command_ids):
        cil_batches.append((limit, len(command_ids)))
        return {
            "processed": len(command_ids), "completed": len(command_ids),
            "already_delivered": 0, "delivered": len(command_ids),
            "failed": 0, "pending": False,
        }

    async def fake_twin(_db, *, limit, command_ids):
        twin_batches.append((limit, len(command_ids)))
        return {
            "processed": len(command_ids), "completed": len(command_ids),
            "already_delivered": 0, "delivered": len(command_ids),
            "failed": 0, "pending": False,
        }

    monkeypatch.setattr(main, "_dispatch_cil_provider_consent_revocations", fake_cil)
    monkeypatch.setattr(main, "_dispatch_twin_consent_revocations", fake_twin)
    command_ids = [f"cleanup-command-{index:03d}" for index in range(205)]

    cil = asyncio.run(main._dispatch_cil_provider_consent_revocations_batched(None, command_ids))
    twin = asyncio.run(main._dispatch_twin_consent_revocations_batched(None, command_ids))

    assert cil_batches == [(100, 100), (100, 100), (5, 5)]
    assert twin_batches == [(100, 100), (100, 100), (5, 5)]
    assert cil["delivered"] == 205 and cil["failed"] == 0 and cil["pending"] is False
    assert twin["delivered"] == 205 and twin["failed"] == 0 and twin["pending"] is False



def test_usi_accepts_only_explicitly_allowlisted_new_style_dimensions(client):
    assert consent(client, scope="profile_storage", receipt="receipt-style-axis-0001").status_code == 200
    accepted = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 0,
        "consent_receipt_id": "receipt-style-axis-0001",
        "preferences": [{
            "preference_id": "pnelly-style-axis-0001",
            "attribute": "culture:contemporary-african-luxury",
            "weight": 0.8,
            "active": True,
            "source": "pnelly_user_confirmed",
            "source_request_id": "pnelly-style-request-0001",
        }],
    })
    assert accepted.status_code == 200, accepted.text
    rejected = client.put("/v1/profiles/user-verified-1", headers=auth(), json={
        "expected_version": 1,
        "consent_receipt_id": "receipt-style-axis-0001",
        "preferences": [{
            "preference_id": "pnelly-style-axis-0002",
            "attribute": "culture:unreviewed-free-text",
            "weight": 0.8,
            "active": True,
            "source": "pnelly_user_confirmed",
            "source_request_id": "pnelly-style-request-0002",
        }],
    })
    assert rejected.status_code == 422

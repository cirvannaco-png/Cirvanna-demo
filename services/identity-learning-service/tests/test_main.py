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



def _grant_resource_consent(client, *, subject, bundle, resource, scope, receipt):
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={
            "receipt_id": receipt,
            "consent_id": bundle,
            "resource_id": resource,
            "scope": scope,
            "consent_version": "media-2026-11-v1",
            "granted": True,
        },
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
    deleted = client.delete("/v1/tal/users/user-verified-1", headers=auth())
    assert deleted.status_code == 200
    assert deleted.json()["deleted_events"] == 1
    assert client.get("/v1/tal/export/user-verified-1", headers=auth()).json()["profile"] is None
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

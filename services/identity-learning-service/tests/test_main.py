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


def test_resource_bound_consent_bundle_verifies_exact_scopes_and_twin(client):
    consent_id = "twin-consent-bundle-001"
    twin_id = "twin-owned-by-user-001"
    scopes = ["image_processing", "body_measurements", "twin_storage"]
    for index, scope in enumerate(scopes, start=1):
        response = client.post(
            "/v1/tal/consents",
            params={"subject_id": "user-verified-1"},
            headers=auth(),
            json={
                "receipt_id": f"twin-receipt-{index:04d}",
                "consent_id": consent_id,
                "resource_id": twin_id,
                "scope": scope,
                "consent_version": "virtual-twin-v1",
                "granted": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["consent_id"] == consent_id
        assert response.json()["resource_id"] == twin_id

    verified = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": consent_id,
            "resource_id": twin_id,
            "required_scopes": scopes,
        },
    )
    wrong_twin = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": consent_id,
            "resource_id": "another-twin-0001",
            "required_scopes": scopes,
        },
    )
    missing_scope = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": consent_id,
            "resource_id": twin_id,
            "required_scopes": ["image_processing", "virtual_try_on"],
        },
    )
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert set(verified.json()["granted_scopes"]) == set(scopes)
    assert verified.json()["consent_version"] == "virtual-twin-v1"
    assert wrong_twin.status_code == 403
    assert missing_scope.status_code == 403


def test_resource_bound_consent_bundle_revocation_blocks_try_on(client):
    consent_id = "tryon-consent-bundle-001"
    twin_id = "twin-owned-by-user-002"
    receipt_ids = []
    for index, scope in enumerate(["image_processing", "virtual_try_on", "twin_storage"], start=1):
        receipt_id = f"tryon-receipt-{index:04d}"
        receipt_ids.append(receipt_id)
        client.post(
            "/v1/tal/consents",
            params={"subject_id": "user-verified-1"},
            headers=auth(),
            json={
                "receipt_id": receipt_id,
                "consent_id": consent_id,
                "resource_id": twin_id,
                "scope": scope,
                "consent_version": "virtual-try-on-v1",
                "granted": True,
            },
        )
    before = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1", "consent_id": consent_id,
            "resource_id": twin_id,
            "required_scopes": ["image_processing", "virtual_try_on", "twin_storage"],
        },
    )
    revoked = client.post(
        f"/v1/tal/consents/{receipt_ids[1]}/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    after = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-verified-1", "consent_id": consent_id,
            "resource_id": twin_id,
            "required_scopes": ["image_processing", "virtual_try_on", "twin_storage"],
        },
    )
    assert before.status_code == 200
    assert revoked.status_code == 200
    assert after.status_code == 403



def resource_consent(client, *, subject, bundle, resource, scope, receipt):
    return client.post(
        "/v1/tal/consents",
        params={"subject_id": subject},
        headers=auth(),
        json={
            "receipt_id": receipt,
            "consent_id": bundle,
            "resource_id": resource,
            "scope": scope,
            "consent_version": "media-v1",
            "granted": True,
        },
    )


def test_resource_bound_consent_revocation_does_not_cross_resource(client):
    for resource, bundle, prefix in (
        ("twin-resource-1", "bundle-resource-1", "receipt-resource-1"),
        ("twin-resource-2", "bundle-resource-2", "receipt-resource-2"),
    ):
        for suffix, scope in (("image", "image_processing"), ("storage", "twin_storage")):
            response = resource_consent(
                client, subject="user-verified-1", bundle=bundle, resource=resource,
                scope=scope, receipt=prefix + "-" + suffix,
            )
            assert response.status_code == 200

    verify = client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={
            "subject_id": "user-verified-1",
            "consent_id": "bundle-resource-1",
            "resource_id": "twin-resource-1",
            "required_scopes": ["image_processing", "twin_storage"],
        },
    )
    assert verify.status_code == 200
    assert verify.json()["consent_version"] == "media-v1"

    revoked = client.post(
        "/v1/tal/consents/receipt-resource-1-image/revoke?subject_id=user-verified-1",
        headers=auth(),
    )
    assert revoked.status_code == 200

    all_same_resource = client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={"subject_id": "user-verified-1", "consent_id": "bundle-resource-1",
              "resource_id": "twin-resource-1", "required_scopes": ["image_processing", "twin_storage"]},
    )
    first = client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={"subject_id": "user-verified-1", "consent_id": "bundle-resource-1",
              "resource_id": "twin-resource-1", "required_scopes": ["twin_storage"]},
    )
    second = client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={"subject_id": "user-verified-1", "consent_id": "bundle-resource-2",
              "resource_id": "twin-resource-2", "required_scopes": ["image_processing", "twin_storage"]},
    )
    assert first.status_code == 200  # storage receipt remains active
    assert second.status_code == 200  # other Twin consent remains active


def test_resource_bound_denial_does_not_revoke_other_resources(client):
    resource_consent(
        client, subject="user-verified-1", bundle="bundle-a", resource="twin-a",
        scope="twin_storage", receipt="receipt-twin-a",
    )
    resource_consent(
        client, subject="user-verified-1", bundle="bundle-b", resource="twin-b",
        scope="twin_storage", receipt="receipt-twin-b",
    )
    denied = client.post(
        "/v1/tal/consents", params={"subject_id": "user-verified-1"}, headers=auth(),
        json={
            "receipt_id": "receipt-denial-a", "consent_id": "bundle-a",
            "resource_id": "twin-a", "scope": "twin_storage",
            "consent_version": "media-v1", "granted": False,
        },
    )
    assert denied.status_code == 200
    assert client.post(
        "/internal/v1/consents/verify", headers=auth(),
        json={"subject_id": "user-verified-1", "consent_id": "bundle-b",
              "resource_id": "twin-b", "required_scopes": ["twin_storage"]},
    ).status_code == 200



def test_wardrobe_image_storage_is_a_valid_resource_bound_consent_scope(client):
    saved = resource_consent(
        client,
        subject="user-wardrobe-1",
        bundle="wardrobe-consent-1",
        resource="wardrobe-item-1",
        scope="wardrobe_image_storage",
        receipt="wardrobe-image-receipt-1",
    )
    assert saved.status_code == 200
    verified = client.post(
        "/internal/v1/consents/verify",
        headers=auth(),
        json={
            "subject_id": "user-wardrobe-1",
            "consent_id": "wardrobe-consent-1",
            "resource_id": "wardrobe-item-1",
            "required_scopes": ["image_processing", "wardrobe_image_storage"],
        },
    )
    assert verified.status_code == 200

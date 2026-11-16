from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from appearance_intelligence import FidelityGate  # noqa: E402
from app import main, store  # noqa: E402

SERVICE_TOKEN = "appearance-service-test-token-with-more-than-32-bytes"
RENDERER_TOKEN = "appearance-renderer-test-token-with-more-than-32-bytes"
SUBJECT = "user-appearance-001"
LOOK_ID = "look-appearance-001"
CONSENT_ID = "consent-appearance-001"
SOURCE_ASSET = "00000000-0000-4000-8000-000000000101"
OUTPUT_ASSET = "00000000-0000-4000-8000-000000000201"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, **kwargs):
        self.calls = []
        self.asset_authorized = True
        self.twin_authorized = True
        self.consent_allowed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, *, headers=None, params=None):
        self.calls.append(("GET", url, params))
        if "/v1/tal/consents/" in url:
            return FakeResponse([
                {
                    "receipt_id": "appearance-delete-receipt-001",
                    "consent_id": CONSENT_ID,
                    "resource_id": LOOK_ID,
                    "granted": True,
                    "revoked_at": None,
                },
                {
                    "receipt_id": "appearance-branch-receipt-001",
                    "consent_id": "consent-branch-from-render-001",
                    "resource_id": "look-branch-from-render-001",
                    "granted": True,
                    "revoked_at": None,
                },
            ])
        pytest.fail(f"Unexpected provider GET URL: {url}")

    async def delete(self, url, *, headers=None):
        self.calls.append(("DELETE", url, headers))
        if "/v1/assets/" in url:
            return FakeResponse({}, 204)
        pytest.fail(f"Unexpected provider DELETE URL: {url}")

    async def post(self, url, *, headers=None, json=None, params=None):
        self.calls.append((url, json))
        if url.endswith("/revoke"):
            return FakeResponse({"status": "revoked"})
        if url.endswith("/internal/v1/consents/verify"):
            scopes = json["required_scopes"]
            if not self.consent_allowed:
                return FakeResponse({"detail": {"code": "CONSENT_NOT_ACTIVE"}}, 403)
            return FakeResponse({
                "verified": True,
                "active": True,
                "subject_id": json["subject_id"],
                "consent_id": json["consent_id"],
                "resource_id": json["resource_id"],
                "consent_version": "appearance-look-session-v1",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
                "granted_scopes": scopes,
            })
        if url.endswith("/internal/v1/assets/authorize"):
            return FakeResponse({
                "authorized": self.asset_authorized,
                "active": self.asset_authorized,
                "subject_id": json["subject_id"],
                "asset_id": json["asset_id"],
                "purpose": json["purpose"],
                "parent_id": json["parent_id"],
            }, 200 if self.asset_authorized else 404)
        if url.endswith("/internal/v1/twins/authorize"):
            return FakeResponse({
                "authorized": self.twin_authorized,
                "active": self.twin_authorized,
                "subject_id": json["subject_id"],
                "twin_id": json["twin_id"],
                "representation_type": "full_body_mesh",
                "source_image_asset_ids": [SOURCE_ASSET],
            }, 200 if self.twin_authorized else 404)
        pytest.fail(f"Unexpected provider URL: {url}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "appearance.db")
    monkeypatch.setenv("APPEARANCE_DATABASE_URL", url)
    monkeypatch.setenv("APPEARANCE_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("APPEARANCE_RENDERER_TOKEN", RENDERER_TOKEN)
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-provider-token-with-more-than-32-bytes")
    monkeypatch.setenv("ASSET_SERVICE_URL", "https://asset.example.test")
    monkeypatch.setenv("ASSET_SERVICE_TOKEN", "asset-provider-token-with-more-than-32-bytes")
    monkeypatch.setenv("TWIN_REGISTRY_API_URL", "https://twin.example.test")
    monkeypatch.setenv("TWIN_REGISTRY_API_TOKEN", "twin-provider-token-with-more-than-32-bytes")

    store.engine.cache_clear()
    store.session_factory.cache_clear()
    store.Base.metadata.create_all(bind=store.engine(url))

    provider = FakeAsyncClient()
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: provider)
    with TestClient(main.app) as test_client:
        test_client.app.state.provider = provider
        yield test_client
    store.session_factory.cache_clear()
    store.engine.cache_clear()


def auth():
    return {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def renderer_auth():
    return {"Authorization": f"Bearer {RENDERER_TOKEN}"}


def source_payload(**overrides):
    body = {
        "look_id": LOOK_ID,
        "subject_id": SUBJECT,
        "consent_id": CONSENT_ID,
        "idempotency_key": "create-look-command-001",
        "base": {
            "kind": "source_photo",
            "source_asset_ids": [SOURCE_ASSET],
        },
        "operations": [{
            "operation_id": "hair-edit-001",
            "component": "hairstyle",
            "action": "replace",
            "description": "Long layered curls with a side part",
        }],
    }
    body.update(overrides)
    return body


def create_source_look(client):
    response = client.post("/v1/looks", headers=auth(), json=source_payload())
    assert response.status_code == 201, response.text
    return response.json()["look"]


def all_passing_gates():
    return [{"gate": gate.value, "status": "pass"} for gate in FidelityGate]


def test_internal_auth_is_required(client):
    assert client.post("/v1/looks", json=source_payload()).status_code == 401
    assert client.get(f"/v1/looks/{LOOK_ID}", params={"subject_id": SUBJECT}).status_code == 401


def test_create_look_binds_consent_private_source_asset_and_owner(client):
    created = client.post("/v1/looks", headers=auth(), json=source_payload())
    assert created.status_code == 201, created.text
    look = created.json()["look"]
    assert look["look_id"] == LOOK_ID
    assert look["subject_id"] == SUBJECT
    assert look["version"] == 1
    assert look["base"]["kind"] == "source_photo"
    assert look["base"]["source_asset_parent_id"] == LOOK_ID
    assert look["operations"][0]["component"] == "hairstyle"

    provider_calls = client.app.state.provider.calls
    assert provider_calls[0][0].endswith("/internal/v1/consents/verify")
    assert provider_calls[0][1]["required_scopes"] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]
    assert provider_calls[1][1]["purpose"] == "appearance_source_image"
    assert provider_calls[1][1]["parent_id"] == LOOK_ID


def test_create_is_idempotent_and_changed_payload_conflicts(client):
    first = client.post("/v1/looks", headers=auth(), json=source_payload())
    replay = client.post("/v1/looks", headers=auth(), json=source_payload())
    changed = source_payload(operations=[])
    changed["look_id"] = LOOK_ID
    changed["idempotency_key"] = "create-look-command-001"

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    assert replay.json()["look"]["version"] == 1
    conflict = client.post("/v1/looks", headers=auth(), json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "APPEARANCE_IDEMPOTENCY_CONFLICT"


def test_source_asset_owner_or_parent_mismatch_fails_closed(client):
    client.app.state.provider.asset_authorized = False
    response = client.post("/v1/looks", headers=auth(), json=source_payload())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "APPEARANCE_ASSET_NOT_FOUND_OR_NOT_AUTHORIZED"


def test_twin_base_uses_registry_authorization_and_registry_source_lineage(client):
    payload = source_payload(
        look_id="look-from-twin-001",
        consent_id="consent-from-twin-001",
        idempotency_key="create-twin-look-command-001",
        base={"kind": "virtual_twin", "twin_id": "virtual-twin-001"},
    )
    response = client.post("/v1/looks", headers=auth(), json=payload)
    assert response.status_code == 201, response.text
    look = response.json()["look"]
    assert look["base"]["kind"] == "virtual_twin"
    assert look["base"]["twin_id"] == "virtual-twin-001"
    assert look["base"]["source_asset_parent_id"] == "virtual-twin-001"
    assert look["base"]["source_asset_ids"] == [SOURCE_ASSET]
    provider_urls = [call[0] for call in client.app.state.provider.calls]
    assert any(url.endswith("/internal/v1/twins/authorize") for url in provider_urls)


def test_twin_registry_denial_prevents_look_creation(client):
    client.app.state.provider.twin_authorized = False
    payload = source_payload(
        look_id="look-from-denied-twin-001",
        consent_id="consent-denied-twin-001",
        idempotency_key="create-denied-twin-command-001",
        base={"kind": "virtual_twin", "twin_id": "virtual-twin-denied-001"},
    )
    response = client.post("/v1/looks", headers=auth(), json=payload)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "APPEARANCE_TWIN_NOT_FOUND_OR_NOT_AUTHORIZED"


def test_component_edit_preserves_other_components_and_uses_optimistic_version(client):
    create_source_look(client)
    payload = {
        "subject_id": SUBJECT,
        "expected_version": 1,
        "command_id": "edit-hair-colour-command-001",
        "operation": {
            "operation_id": "hair-colour-edit-001",
            "component": "hair_colour",
            "action": "replace",
            "description": "Deep burgundy with natural dark roots",
        },
    }
    updated = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json=payload)
    assert updated.status_code == 200, updated.text
    look = updated.json()["look"]
    assert look["version"] == 2
    assert {item["component"] for item in look["operations"]} == {"hairstyle", "hair_colour"}

    replay = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json=payload)
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    assert replay.json()["look"]["version"] == 2

    changed_payload = dict(payload)
    changed_payload["operation"] = {
        "operation_id": "different-hair-colour-edit",
        "component": "hair_colour",
        "action": "replace",
        "description": "Platinum blonde",
    }
    changed_replay = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json=changed_payload)
    assert changed_replay.status_code == 409
    assert changed_replay.json()["detail"]["code"] == "APPEARANCE_IDEMPOTENCY_CONFLICT"

    stale = dict(payload)
    stale["expected_version"] = 1
    stale["command_id"] = "edit-stale-command-001"
    stale["operation"]["operation_id"] = "stale-edit-001"
    conflict = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json=stale)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "APPEARANCE_VERSION_CONFLICT"


def test_reset_and_undo_create_new_versions_without_mutating_history(client):
    create_source_look(client)
    edit = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json={
        "subject_id": SUBJECT,
        "expected_version": 1,
        "command_id": "edit-for-reset-command-001",
        "operation": {
            "operation_id": "beard-edit-001",
            "component": "facial_hair",
            "action": "apply",
            "description": "Short boxed beard with clean cheek line",
        },
    })
    assert edit.status_code == 200

    reset = client.post(f"/v1/looks/{LOOK_ID}/reset", headers=auth(), json={
        "subject_id": SUBJECT, "expected_version": 2, "command_id": "reset-look-command-001",
    })
    assert reset.status_code == 200
    assert reset.json()["look"]["version"] == 3
    assert reset.json()["look"]["operations"] == []

    undo = client.post(f"/v1/looks/{LOOK_ID}/undo", headers=auth(), json={
        "subject_id": SUBJECT,
        "expected_version": 3,
        "command_id": "undo-look-command-001",
        "target_version": 2,
    })
    assert undo.status_code == 200
    assert undo.json()["look"]["version"] == 4
    assert {item["component"] for item in undo.json()["look"]["operations"]} == {
        "hairstyle", "facial_hair",
    }

    versions = client.get(f"/v1/looks/{LOOK_ID}/versions", headers=auth(), params={"subject_id": SUBJECT})
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()["versions"]] == [1, 2, 3, 4]
    assert versions.json()["versions"][2]["operations"] == []


def test_expired_or_revoked_appearance_consent_blocks_look_reads(client):
    create_source_look(client)
    client.app.state.provider.consent_allowed = False
    current = client.get(f"/v1/looks/{LOOK_ID}", headers=auth(), params={"subject_id": SUBJECT})
    versions = client.get(
        f"/v1/looks/{LOOK_ID}/versions", headers=auth(), params={"subject_id": SUBJECT},
    )
    compared = client.get(
        f"/v1/looks/{LOOK_ID}/compare", headers=auth(),
        params={"subject_id": SUBJECT, "from_version": 1, "to_version": 1},
    )
    assert current.status_code == 403
    assert versions.status_code == 403
    assert compared.status_code == 403


def test_compare_versions_and_favorite_are_owner_scoped(client):
    create_source_look(client)
    edit = client.post(f"/v1/looks/{LOOK_ID}/operations", headers=auth(), json={
        "subject_id": SUBJECT,
        "expected_version": 1,
        "command_id": "compare-edit-command-001",
        "operation": {
            "operation_id": "lip-edit-001",
            "component": "lipstick",
            "action": "apply",
            "description": "Warm terracotta satin finish",
        },
    })
    assert edit.status_code == 200

    compared = client.get(
        f"/v1/looks/{LOOK_ID}/compare",
        headers=auth(),
        params={"subject_id": SUBJECT, "from_version": 1, "to_version": 2},
    )
    assert compared.status_code == 200
    assert compared.json()["changed_components"] == ["lipstick"]

    favorite = client.post(f"/v1/looks/{LOOK_ID}/favorite", headers=auth(), json={
        "subject_id": SUBJECT, "is_favorite": True,
    })
    assert favorite.status_code == 200
    assert favorite.json()["look"]["is_favorite"] is True

    foreign = client.get(
        f"/v1/looks/{LOOK_ID}",
        headers=auth(),
        params={"subject_id": "another-user-001"},
    )
    assert foreign.status_code == 404


def test_render_result_requires_separate_renderer_auth_and_complete_fidelity(client):
    create_source_look(client)
    denied = client.post(f"/internal/v1/looks/{LOOK_ID}/render-result", headers=auth(), json={})
    assert denied.status_code == 401

    renderer_version = "renderer-v1@sha256:" + ("a" * 64)
    payload = {
        "subject_id": SUBJECT,
        "version": 1,
        "output_asset_id": OUTPUT_ASSET,
        "renderer_id": "renderer-hair-v1",
        "renderer_version": renderer_version,
        "assessment_id": "assessment-render-001",
        "checks": all_passing_gates(),
    }
    attached = client.post(
        f"/internal/v1/looks/{LOOK_ID}/render-result",
        headers=renderer_auth(),
        json=payload,
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["fidelity"]["disposition"] == "releasable"


def test_failed_fidelity_report_cannot_be_attached_or_used_as_branch_base(client):
    create_source_look(client)
    renderer_version = "renderer-v1@sha256:" + ("b" * 64)
    checks = all_passing_gates()
    checks[0] = {"gate": "identity_consistency", "status": "fail"}
    response = client.post(
        f"/internal/v1/looks/{LOOK_ID}/render-result",
        headers=renderer_auth(),
        json={
            "subject_id": SUBJECT,
            "version": 1,
            "output_asset_id": OUTPUT_ASSET,
            "renderer_id": "renderer-hair-v1",
            "renderer_version": renderer_version,
            "assessment_id": "assessment-failed-001",
            "checks": checks,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APPEARANCE_RENDER_NOT_RELEASABLE"

    branch = client.post(f"/v1/looks/{LOOK_ID}/branch", headers=auth(), json={
        "subject_id": SUBJECT,
        "new_look_id": "look-branch-without-render",
        "consent_id": "consent-branch-without-render",
        "command_id": "branch-without-render-command",
        "parent_version": 1,
    })
    assert branch.status_code == 409
    assert branch.json()["detail"]["code"] == "APPEARANCE_PARENT_RENDER_NOT_READY"


def test_branch_from_passing_render_retains_original_lineage(client):
    create_source_look(client)
    renderer_version = "renderer-v1@sha256:" + ("c" * 64)
    attached = client.post(
        f"/internal/v1/looks/{LOOK_ID}/render-result",
        headers=renderer_auth(),
        json={
            "subject_id": SUBJECT,
            "version": 1,
            "output_asset_id": OUTPUT_ASSET,
            "renderer_id": "renderer-v1",
            "renderer_version": renderer_version,
            "assessment_id": "assessment-branch-001",
            "checks": all_passing_gates(),
        },
    )
    assert attached.status_code == 200

    branch = client.post(f"/v1/looks/{LOOK_ID}/branch", headers=auth(), json={
        "subject_id": SUBJECT,
        "new_look_id": "look-branch-from-render-001",
        "consent_id": "consent-branch-from-render-001",
        "command_id": "branch-from-render-command-001",
        "parent_version": 1,
    })
    assert branch.status_code == 201, branch.text
    base = branch.json()["look"]["base"]
    assert base["kind"] == "previous_render"
    assert base["parent_look_id"] == LOOK_ID
    assert base["parent_render_asset_id"] == OUTPUT_ASSET
    assert base["source_asset_ids"] == [OUTPUT_ASSET]
    assert base["source_asset_parent_id"] == LOOK_ID


def test_look_creation_rejects_url_as_source_asset(client):
    payload = source_payload(base={
        "kind": "source_photo",
        "source_asset_ids": ["https://example.test/photo.png"],
    })
    response = client.post("/v1/looks", headers=auth(), json=payload)
    assert response.status_code == 422


def test_expired_look_consent_context_is_private_and_returns_minimum_scopes(client):
    create_source_look(client)
    context = client.get(
        f"/internal/v1/looks/{LOOK_ID}/consent-context",
        headers=auth(),
        params={"subject_id": SUBJECT},
    )
    assert context.status_code == 200
    assert context.json()["look_id"] == LOOK_ID
    assert context.json()["subject_id"] == SUBJECT
    assert context.json()["base_kind"] == "source_photo"
    assert context.json()["required_scopes"] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]
    assert "source_asset_ids" not in context.text
    assert client.get(
        f"/internal/v1/looks/{LOOK_ID}/consent-context",
        params={"subject_id": SUBJECT},
    ).status_code == 401


def test_renew_consent_rebinds_active_bundle_and_preserves_history(client):
    create_source_look(client)
    renewed = client.post(
        f"/internal/v1/looks/{LOOK_ID}/renew-consent",
        headers=auth(),
        json={
            "subject_id": SUBJECT,
            "consent_id": "consent-appearance-renewed-001",
            "consent_version": "appearance-look-session-v1",
        },
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["status"] == "renewed"
    assert renewed.json()["granted_scopes"] == [
        "appearance_session_storage", "appearance_source_storage", "image_processing",
    ]

    current = client.get(
        f"/v1/looks/{LOOK_ID}",
        headers=auth(),
        params={"subject_id": SUBJECT},
    )
    assert current.status_code == 200
    assert current.json()["look"]["consent_id"] == "consent-appearance-renewed-001"
    assert current.json()["look"]["consent_version"] == "appearance-look-session-v1"

    with store.open_session(__import__("os").environ["APPEARANCE_DATABASE_URL"]) as db:
        events = db.query(store.AppearanceLookConsentEventRow).filter_by(
            subject_id=SUBJECT, look_id=LOOK_ID,
        ).all()
        assert len(events) == 1
        assert events[0].previous_consent_id == CONSENT_ID
        assert events[0].consent_id == "consent-appearance-renewed-001"
        assert events[0].granted_scopes == [
            "appearance_session_storage", "appearance_source_storage", "image_processing",
        ]


def test_renewal_revokes_old_bundle_only_after_new_bundle_is_verified(client):
    create_source_look(client)
    response = client.post(
        f"/internal/v1/looks/{LOOK_ID}/renew-consent",
        headers=auth(),
        json={
            "subject_id": SUBJECT,
            "consent_id": "consent-appearance-renewed-002",
            "consent_version": "appearance-look-session-v1",
        },
    )
    assert response.status_code == 200, response.text
    revocations = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and len(call) == 2 and call[0].endswith("/revoke")
    ]
    assert len(revocations) == 1
    assert revocations[0][0].endswith("/appearance-delete-receipt-001/revoke")
    assert revocations[0][1]["subject_id"] == SUBJECT

    consent_verify_calls = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and len(call) == 2
        and call[0].endswith("/internal/v1/consents/verify")
    ]
    assert len(consent_verify_calls) == 1
    assert consent_verify_calls[0][1]["consent_id"] == "consent-appearance-renewed-002"


def test_consent_version_mismatch_does_not_revoke_previous_bundle(client):
    create_source_look(client)
    response = client.post(
        f"/internal/v1/looks/{LOOK_ID}/renew-consent",
        headers=auth(),
        json={
            "subject_id": SUBJECT,
            "consent_id": "consent-appearance-wrong-version",
            "consent_version": "wrong-appearance-policy-version",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "APPEARANCE_CONSENT_VERSION_MISMATCH"
    revocations = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and len(call) == 2 and call[0].endswith("/revoke")
    ]
    assert revocations == []


def test_denied_renewal_does_not_replace_previous_consent(client):
    create_source_look(client)
    client.app.state.provider.consent_allowed = False
    denied = client.post(
        f"/internal/v1/looks/{LOOK_ID}/renew-consent",
        headers=auth(),
        json={
            "subject_id": SUBJECT,
            "consent_id": "consent-appearance-renew-denied",
            "consent_version": "appearance-look-session-v1",
        },
    )
    assert denied.status_code == 403
    client.app.state.provider.consent_allowed = True
    current = client.get(
        f"/v1/looks/{LOOK_ID}",
        headers=auth(),
        params={"subject_id": SUBJECT},
    )
    assert current.status_code == 200
    assert current.json()["look"]["consent_id"] == CONSENT_ID


def test_list_saved_looks_is_owner_scoped_and_exposes_only_minimal_metadata(client):
    create_source_look(client)
    response = client.get("/v1/looks", headers=auth(), params={"subject_id": SUBJECT})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    summary = response.json()["looks"][0]
    assert summary["look_id"] == LOOK_ID
    assert summary["subject_id"] == SUBJECT
    assert summary["version"] == 1
    assert summary["base_kind"] == "source_photo"
    assert summary["consent_required"] is False
    assert "source_asset_ids" not in summary
    assert "operations" not in summary

    client.app.state.provider.consent_allowed = False
    expired = client.get("/v1/looks", headers=auth(), params={"subject_id": SUBJECT})
    assert expired.status_code == 200
    assert expired.json()["looks"][0]["consent_required"] is True


def test_delete_look_revokes_exact_consent_and_deletes_private_source_asset(client):
    create_source_look(client)
    response = client.request(
        "DELETE",
        f"/v1/looks/{LOOK_ID}",
        headers=auth(),
        json={
            "subject_id": SUBJECT,
            "expected_version": 1,
            "command_id": "delete-appearance-look-001",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"
    deletion = response.json()["deletion"]
    assert deletion["status"] == "completed"
    assert deletion["consent_revoked"] is True
    assert deletion["pending_asset_count"] == 0

    consent_calls = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and len(call) == 2 and call[0].endswith("/revoke")
    ]
    assert len(consent_calls) == 1
    asset_calls = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and call[0] == "DELETE" and "/v1/assets/" in call[1]
    ]
    assert len(asset_calls) == 1
    assert asset_calls[0][2]["X-Asset-Owner-ID"] == SUBJECT
    assert asset_calls[0][2]["Idempotency-Key"].startswith("appearance-delete-")

    hidden = client.get(
        f"/v1/looks/{LOOK_ID}", headers=auth(), params={"subject_id": SUBJECT},
    )
    assert hidden.status_code == 404

    with store.open_session(__import__("os").environ["APPEARANCE_DATABASE_URL"]) as db:
        job = db.query(store.AppearanceLookDeletionRow).filter_by(look_id=LOOK_ID).one()
        assert job.status == "completed"
        assert job.consent_revoked is True
        assert job.pending_asset_references == []


def test_delete_parent_look_preserves_render_asset_referenced_by_live_child(client):
    create_source_look(client)
    renderer_version = "renderer-v1@sha256:" + ("d" * 64)
    attached = client.post(
        f"/internal/v1/looks/{LOOK_ID}/render-result",
        headers=renderer_auth(),
        json={
            "subject_id": SUBJECT,
            "version": 1,
            "output_asset_id": OUTPUT_ASSET,
            "renderer_id": "renderer-v1",
            "renderer_version": renderer_version,
            "assessment_id": "assessment-delete-parent-001",
            "checks": all_passing_gates(),
        },
    )
    assert attached.status_code == 200
    branch = client.post(f"/v1/looks/{LOOK_ID}/branch", headers=auth(), json={
        "subject_id": SUBJECT,
        "new_look_id": "look-branch-from-render-001",
        "consent_id": "consent-branch-from-render-001",
        "command_id": "branch-delete-parent-001",
        "parent_version": 1,
    })
    assert branch.status_code == 201, branch.text

    deleted = client.request("DELETE", f"/v1/looks/{LOOK_ID}", headers=auth(), json={
        "subject_id": SUBJECT, "expected_version": 1,
        "command_id": "delete-parent-look-001",
    })
    assert deleted.status_code == 200, deleted.text
    with store.open_session(__import__("os").environ["APPEARANCE_DATABASE_URL"]) as db:
        job = db.query(store.AppearanceLookDeletionRow).filter_by(look_id=LOOK_ID).one()
        deleted_ids = {item["asset_id"] for item in job.asset_references}
        assert SOURCE_ASSET in deleted_ids
        assert OUTPUT_ASSET not in deleted_ids
    child = client.get(
        "/v1/looks/look-branch-from-render-001",
        headers=auth(),
        params={"subject_id": SUBJECT},
    )
    assert child.status_code == 200
    assert child.json()["look"]["base"]["parent_render_asset_id"] == OUTPUT_ASSET


def test_deleting_last_child_releases_parent_render_asset(client):
    create_source_look(client)
    renderer_version = "renderer-v1@sha256:" + ("e" * 64)
    client.post(
        f"/internal/v1/looks/{LOOK_ID}/render-result",
        headers=renderer_auth(),
        json={
            "subject_id": SUBJECT, "version": 1, "output_asset_id": OUTPUT_ASSET,
            "renderer_id": "renderer-v1", "renderer_version": renderer_version,
            "assessment_id": "assessment-delete-child-001", "checks": all_passing_gates(),
        },
    )
    client.post(f"/v1/looks/{LOOK_ID}/branch", headers=auth(), json={
        "subject_id": SUBJECT, "new_look_id": "look-branch-from-render-001",
        "consent_id": "consent-branch-from-render-001",
        "command_id": "branch-delete-child-001", "parent_version": 1,
    })
    client.request("DELETE", f"/v1/looks/{LOOK_ID}", headers=auth(), json={
        "subject_id": SUBJECT, "expected_version": 1,
        "command_id": "delete-source-before-child-001",
    })
    deleted_child = client.request(
        "DELETE", "/v1/looks/look-branch-from-render-001", headers=auth(), json={
            "subject_id": SUBJECT, "expected_version": 1,
            "command_id": "delete-last-child-001",
        },
    )
    assert deleted_child.status_code == 200, deleted_child.text
    assert deleted_child.json()["deletion"]["status"] == "completed"
    assert deleted_child.json()["deletion"]["consent_revoked"] is True
    last_asset_delete = [
        call for call in client.app.state.provider.calls
        if isinstance(call, tuple) and call[0] == "DELETE"
        and call[1].endswith("/" + OUTPUT_ASSET)
    ]
    assert len(last_asset_delete) == 1


def test_deletion_worker_recovers_interrupted_processing_jobs(client):
    create_source_look(client)
    now = datetime.now(timezone.utc)
    job_id = "00000000-0000-4000-8000-000000000909"
    with store.open_session(__import__("os").environ["APPEARANCE_DATABASE_URL"]) as db:
        row = store.get_look(db, SUBJECT, LOOK_ID)
        row.status = "deleted"
        db.add(store.AppearanceLookDeletionRow(
            job_id=job_id,
            look_id=LOOK_ID,
            subject_id=SUBJECT,
            consent_id=CONSENT_ID,
            command_id="interrupted-delete-command-001",
            payload_sha256="f" * 64,
            consent_revoked=False,
            asset_references=[{
                "asset_id": SOURCE_ASSET,
                "purpose": "appearance_source_image",
                "parent_id": LOOK_ID,
            }],
            pending_asset_references=[{
                "asset_id": SOURCE_ASSET,
                "purpose": "appearance_source_image",
                "parent_id": LOOK_ID,
            }],
            status="processing",
            attempt_count=1,
            last_error="worker interrupted",
            created_at=now - timedelta(minutes=20),
            updated_at=now - timedelta(minutes=10),
        ))
        db.commit()

    response = client.post("/internal/v1/deletions/process", headers=auth(), params={"limit": 10})
    assert response.status_code == 200, response.text
    assert response.json()["processed"] == 1
    assert response.json()["completed"] == 1
    with store.open_session(__import__("os").environ["APPEARANCE_DATABASE_URL"]) as db:
        job = db.get(store.AppearanceLookDeletionRow, job_id)
        assert job.status == "completed"
        assert job.consent_revoked is True
        assert job.pending_asset_references == []

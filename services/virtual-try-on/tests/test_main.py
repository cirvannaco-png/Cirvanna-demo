from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "virtual-try-on-test-token"


class FixtureConsentVerifier:
    def __init__(self, result=True):
        self.result = result

    def verify(self, subject_id, consent):
        return self.result


class FixtureAssetAuthorizer:
    def __init__(self, result=True):
        self.result = result

    def authorize(self, subject_id, twin_id, product_id, person_image_asset_id, garment_image_asset_id):
        return self.result


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TRY_ON_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "RENDERER", None)
    monkeypatch.setattr(main, "CONSENT_VERIFIER", None)
    monkeypatch.setattr(main, "ASSET_AUTHORIZER", None)
    return TestClient(main.app)


def headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def payload(**overrides):
    value = {
        "request_id": "request-test-001",
        "subject_id": "subject-test-001",
        "twin_id": "twin-test-001",
        "product_id": "product-test-001",
        "person_image_asset_id": "person-asset-001",
        "garment_image_asset_id": "garment-asset-001",
        "garment_category": "upper_body",
        "consent": {
            "consent_id": "consent-test-0001",
            "image_processing": True,
            "virtual_try_on": True,
            "retention_policy": "ephemeral",
        },
    }
    value.update(overrides)
    return value


def install_test_authorizers(monkeypatch, consent=True, assets=True):
    monkeypatch.setattr(main, "CONSENT_VERIFIER", FixtureConsentVerifier(consent))
    monkeypatch.setattr(main, "ASSET_AUTHORIZER", FixtureAssetAuthorizer(assets))


def test_health_is_liveness_only(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == main.SERVICE_NAME


def test_ready_fails_closed_until_all_providers_exist(client):
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "validated_renderer_consent_and_asset_authorization_adapters_not_integrated"


def test_capabilities_do_not_claim_rendering_is_live(client):
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["orchestration_api"] is True
    assert data["renderer_configured"] is False
    assert data["consent_verifier_configured"] is False
    assert data["asset_authorizer_configured"] is False
    assert data["raw_image_upload"] is False
    assert data["arbitrary_remote_urls"] is False


def test_try_on_requires_authentication(client):
    response = client.post("/v1/try-ons", json=payload())
    assert response.status_code == 401


@pytest.mark.parametrize("consent_field", ["image_processing", "virtual_try_on"])
def test_try_on_requires_each_consent_flag(client, consent_field):
    body = payload()
    body["consent"][consent_field] = False
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_REQUIRED"


def test_try_on_fails_closed_without_providers_and_claims_no_output(client):
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TRY_ON_DEPENDENCIES_NOT_CONFIGURED"
    assert "no output was created" in response.json()["detail"]["message"].lower()


@pytest.mark.parametrize("asset_id", [
    "https://example.com/person.jpg",
    "../private/person.jpg",
    "/tmp/person.jpg",
    "file:///tmp/person.jpg",
])
def test_external_urls_and_paths_are_rejected_as_asset_ids(client, asset_id):
    body = payload(person_image_asset_id=asset_id)
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422


def test_non_ephemeral_retention_is_rejected(client):
    body = payload()
    body["consent"]["retention_policy"] = "permanent"
    response = client.post("/v1/try-ons", json=body, headers=headers())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "RETENTION_POLICY_UNSUPPORTED"


def test_unverified_consent_blocks_rendering(client, monkeypatch):
    install_test_authorizers(monkeypatch, consent=False)
    class FixtureRenderer:
        renderer_id = "fixture-renderer"
        renderer_version = "fixture-only"
        def render(self, request):
            raise AssertionError("renderer must not be called without verified consent")
    monkeypatch.setattr(main, "RENDERER", FixtureRenderer())
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONSENT_NOT_VERIFIED"


def test_unauthorized_assets_block_rendering(client, monkeypatch):
    install_test_authorizers(monkeypatch, assets=False)
    class FixtureRenderer:
        renderer_id = "fixture-renderer"
        renderer_version = "fixture-only"
        def render(self, request):
            raise AssertionError("renderer must not be called for unauthorized assets")
    monkeypatch.setattr(main, "RENDERER", FixtureRenderer())
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ASSET_ACCESS_DENIED"


def test_renderer_success_is_only_returned_after_authorization_and_real_asset_id(client, monkeypatch):
    install_test_authorizers(monkeypatch)
    class FixtureRenderer:
        renderer_id = "fixture-renderer"
        renderer_version = "fixture-only"
        def render(self, request):
            assert request.consent.image_processing
            assert request.consent.virtual_try_on
            return "rendered-asset-001"
    monkeypatch.setattr(main, "RENDERER", FixtureRenderer())
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "complete"
    assert result["output_asset_id"] == "rendered-asset-001"
    assert result["renderer_version"] == "fixture-only"


def test_renderer_failure_does_not_leak_provider_error(client, monkeypatch):
    install_test_authorizers(monkeypatch)
    class BrokenRenderer:
        renderer_id = "fixture-renderer"
        renderer_version = "fixture-only"
        def render(self, request):
            raise RuntimeError("private upstream credential and request payload")
    monkeypatch.setattr(main, "RENDERER", BrokenRenderer())
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "RENDERER_FAILED"
    assert "credential" not in response.text
    assert "request payload" not in response.text


def test_invalid_renderer_output_is_rejected(client, monkeypatch):
    install_test_authorizers(monkeypatch)
    class BadRenderer:
        renderer_id = "fixture-renderer"
        renderer_version = "fixture-only"
        def render(self, request):
            return "https://example.com/fake-output.png"
    monkeypatch.setattr(main, "RENDERER", BadRenderer())
    response = client.post("/v1/try-ons", json=payload(), headers=headers())
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "RENDERER_INVALID_OUTPUT"

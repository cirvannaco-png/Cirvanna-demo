from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app import privacy_policy


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def receipt(**overrides):
    data = {
        "decision": "PASS",
        "current": True,
        "policy_version": "registry-2026-11-05.1",
        "jurisdiction_resolution_complete": True,
        "policy_conflicts_resolved": True,
        "lawful_basis_authorized": True,
        "cross_border_transfers_authorized": True,
        "policy_sha256": "a" * 64,
        "applicable_jurisdictions": ["JURISDICTION_A", "JURISDICTION_B"],
        "facial_recognition_allowed": False,
        "face_identity_analysis_allowed": False,
        "child_facial_identity_analysis_allowed": False,
        "child_behavioural_profiling_allowed": False,
        "public_unmasked_face_exposure_allowed": False,
        "image_retention_allowed": False,
        "guardian_consent_required": True,
        "public_sharing_allowed": False,
    }
    data.update(overrides)
    return data


def configure(monkeypatch):
    monkeypatch.setenv("PRIVACY_POLICY_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_POLICY_API_TOKEN", "privacy-policy-test-token-at-least-32-bytes")


def test_unknown_photographed_people_status_fails_closed_without_policy_call(monkeypatch):
    monkeypatch.delenv("PRIVACY_POLICY_API_URL", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-1", "unknown"))
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "CHILD_SAFETY_STATUS_UNCONFIRMED"


def test_missing_policy_registry_fails_closed(monkeypatch):
    monkeypatch.delenv("PRIVACY_POLICY_API_URL", raising=False)
    monkeypatch.delenv("PRIVACY_POLICY_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-1", "adults_only"))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "PRIVACY_POLICY_REGISTRY_NOT_CONFIGURED"


def test_current_multi_jurisdiction_policy_receipt_is_required_and_returned(monkeypatch):
    configure(monkeypatch)
    fake = FakeAsyncClient(FakeResponse(receipt()))
    monkeypatch.setattr(privacy_policy.httpx, "AsyncClient", lambda **kwargs: fake)
    result = asyncio.run(privacy_policy.authorize_click_it_policy("subject-1", "contains_minor"))
    assert result["applicable_jurisdictions"] == ["JURISDICTION_A", "JURISDICTION_B"]
    assert result["guardian_consent_required"] is True
    body = fake.calls[0][1]["json"]
    assert body["photographed_people_status"] == "contains_minor"
    assert body["requested_retention_seconds"] == 0
    assert body["jurisdiction_resolution"]["do_not_trust_client_country_claims"] is True
    assert "facial_recognition" in body["prohibited_processing"]
    assert "child_behavioural_profiling" in body["prohibited_processing"]


@pytest.mark.parametrize(
    "changes",
    [
        {"current": False},
        {"jurisdiction_resolution_complete": False},
        {"policy_conflicts_resolved": False},
        {"lawful_basis_authorized": False},
        {"cross_border_transfers_authorized": False},
        {"applicable_jurisdictions": []},
        {"policy_sha256": "not-a-digest"},
        {"facial_recognition_allowed": True},
        {"face_identity_analysis_allowed": True},
        {"child_facial_identity_analysis_allowed": True},
        {"child_behavioural_profiling_allowed": True},
        {"public_unmasked_face_exposure_allowed": True},
        {"image_retention_allowed": True},
        {"public_sharing_allowed": True},
    ],
)
def test_stale_incomplete_or_unsafe_policy_receipt_is_blocked(monkeypatch, changes):
    configure(monkeypatch)
    fake = FakeAsyncClient(FakeResponse(receipt(**changes)))
    monkeypatch.setattr(privacy_policy.httpx, "AsyncClient", lambda **kwargs: fake)
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-1", "adults_only"))
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "PRIVACY_POLICY_BLOCKED"

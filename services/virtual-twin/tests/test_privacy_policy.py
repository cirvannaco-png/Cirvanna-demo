from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app import privacy_policy


class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeClient:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def valid_policy_receipt(subject_id: str = "subject-123") -> dict:
    return {
        "subject_id": subject_id,
        "service": "cirvanna-click-it",
        "purpose": "visual_product_discovery",
        "decision": "PASS",
        "current": True,
        "jurisdiction_resolution_complete": True,
        "policy_conflicts_resolved": True,
        "lawful_basis_authorized": True,
        "cross_border_transfers_authorized": True,
        "policy_version": "KE@v1",
        "policy_sha256": "a" * 64,
        "applicable_jurisdictions": ["KE"],
        "guardian_consent_required": False,
        "retention_seconds": 0,
        "facial_recognition_allowed": False,
        "face_identity_analysis_allowed": False,
        "child_facial_identity_analysis_allowed": False,
        "child_behavioural_profiling_allowed": False,
        "public_unmasked_face_exposure_allowed": False,
        "image_retention_allowed": False,
        "public_sharing_allowed": False,
    }


def configure_policy(monkeypatch, receipt):
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_URL", "https://privacy.example.test")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_API_TOKEN", "p" * 40)
    calls = []
    monkeypatch.setattr(
        privacy_policy.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient(FakeResponse(receipt), calls),
    )
    return calls


def test_click_it_policy_pass_is_bound_to_subject_and_zero_retention(monkeypatch):
    calls = configure_policy(monkeypatch, valid_policy_receipt())
    result = asyncio.run(
        privacy_policy.authorize_click_it_policy("subject-123", "no_people", "user-entered-country")
    )
    assert result["policy_version"] == "KE@v1"
    assert result["applicable_jurisdictions"] == ["KE"]
    assert result["public_sharing_allowed"] is False
    payload = calls[0][1]["json"]
    assert payload["subject_id"] == "subject-123"
    assert payload["capture_jurisdiction_hint_is_unverified"] is True
    assert payload["requested_retention_seconds"] == 0
    assert payload["requested_public_display"] is False
    assert "facial_recognition" in payload["prohibited_processing"]
    assert payload["jurisdiction_resolution"]["do_not_trust_client_country_claims"] is True


def test_click_it_policy_rejects_receipt_for_another_subject(monkeypatch):
    configure_policy(monkeypatch, valid_policy_receipt("different-subject"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-123", "no_people"))
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "PRIVACY_POLICY_BLOCKED"


def test_click_it_policy_rejects_nonzero_retention(monkeypatch):
    receipt = valid_policy_receipt()
    receipt["retention_seconds"] = 3600
    configure_policy(monkeypatch, receipt)
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-123", "no_people"))
    assert error.value.status_code == 403


def test_click_it_policy_fails_closed_when_registry_is_missing(monkeypatch):
    monkeypatch.delenv("PRIVACY_GOVERNANCE_API_URL", raising=False)
    monkeypatch.delenv("PRIVACY_GOVERNANCE_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_policy.authorize_click_it_policy("subject-123", "no_people"))
    assert error.value.status_code == 503

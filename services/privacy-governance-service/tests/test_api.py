from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app import main


INTERNAL = "privacy-governance-internal-test-token-at-least-32-bytes"
PUBLISH = "privacy-policy-publisher-test-token-at-least-32-bytes"
REVIEW = "privacy-rights-review-test-token-at-least-32-bytes"


@pytest.fixture(autouse=True)
def configure_database(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "privacy.db")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_DATABASE_URL", url)
    monkeypatch.setenv("PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("PRIVACY_GOVERNANCE_INTERNAL_TOKEN", INTERNAL)
    monkeypatch.setenv("PRIVACY_POLICY_PUBLISH_TOKEN", PUBLISH)
    monkeypatch.setenv("PRIVACY_RIGHTS_REVIEW_TOKEN", REVIEW)
    main.Base.metadata.create_all(main._engine(url))
    yield
    main.Base.metadata.drop_all(main._engine(url))


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def internal():
    return {"Authorization": "Bearer " + INTERNAL}


def reviewer():
    return {"Authorization": "Bearer " + REVIEW}


def publisher():
    return {"Authorization": "Bearer " + PUBLISH}


def grant_payload(status="adults_only", guardian_reference=None):
    payload = {
        "subject_id": "customer-123",
        "consent_image_processing": True,
        "consent_click_it": True,
        "photographed_people_status": status,
        "photographed_people_consent_confirmed": status != "no_people",
        "consent_version": "click-it-privacy-v1",
    }
    if guardian_reference:
        payload["guardian_verification_reference"] = guardian_reference
    return payload


def policy_bundle(signer, jurisdiction, **overrides):
    now = datetime.now(timezone.utc)
    data = {
        "jurisdiction": jurisdiction,
        "policy_version": "legal-review-v1",
        "effective_at": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
        "guardian_consent_required_for_minor": False,
        "child_product_discovery_allowed": True,
        "lawful_basis_approved": True,
        "cross_border_transfer_allowed": True,
        "rights_response_deadline_hours": 168,
        "approved_by": "privacy-counsel-role",
        "legal_review_reference": "legal-review-ticket-123",
        "facial_recognition_allowed": False,
        "face_identity_analysis_allowed": False,
        "child_facial_identity_analysis_allowed": False,
        "child_behavioural_profiling_allowed": False,
        "public_unmasked_face_exposure_allowed": False,
        "image_retention_allowed": False,
        "public_sharing_allowed": False,
        "signature_base64": base64.b64encode(b"x" * 64).decode(),
    }
    data.update(overrides)
    model = main.PolicyBundleIn.model_validate(data)
    signature = signer.sign(main._canonical_policy_payload(model))
    data["signature_base64"] = base64.b64encode(signature).decode()
    return data


def configure_policy_key(monkeypatch):
    signer = Ed25519PrivateKey.generate()
    public_key = signer.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM", public_key)
    return signer


def test_health_and_readiness_do_not_claim_missing_provider_readiness(client):
    assert client.get("/health").json()["status"] == "alive"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is False
    assert ready.json()["jurisdiction_resolver_configured"] is False
    assert ready.json()["content_lifecycle_configured"] is False
    assert ready.json()["vision_privacy_attestation_configured"] is False


def test_publication_gate_requires_signed_mask_attestation_for_every_public_surface(client, monkeypatch):
    calls = []

    async def verify(name, path, payload):
        calls.append((name, path, payload))
        return {
            "verified": True,
            "active": True,
            "asset_id": "asset-public-001",
            "attestation_id": "mask-attestation-000001",
            "all_detected_faces_masked": True,
            "unmasked_face_count": 0,
            "masking_applied_before_publication": True,
            "face_recognition_performed": False,
            "face_embeddings_created": False,
            "age_estimation_performed": False,
            "all_face_regions_processed": True,
            "masking_model_sha256": "a" * 64,
        }

    monkeypatch.setattr(main, "post_trusted", verify)
    response = client.post(
        "/internal/v1/privacy/assets/publication/evaluate",
        headers=internal(),
        json={
            "asset_id": "asset-public-001",
            "masking_attestation_id": "mask-attestation-000001",
            "target_surface": "community_feed",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "PASS"
    assert body["all_detected_faces_masked"] is True
    assert body["unmasked_face_count"] == 0
    assert body["face_recognition_performed"] is False
    assert body["age_estimation_performed"] is False
    assert calls[0][0] == "VISION_PRIVACY_ATTESTATION"
    assert calls[0][2]["require_all_detected_faces_masked"] is True


def test_publication_gate_blocks_any_unmasked_face_or_identity_or_age_processing(client, monkeypatch):
    async def verify(_name, _path, _payload):
        return {
            "verified": True,
            "active": True,
            "asset_id": "asset-public-002",
            "attestation_id": "mask-attestation-000002",
            "all_detected_faces_masked": False,
            "unmasked_face_count": 1,
            "masking_applied_before_publication": True,
            "face_recognition_performed": False,
            "face_embeddings_created": False,
            "age_estimation_performed": False,
            "all_face_regions_processed": False,
            "masking_model_sha256": "b" * 64,
        }

    monkeypatch.setattr(main, "post_trusted", verify)
    response = client.post(
        "/internal/v1/privacy/assets/publication/evaluate",
        headers=internal(),
        json={
            "asset_id": "asset-public-002",
            "masking_attestation_id": "mask-attestation-000002",
            "target_surface": "shared_link",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PUBLICATION_PRIVACY_ATTESTATION_NOT_VALID"


def test_publication_gate_fails_closed_when_vision_attestation_provider_is_missing(client, monkeypatch):
    monkeypatch.delenv("VISION_PRIVACY_ATTESTATION_API_URL", raising=False)
    monkeypatch.delenv("VISION_PRIVACY_ATTESTATION_API_TOKEN", raising=False)
    response = client.post(
        "/internal/v1/privacy/assets/publication/evaluate",
        headers=internal(),
        json={
            "asset_id": "asset-public-003",
            "masking_attestation_id": "mask-attestation-000003",
            "target_surface": "public_profile",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VISION_PRIVACY_ATTESTATION_PROVIDER_NOT_CONFIGURED"



def test_consent_grant_is_purpose_bound_and_verifiable(client):
    response = client.post("/internal/v1/consents/grant", headers=internal(), json=grant_payload())
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["active"] is True
    assert set(receipt["granted_scopes"]) == {
        "image_processing", "click_it", "photographed_people_adult_attestation"
    }
    verify = client.post(
        "/internal/v1/consents/verify",
        headers=internal(),
        json={
            "subject_id": "customer-123",
            "consent_id": receipt["consent_id"],
            "required_scopes": ["image_processing", "click_it", "photographed_people_adult_attestation"],
        },
    )
    assert verify.status_code == 200
    assert verify.json()["verified"] is True
    assert verify.json()["guardian_authority_verified"] is False




def test_adult_photograph_requires_explicit_permission_attestation(client):
    payload = grant_payload("adults_only")
    payload["photographed_people_consent_confirmed"] = False
    response = client.post("/internal/v1/consents/grant", headers=internal(), json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PHOTOGRAPHED_PEOPLE_CONSENT_REQUIRED"


def test_consent_requires_both_explicit_click_it_acceptances(client):
    payload = grant_payload()
    payload["consent_click_it"] = False
    response = client.post("/internal/v1/consents/grant", headers=internal(), json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"


def test_minor_consent_never_grants_guardian_scope_from_a_checkbox_or_reference_alone(client, monkeypatch):
    async def absent_provider(*_args, **_kwargs):
        raise HTTPException(503, detail={"code": "GUARDIAN_VERIFICATION_PROVIDER_NOT_CONFIGURED"})

    monkeypatch.setattr(main, "post_trusted", absent_provider)
    response = client.post(
        "/internal/v1/consents/grant",
        headers=internal(),
        json=grant_payload("contains_minor", guardian_reference="guardian-case-reference-123"),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GUARDIAN_VERIFICATION_PROVIDER_NOT_CONFIGURED"


def test_minor_consent_adds_guardian_scope_only_after_verified_provider_receipt(client, monkeypatch):
    calls = []

    async def verified_provider(name, path, payload):
        calls.append((name, path, payload))
        return {
            "verified": True,
            "active": True,
            "guardian_authority_verified": True,
            "subject_id": "customer-123",
            "purpose": "cirvanna_click_it_photographed_minor",
        }

    monkeypatch.setattr(main, "post_trusted", verified_provider)
    response = client.post(
        "/internal/v1/consents/grant",
        headers=internal(),
        json=grant_payload("contains_minor", guardian_reference="guardian-case-reference-123"),
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["guardian_authority_verified"] is True
    assert "guardian_authorized" in receipt["granted_scopes"]
    assert "photographed_people_minor_attestation" in receipt["granted_scopes"]
    assert calls[0][0] == "GUARDIAN_VERIFICATION"


def test_consent_revocation_is_immediate_and_irreversible_for_that_receipt(client):
    grant = client.post("/internal/v1/consents/grant", headers=internal(), json=grant_payload()).json()
    revoked = client.post(
        f"/internal/v1/consents/{grant['consent_id']}/revoke",
        headers=internal(),
        json={"subject_id": "customer-123", "reason_code": "user_request"},
    )
    assert revoked.status_code == 200
    verify = client.post(
        "/internal/v1/consents/verify",
        headers=internal(),
        json={
            "subject_id": "customer-123",
            "consent_id": grant["consent_id"],
            "required_scopes": ["image_processing", "click_it"],
        },
    )
    assert verify.status_code == 200
    assert verify.json()["verified"] is False


def test_consent_verification_binds_subject_and_resource(client):
    grant = client.post(
        "/internal/v1/consents/grant",
        headers=internal(),
        json={**grant_payload(), "resource_id": "twin-123"},
    ).json()
    wrong_subject = client.post(
        "/internal/v1/consents/verify",
        headers=internal(),
        json={"subject_id": "another-user", "consent_id": grant["consent_id"], "required_scopes": ["click_it"]},
    )
    wrong_resource = client.post(
        "/internal/v1/consents/verify",
        headers=internal(),
        json={"subject_id": "customer-123", "consent_id": grant["consent_id"], "required_scopes": ["click_it"], "resource_id": "twin-999"},
    )
    assert wrong_subject.json()["verified"] is False
    assert wrong_resource.json()["verified"] is False


def test_policy_publisher_requires_a_valid_ed25519_signature(client, monkeypatch):
    signer = configure_policy_key(monkeypatch)
    payload = policy_bundle(signer, "JUR-A")
    response = client.post("/internal/v1/privacy/policies", headers=publisher(), json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["signature_verified"] is True
    invalid = dict(payload)
    invalid["policy_version"] = "tampered-v2"
    invalid["lawful_basis_approved"] = False
    response = client.post("/internal/v1/privacy/policies", headers=publisher(), json=invalid)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "POLICY_SIGNATURE_INVALID"


def test_unsafe_policy_bundle_cannot_be_published(client, monkeypatch):
    signer = configure_policy_key(monkeypatch)
    payload = policy_bundle(signer, "JUR-A", facial_recognition_allowed=True)
    response = client.post("/internal/v1/privacy/policies", headers=publisher(), json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNSAFE_PRIVACY_POLICY_CANNOT_BE_PUBLISHED"


def test_unknown_or_incomplete_jurisdiction_resolution_blocks_click_it(client, monkeypatch):
    async def incomplete(*_args, **_kwargs):
        return {
            "jurisdiction_resolution_complete": False,
            "applicable_jurisdictions": [],
            "policy_conflicts_resolved": False,
        }

    monkeypatch.setattr(main, "post_trusted", incomplete)
    response = client.post(
        "/internal/v1/privacy/click-it/evaluate",
        headers=internal(),
        json={
            "subject_id": "customer-123",
            "service": "cirvanna-click-it",
            "purpose": "visual_product_discovery",
            "photographed_people_status": "adults_only",
            "requested_retention_seconds": 0,
            "requested_public_display": False,
            "prohibited_processing": [
                "facial_recognition", "face_identity_analysis", "face_embeddings",
                "identity_matching", "sensitive_trait_inference",
                "child_behavioural_profiling", "child_facial_identity_analysis",
            ],
            "jurisdiction_resolution": {"do_not_trust_client_country_claims": True},
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"
    assert response.json()["jurisdiction_resolution_complete"] is False


def test_multi_jurisdiction_uses_stricter_guardian_policy(client, monkeypatch):
    signer = configure_policy_key(monkeypatch)
    for code, guardian in [("JUR-A", False), ("JUR-B", True)]:
        payload = policy_bundle(signer, code, guardian_consent_required_for_minor=guardian)
        response = client.post("/internal/v1/privacy/policies", headers=publisher(), json=payload)
        assert response.status_code == 200, response.text

    async def resolver(*_args, **_kwargs):
        return {
            "jurisdiction_resolution_complete": True,
            "policy_conflicts_resolved": True,
            "applicable_jurisdictions": ["JUR-A", "JUR-B"],
            "controller_establishments": ["controller-A"],
            "processor_establishments": ["processor-A"],
            "processing_locations": ["region-A", "region-B"],
            "storage_locations": ["region-A"],
            "transfer_paths": [{"from": "processor-a", "to": "processor-b", "allowed": True}],
        }

    monkeypatch.setattr(main, "post_trusted", resolver)
    response = client.post(
        "/internal/v1/privacy/click-it/evaluate",
        headers=internal(),
        json={
            "subject_id": "customer-123",
            "service": "cirvanna-click-it",
            "purpose": "visual_product_discovery",
            "photographed_people_status": "contains_minor",
            "capture_jurisdiction_hint": "untrusted user-entered place",
            "capture_jurisdiction_hint_is_unverified": True,
            "requested_retention_seconds": 0,
            "requested_public_display": False,
            "prohibited_processing": [
                "facial_recognition", "face_identity_analysis", "face_embeddings",
                "identity_matching", "sensitive_trait_inference",
                "child_behavioural_profiling", "child_facial_identity_analysis",
            ],
            "jurisdiction_resolution": {"do_not_trust_client_country_claims": True},
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "PASS"
    assert result["applicable_jurisdictions"] == ["JUR-A", "JUR-B"]
    assert result["guardian_consent_required"] is True
    assert result["retention_seconds"] == 0
    assert result["facial_recognition_allowed"] is False
    assert result["public_unmasked_face_exposure_allowed"] is False
    assert result["rights_response_deadline_hours"] == 168


def test_policy_missing_for_one_overlapping_jurisdiction_blocks(client, monkeypatch):
    signer = configure_policy_key(monkeypatch)
    payload = policy_bundle(signer, "JUR-A")
    assert client.post("/internal/v1/privacy/policies", headers=publisher(), json=payload).status_code == 200

    async def resolver(*_args, **_kwargs):
        return {
            "jurisdiction_resolution_complete": True,
            "policy_conflicts_resolved": True,
            "applicable_jurisdictions": ["JUR-A", "JUR-B"],
            "controller_establishments": ["controller-A"],
            "processor_establishments": ["processor-A"],
            "processing_locations": ["region-A"],
            "storage_locations": ["region-A"],
            "transfer_paths": [],
        }

    monkeypatch.setattr(main, "post_trusted", resolver)
    body = {
        "subject_id": "customer-123",
        "service": "cirvanna-click-it",
        "purpose": "visual_product_discovery",
        "photographed_people_status": "adults_only",
        "requested_retention_seconds": 0,
        "requested_public_display": False,
        "prohibited_processing": [
            "facial_recognition", "face_identity_analysis", "face_embeddings",
            "identity_matching", "sensitive_trait_inference",
            "child_behavioural_profiling", "child_facial_identity_analysis",
        ],
        "jurisdiction_resolution": {},
    }
    result = client.post("/internal/v1/privacy/click-it/evaluate", headers=internal(), json=body).json()
    assert result["decision"] == "BLOCK"
    assert "CURRENT_SIGNED_POLICY_MISSING_OR_EXPIRED" in result["block_reasons"]


def test_rights_request_requires_asset_registry_and_urgent_quarantine_ack(client, monkeypatch):
    calls = []

    async def content(name, path, payload):
        calls.append((name, path, payload))
        if path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-opaque-001"}
        if path.endswith("/quarantine"):
            return {"quarantined": True, "unpublished": True}
        raise AssertionError(path)

    monkeypatch.setattr(main, "post_trusted", content)
    response = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-1234",
            "request_type": "report",
            "reason_code": "possible_minor",
            "requester_relationship": "parent_guardian",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "quarantined"
    assert result["quarantined"] is True
    assert len(result["status_token"]) >= 24
    assert len(calls) == 3
    assert calls[0][0] == "CONTENT_LIFECYCLE"
    assert calls[0][1].endswith("/resolve")
    assert calls[1][0] == "JURISDICTION_RESOLVER"
    assert calls[1][1].endswith("/jurisdictions/resolve")
    assert calls[2][0] == "CONTENT_LIFECYCLE"
    assert calls[2][1].endswith("/quarantine")


def test_urgent_rights_report_is_not_acknowledged_without_unpublish_confirmation(client, monkeypatch):
    async def content(_name, path, _payload):
        if path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-opaque-002"}
        return {"quarantined": True, "unpublished": False}

    monkeypatch.setattr(main, "post_trusted", content)
    response = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-5678",
            "request_type": "removal",
            "reason_code": "unmasked_face",
            "requester_relationship": "photographed_person",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "IMAGE_RIGHTS_QUARANTINE_NOT_CONFIRMED"


def test_rights_status_token_is_one_time_and_only_its_hash_is_stored(client, monkeypatch):
    async def content(_name, path, _payload):
        if path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-opaque-003"}
        return {"quarantined": True, "unpublished": True}

    monkeypatch.setattr(main, "post_trusted", content)
    created = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-9012",
            "request_type": "report",
            "reason_code": "possible_minor",
            "requester_relationship": "other",
        },
    ).json()
    status = client.get(
        f"/internal/v1/image-rights/requests/{created['request_id']}",
        headers={**internal(), "X-Requester-Status-Token": created["status_token"]},
    )
    assert status.status_code == 200
    assert status.json()["quarantined"] is True
    assert status.json()["triage_due_at"]
    assert status.json()["legal_response_due_at"] is None
    assert status.json()["deadline_basis"] == "jurisdiction_unresolved_platform_triage"
    wrong = client.get(
        f"/internal/v1/image-rights/requests/{created['request_id']}",
        headers={**internal(), "X-Requester-Status-Token": "wrong-token-value-long-enough-123"},
    )
    assert wrong.status_code == 404


def test_rights_approval_requires_verified_authority_and_full_deletion_propagation(client, monkeypatch):
    authority_confirmed = False
    async def content(name, path, payload):
        if name == "RIGHTS_AUTHORITY_VERIFICATION":
            return {
                "verified": True, "active": True,
                "request_id": payload["request_id"],
                "asset_id": payload["asset_id"],
                "requester_relationship": payload["requester_relationship"],
                "authority_confirmed": authority_confirmed,
            }
        if path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-opaque-004"}
        return {"propagation_complete": True, "deleted_surfaces": sorted(main.REQUIRED_REMOVAL_SURFACES)}

    monkeypatch.setattr(main, "post_trusted", content)
    created = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-3456",
            "request_type": "removal",
            "reason_code": "privacy_concern",
            "requester_relationship": "photographed_person",
        },
    ).json()
    denied = client.post(
        f"/internal/v1/image-rights/requests/{created['request_id']}/review",
        headers=reviewer(),
        json={"decision": "approve", "verification_reference": "verification-ticket-123", "resolution_code": "privacy-approved"},
    )
    assert denied.status_code == 403
    authority_confirmed = True
    approved = client.post(
        f"/internal/v1/image-rights/requests/{created['request_id']}/review",
        headers=reviewer(),
        json={"decision": "approve", "verification_reference": "verification-ticket-123", "resolution_code": "privacy-approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["deletion_propagated"] is True
    assert approved.json()["status"] == "completed"


def test_rights_review_does_not_mark_completed_when_deletion_is_partial(client, monkeypatch):
    async def content(name, path, payload):
        if name == "RIGHTS_AUTHORITY_VERIFICATION":
            return {
                "verified": True, "active": True,
                "request_id": payload["request_id"],
                "asset_id": payload["asset_id"],
                "requester_relationship": payload["requester_relationship"],
                "authority_confirmed": True,
            }
        if path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-opaque-005"}
        return {"propagation_complete": False, "deleted_surfaces": ["source", "cdn"]}

    monkeypatch.setattr(main, "post_trusted", content)
    created = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-7890",
            "request_type": "removal",
            "reason_code": "privacy_concern",
            "requester_relationship": "photographed_person",
        },
    ).json()
    response = client.post(
        f"/internal/v1/image-rights/requests/{created['request_id']}/review",
        headers=reviewer(),
        json={"decision": "approve", "verification_reference": "verification-ticket-456", "resolution_code": "privacy-approved"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "IMAGE_RIGHTS_DELETION_PROPAGATION_INCOMPLETE"


def test_image_rights_rejects_external_urls_and_uploaded_data(client):
    response = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "https://external.example/photo.jpg",
            "request_type": "removal",
            "reason_code": "privacy_concern",
            "requester_relationship": "photographed_person",
            "image_bytes": "not-accepted",
        },
    )
    assert response.status_code == 422


def test_internal_and_reviewer_endpoints_require_separate_tokens(client):
    assert client.post("/internal/v1/consents/verify", json={}).status_code == 401
    assert client.get("/internal/v1/image-rights/queue", headers=internal()).status_code == 401
    assert client.post("/internal/v1/privacy/policies", headers=reviewer(), json={}).status_code == 401


def test_rights_request_uses_strictest_current_signed_jurisdiction_deadline(client, monkeypatch):
    signer = configure_policy_key(monkeypatch)
    for code, deadline in [("JUR-A", 72), ("JUR-B", 12)]:
        policy = policy_bundle(signer, code, rights_response_deadline_hours=deadline)
        published = client.post("/internal/v1/privacy/policies", headers=publisher(), json=policy)
        assert published.status_code == 200, published.text

    async def providers(name, path, payload):
        if name == "CONTENT_LIFECYCLE" and path.endswith("/resolve"):
            return {"found": True, "active": True, "asset_id": "asset-deadline-001"}
        if name == "JURISDICTION_RESOLVER":
            return {
                "jurisdiction_resolution_complete": True,
                "policy_conflicts_resolved": True,
                "applicable_jurisdictions": ["JUR-A", "JUR-B"],
                "controller_establishments": ["controller-A"],
                "processor_establishments": ["processor-A"],
                "processing_locations": ["region-A"],
                "storage_locations": ["region-A"],
                "transfer_paths": [{"from": "region-A", "to": "region-A", "allowed": True}],
            }
        raise AssertionError((name, path))

    monkeypatch.setattr(main, "post_trusted", providers)
    created = client.post(
        "/internal/v1/image-rights/requests",
        headers=internal(),
        json={
            "asset_reference": "cirvanna-share-deadline",
            "request_type": "removal",
            "reason_code": "privacy_concern",
            "requester_relationship": "photographed_person",
        },
    )
    assert created.status_code == 200, created.text
    status = client.get(
        f"/internal/v1/image-rights/requests/{created.json()['request_id']}",
        headers={**internal(), "X-Requester-Status-Token": created.json()["status_token"]},
    )
    assert status.status_code == 200
    result = status.json()
    assert result["deadline_basis"] == "resolved_signed_jurisdiction_policy"
    assert result["applicable_jurisdictions"] == ["JUR-A", "JUR-B"]
    assert result["legal_response_due_at"] is not None
    triage_due = datetime.fromisoformat(result["triage_due_at"])
    legal_due = datetime.fromisoformat(result["legal_response_due_at"])
    assert triage_due < legal_due

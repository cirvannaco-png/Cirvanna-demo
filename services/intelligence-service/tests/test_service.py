from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import Base, Outcome, ProviderTask, SessionLocal, app, engine
from app.provider import ProviderNotConfigured, fetch_licensed_research


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CIL_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "service-test")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "catalog-test")
    monkeypatch.setenv("CIL_CAL_SERVICE_TOKEN", "cal-test")
    monkeypatch.setenv("CIL_RECEIPT_SIGNING_KEY", "test-signing-key-that-is-at-least-32-bytes")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def receipt(payload):
    key = b"test-signing-key-that-is-at-least-32-bytes"
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def register_source(client, source_id="source-licensed", **overrides):
    payload = {
        "source_id": source_id,
        "owner": "Research Publisher",
        "kind": "licensed_research",
        "locator": "https://publisher.example/research/123",
        "rights_status": "licensed",
        "rights_reference": "licence-contract-2026-01",
        "permitted_purposes": ["product_enrichment", "commercial_recommendation"],
        "attribution_required": True,
        "attribution_text": "Research Publisher",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    response = client.post("/sources", json=payload, headers=auth("admin-test"))
    assert response.status_code == 201, response.text
    return payload


def register_evidence(client, source_id="source-licensed", evidence_id="evidence-1", **overrides):
    payload = {
        "evidence_id": evidence_id,
        "source_id": source_id,
        "grade": "E1",
        "scope": "finished_product",
        "locator": "https://publisher.example/research/123#results",
        "limitations": "The result applies only to the evaluated finished formulation and study conditions.",
    }
    payload.update(overrides)
    response = client.post("/evidence", json=payload, headers=auth("admin-test"))
    assert response.status_code == 201, response.text
    return payload


def test_durable_source_and_evidence_registry(client):
    register_source(client)
    register_evidence(client)
    db = SessionLocal()
    try:
        from app.main import Source, Evidence
        assert db.get(Source, "source-licensed") is not None
        assert db.get(Evidence, "evidence-1") is not None
    finally:
        db.close()


def test_serving_assessment_allows_only_registered_licensed_scope(client):
    register_source(client)
    register_evidence(client)
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 3,
        "claims": [{
            "claim_id": "claim-1",
            "claim_type": "finished_product_efficacy",
            "review_status": "approved",
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed", "scope": "finished_product"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["all_eligible"] is True


def test_ingredient_research_cannot_substantiate_finished_product_efficacy(client):
    register_source(client)
    register_evidence(client, scope="ingredient")
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "claim-1",
            "claim_type": "finished_product_efficacy",
            "review_status": "approved",
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["decisions"][0]["eligible"] is False


def test_research_only_source_cannot_be_registered_for_commercial_use(client):
    payload = {
        "source_id": "research-only",
        "owner": "University",
        "kind": "public_research",
        "locator": "https://university.example/paper",
        "rights_status": "research_only",
        "rights_reference": "research-terms",
        "permitted_purposes": ["research", "commercial_recommendation"],
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/sources", json=payload, headers=auth("admin-test"))
    assert response.status_code == 422


def test_expired_licence_fails_closed_at_serving(client):
    register_source(client, expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    register_evidence(client)
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "claim-1",
            "claim_type": "cosmetic_intent",
            "evidence": {"evidence_id": "evidence-1"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["decisions"][0]["eligible"] is False
    assert result.json()["decisions"][0]["reason"] == "SOURCE_RIGHTS_EXPIRED"


def test_outcome_requires_signed_consent_and_cal_show_receipts(client):
    token = "hmac-sha256:" + "a" * 64
    common = {"product_id": "product-1", "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
    consent = receipt({**common, "type": "consent", "purpose": "recommendation_outcome_learning", "subject_token": token})
    cal = receipt({**common, "type": "cal", "verdict": "SHOW", "candidate_id": "candidate-1", "decision_id": "decision-1"})
    payload = {
        "event_id": "event-1", "product_id": "product-1", "context_key": "humid-daily",
        "contributor_token": token, "action": "saved", "suitability": "suitable",
        "reason_codes": [], "candidate_id": "candidate-1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "consent_receipt": consent, "cal_decision_receipt": cal,
    }
    result = client.post("/outcomes", json=payload, headers=auth("service-test"))
    assert result.status_code == 201, result.text
    assert result.json()["stored"] is True


def test_outcome_rejects_mismatched_consent_subject(client):
    token = "hmac-sha256:" + "a" * 64
    common = {"product_id": "product-1", "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
    consent = receipt({**common, "type": "consent", "purpose": "recommendation_outcome_learning", "subject_token": "hmac-sha256:" + "b" * 64})
    cal = receipt({**common, "type": "cal", "verdict": "SHOW", "candidate_id": "candidate-1"})
    payload = {
        "event_id": "event-1", "product_id": "product-1", "context_key": "humid-daily",
        "contributor_token": token, "action": "opened", "suitability": "not_reported",
        "candidate_id": "candidate-1", "observed_at": datetime.now(timezone.utc).isoformat(),
        "consent_receipt": consent, "cal_decision_receipt": cal,
    }
    result = client.post("/outcomes", json=payload, headers=auth("service-test"))
    assert result.status_code == 403


def test_provider_adapter_requires_explicit_licence_configuration(monkeypatch):
    for key in ("CIL_PROVIDER_BASE_URL", "CIL_PROVIDER_API_TOKEN", "CIL_PROVIDER_LICENCE_ID", "CIL_PROVIDER_TERMS_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ProviderNotConfigured):
        fetch_licensed_research(path="v1/research")


def test_provider_adapter_rejects_path_traversal(monkeypatch):
    monkeypatch.setenv("CIL_PROVIDER_BASE_URL", "https://licensed.example")
    monkeypatch.setenv("CIL_PROVIDER_API_TOKEN", "test-token")
    monkeypatch.setenv("CIL_PROVIDER_LICENCE_ID", "licence-1")
    monkeypatch.setenv("CIL_PROVIDER_TERMS_URL", "https://licensed.example/terms")
    with pytest.raises(ValueError):
        fetch_licensed_research(path="../private")


def test_feedback_aggregate_opens_cal_review_and_records_final_cal_decision(client):
    for index in range(30):
        contributor = "hmac-sha256:" + f"{index:064x}"
        common = {
            "product_id": "product-review",
            "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        consent = receipt({
            **common, "type": "consent", "purpose": "recommendation_outcome_learning",
            "subject_token": contributor,
        })
        cal = receipt({
            **common, "type": "cal", "verdict": "SHOW",
            "candidate_id": "candidate-review", "decision_id": f"decision-{index}",
        })
        payload = {
            "event_id": f"review-event-{index}", "product_id": "product-review",
            "context_key": "humid-daily", "contributor_token": contributor,
            "action": "saved", "suitability": "unsuitable", "reason_codes": ["poor_match"],
            "candidate_id": "candidate-review", "observed_at": datetime.now(timezone.utc).isoformat(),
            "consent_receipt": consent, "cal_decision_receipt": cal,
        }
        result = client.post("/outcomes", json=payload, headers=auth("service-test"))
        assert result.status_code == 201, result.text

    aggregate = client.get(
        "/outcomes/aggregate",
        params={"product_id": "product-review", "context_key": "humid-daily"},
        headers=auth("service-test"),
    )
    assert aggregate.status_code == 200
    result = aggregate.json()
    assert result["status"] == "review_required"
    assert result["cal_action"] == "REVIEW_REQUESTED"
    assert result["automatic_suppression"] is False
    review_id = result["cal_review_id"]

    learning = client.post(
        "/learning/signals", headers=auth("service-test"),
        json={"product_ids": ["product-review"], "context_key": "humid-daily"},
    )
    assert learning.status_code == 200
    feedback_signal = learning.json()["signals"][0]
    assert feedback_signal["status"] == "available"
    assert feedback_signal["contributor_count"] == 30
    assert feedback_signal["unsuitable_share"] == 1.0

    queue = client.get("/cal/review-queue", headers=auth("service-test"))
    assert queue.status_code == 200
    assert any(item["review_id"] == review_id for item in queue.json()["items"])

    decision = client.post(
        f"/cal/review-queue/{review_id}/decision",
        headers=auth("cal-test"),
        json={"verdict": "BLOCK", "decision_reference": "CAL-REVIEW-0001",
              "rationale": "Independent review found a substantiated suitability concern."},
    )
    assert decision.status_code == 200
    assert decision.json()["verdict"] == "BLOCK"
    assert decision.json()["status"] == "decided"


def test_provider_research_ingestion_requires_licence_and_persists_provenance(client, monkeypatch):
    from app import main as cil_main

    monkeypatch.setenv("CIL_PROVIDER_BASE_URL", "https://licensed.example/api")
    monkeypatch.setattr(cil_main, "fetch_licensed_research", lambda **kwargs: {
        "licence_id": "licence-123",
        "terms_url": "https://licensed.example/terms",
        "payload": {"study_id": "study-123", "summary": "A licensed research record."},
    })
    payload = {
        "source_id": "provider-source-1",
        "evidence_id": "provider-evidence-1",
        "owner": "Licensed Research Provider",
        "path": "v1/studies/123",
        "params": {"locale": "en"},
        "rights_status": "licensed",
        "rights_reference": "signed-contract-123",
        "permitted_purposes": ["research", "commercial_recommendation"],
        "grade": "E2",
        "scope": "ingredient",
        "limitations": "Study scope is limited to the evaluated ingredient and conditions.",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/providers/research", json=payload, headers=auth("admin-test"))
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["evidence_id"] == "provider-evidence-1"
    assert result["provider_payload"]["study_id"] == "study-123"
    assert "licence-123" in result["rights_status"] or result["rights_status"] == "licensed"


def test_provider_research_rejects_research_only_commercial_scope_before_fetch(client, monkeypatch):
    from app import main as cil_main

    def should_not_call(**kwargs):
        raise AssertionError("provider must not be called for incompatible rights")
    monkeypatch.setattr(cil_main, "fetch_licensed_research", should_not_call)
    payload = {
        "source_id": "provider-source-research-only",
        "evidence_id": "provider-evidence-research-only",
        "owner": "University",
        "path": "v1/studies/123",
        "rights_status": "research_only",
        "rights_reference": "research-terms",
        "permitted_purposes": ["research", "commercial_recommendation"],
        "grade": "E2",
        "scope": "ingredient",
        "limitations": "This evidence is restricted to non-commercial research use.",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/providers/research", json=payload, headers=auth("admin-test"))
    assert response.status_code == 422


def test_manufacturer_declaration_cannot_substantiate_finished_product_efficacy(client):
    register_source(client, source_id="manufacturer-source", kind="manufacturer")
    register_evidence(client, source_id="manufacturer-source", grade="E4", scope="finished_product")
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "efficacy-claim",
            "claim_type": "finished_product_efficacy",
            "review_status": "approved",
            "evidence": {"evidence_id": "evidence-1", "source_id": "manufacturer-source"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["decisions"][0]["eligible"] is False


def test_missing_required_attribution_fails_closed(client):
    register_source(
        client, source_id="no-attribution",
        attribution_required=True, attribution_text=None,
    )
    register_evidence(client, source_id="no-attribution", evidence_id="evidence-no-attribution")
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "cosmetic-claim",
            "claim_type": "cosmetic_intent",
            "review_status": "approved",
            "evidence": {"evidence_id": "evidence-no-attribution", "source_id": "no-attribution"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["decisions"][0]["eligible"] is False
    assert result.json()["decisions"][0]["reason"] == "ATTRIBUTION_REQUIRED"


def test_pending_claim_is_never_eligible_for_customer_serving(client):
    register_source(client)
    register_evidence(client)
    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "pending-claim",
            "claim_type": "cosmetic_intent",
            "review_status": "pending_review",
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert result.status_code == 200
    assert result.json()["decisions"][0]["eligible"] is False
    assert result.json()["decisions"][0]["reason"] == "CLAIM_NOT_APPROVED"


def test_source_rights_revocation_is_audited_and_immediately_blocks_serving(client):
    register_source(client)
    register_evidence(client)
    revoked = client.post(
        "/sources/source-licensed/revoke",
        headers=auth("admin-test"),
        json={
            "rights_reference": "publisher-termination-notice-2026-11",
            "reason": "The licensed research agreement was terminated by the publisher.",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    payload = {
        "purpose": "commercial_recommendation",
        "product_id": "product-1",
        "catalog_version": 1,
        "claims": [{
            "claim_id": "claim-1",
            "claim_type": "cosmetic_intent",
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed"},
        }],
        "ingredient_declarations": [],
    }
    assessment = client.post("/serving/assessment", json=payload, headers=auth("catalog-test"))
    assert assessment.status_code == 200
    assert assessment.json()["decisions"][0]["eligible"] is False
    assert assessment.json()["decisions"][0]["reason"] == "SOURCE_RIGHTS_REVOKED"


def test_learning_signals_suppress_small_cohorts(client):
    response = client.post(
        "/learning/signals",
        headers=auth("service-test"),
        json={"product_ids": ["product-small-cohort"], "context_key": "humid-daily"},
    )
    assert response.status_code == 200
    signal = response.json()["signals"][0]
    assert signal["status"] == "suppressed"
    assert signal["contributor_count"] == 0
    assert signal["unsuitable_share"] is None


def make_skin_image() -> bytes:
    from io import BytesIO
    from PIL import Image
    image = Image.new("RGB", (512, 512), (220, 160, 130))
    image.getexif()[270] = "private-exif-metadata"
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def sign_skin_consent(*, contributor_token: str, image_bytes: bytes, age: int = 25):
    payload = {
        "type": "consent",
        "purpose": "perfectcorp_skin_analysis",
        "provider": "perfectcorp",
        "subject_token": contributor_token,
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "single_subject": True,
        "subject_age_years": age,
        "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    return receipt(payload)


def test_perfectcorp_skin_analysis_requires_signed_adult_image_consent(client, monkeypatch):
    import base64
    from app import main as cil_main

    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    monkeypatch.setenv("CIL_PERFECTCORP_DPA_APPROVED", "true")
    monkeypatch.setattr(cil_main, "perfectcorp_start_skin_analysis", lambda **kwargs: {
        "task_id": "perfectcorp-vendor-task-001", "status": "running", "provider": "perfectcorp_youcam_skin_analysis_v2_1"
    })
    image_bytes = make_skin_image()
    contributor = "hmac-sha256:" + "c" * 64
    payload = {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "content_type": "image/png",
        "file_name": "my-photo.png",
        "mode": "sd",
        "actions": ["pore", "texture"],
        "contributor_token": contributor,
        "consent_receipt": sign_skin_consent(contributor_token=contributor, image_bytes=image_bytes),
    }
    response = client.post("/providers/perfectcorp/skin-analysis", json=payload, headers=auth("service-test"))
    assert response.status_code == 202, response.text
    import uuid
    uuid.UUID(response.json()["task_id"])
    assert response.json()["provider_task_id"] == "perfectcorp-vendor-task-001"


def test_perfectcorp_skin_analysis_rejects_child_consent(client, monkeypatch):
    import base64
    from app import main as cil_main

    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    def should_not_start(**kwargs):
        raise AssertionError("provider must not receive child image")
    monkeypatch.setattr(cil_main, "perfectcorp_start_skin_analysis", should_not_start)
    image_bytes = make_skin_image()
    contributor = "hmac-sha256:" + "d" * 64
    payload = {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "content_type": "image/png", "mode": "sd", "actions": ["pore"],
        "contributor_token": contributor,
        "consent_receipt": sign_skin_consent(contributor_token=contributor, image_bytes=image_bytes, age=16),
    }
    response = client.post("/providers/perfectcorp/skin-analysis", json=payload, headers=auth("service-test"))
    assert response.status_code == 403


def test_perfectcorp_skin_analysis_rejects_receipt_for_different_image(client, monkeypatch):
    import base64
    from app import main as cil_main

    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    monkeypatch.setattr(cil_main, "perfectcorp_start_skin_analysis", lambda **kwargs: pytest.fail("provider called"))
    image_bytes = make_skin_image()
    other_image = make_skin_image() + b"different"
    contributor = "hmac-sha256:" + "e" * 64
    payload = {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "content_type": "image/png", "mode": "sd", "actions": ["pore"],
        "contributor_token": contributor,
        "consent_receipt": sign_skin_consent(contributor_token=contributor, image_bytes=other_image),
    }
    response = client.post("/providers/perfectcorp/skin-analysis", json=payload, headers=auth("service-test"))
    assert response.status_code == 403


def test_perfectcorp_terminal_result_is_deleted_before_result_is_released(client, monkeypatch):
    from app import main as cil_main

    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    monkeypatch.setenv("CIL_PERFECTCORP_DPA_APPROVED", "true")
    calls = []
    monkeypatch.setattr(cil_main, "perfectcorp_get_skin_analysis_status", lambda **kwargs: {
        "task_id": "task-2", "status": "success", "metrics": [{"type": "pore", "ui_score": 62}],
    })
    monkeypatch.setattr(cil_main, "perfectcorp_delete_task", lambda **kwargs: calls.append(kwargs["task_id"]) or True)
    contributor = "hmac-sha256:" + "f" * 64
    db = SessionLocal()
    try:
        db.add(ProviderTask(
            task_id="task-2", provider_task_id="vendor-task-2", provider="perfectcorp", contributor_token=contributor,
            image_digest="a" * 64,
            consent_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="running",
        ))
        db.commit()
    finally:
        db.close()
    response = client.get(
        "/providers/perfectcorp/skin-analysis/task-2",
        headers={**auth("service-test"), "X-CIL-Contributor-Token": contributor},
    )
    assert response.status_code == 200
    assert response.json()["provider_task_deleted"] is True
    assert calls == ["vendor-task-2"]


def test_perfectcorp_terminal_result_is_not_released_when_deletion_fails(client, monkeypatch):
    from app import main as cil_main

    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    monkeypatch.setenv("CIL_PERFECTCORP_DPA_APPROVED", "true")
    monkeypatch.setattr(cil_main, "perfectcorp_get_skin_analysis_status", lambda **kwargs: {
        "task_id": "task-3", "status": "success", "metrics": [{"type": "pore", "ui_score": 62}],
    })
    monkeypatch.setattr(cil_main, "perfectcorp_delete_task", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("delete failed")))
    contributor = "hmac-sha256:" + "1" * 64
    db = SessionLocal()
    try:
        db.add(ProviderTask(
            task_id="task-3", provider_task_id="vendor-task-3", provider="perfectcorp", contributor_token=contributor,
            image_digest="b" * 64,
            consent_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="running",
        ))
        db.commit()
    finally:
        db.close()
    response = client.get(
        "/providers/perfectcorp/skin-analysis/task-3",
        headers={**auth("service-test"), "X-CIL-Contributor-Token": contributor},
    )
    assert response.status_code == 502


def test_perfectcorp_polling_is_bound_to_the_same_pseudonymous_contributor(client, monkeypatch):
    from app import main as cil_main
    contributor = "hmac-sha256:" + "2" * 64
    db = SessionLocal()
    try:
        db.add(ProviderTask(
            task_id="task-owned", provider_task_id="vendor-owned", provider="perfectcorp",
            contributor_token=contributor, image_digest="c" * 64,
            consent_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), status="running",
        ))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(cil_main, "perfectcorp_get_skin_analysis_status", lambda **kwargs: pytest.fail("foreign subject must not poll"))
    response = client.get(
        "/providers/perfectcorp/skin-analysis/task-owned",
        headers={**auth("service-test"), "X-CIL-Contributor-Token": "hmac-sha256:" + "3" * 64},
    )
    assert response.status_code == 403


def test_perfectcorp_reaper_deletes_abandoned_provider_tasks(client, monkeypatch):
    from app import main as cil_main
    monkeypatch.setenv("CIL_PERFECTCORP_TASK_TTL_MINUTES", "30")
    calls = []
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    db = SessionLocal()
    try:
        db.add(ProviderTask(
            task_id="task-abandoned", provider_task_id="vendor-abandoned", provider="perfectcorp",
            contributor_token="hmac-sha256:" + "4" * 64, image_digest="d" * 64,
            consent_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="running", created_at=old,
        ))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(cil_main, "perfectcorp_delete_task", lambda **kwargs: calls.append(kwargs["task_id"]) or True)
    response = client.post("/providers/perfectcorp/reap-tasks", headers=auth("admin-test"))
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert calls == ["vendor-abandoned"]

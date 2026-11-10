from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import Base, Outcome, SessionLocal, app, engine
from app.provider import ProviderNotConfigured, fetch_licensed_research


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CIL_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "service-test")
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
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed", "scope": "finished_product"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("service-test"))
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
            "evidence": {"evidence_id": "evidence-1", "source_id": "source-licensed"},
        }],
        "ingredient_declarations": [],
    }
    result = client.post("/serving/assessment", json=payload, headers=auth("service-test"))
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
    result = client.post("/serving/assessment", json=payload, headers=auth("service-test"))
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

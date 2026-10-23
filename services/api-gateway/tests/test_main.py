from __future__ import annotations

import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main


PRODUCT_ID = "2e4c0b5a-d9b4-4b96-87f0-5c92f120d14f"
TOKEN = "unit-test-gateway-token"


def product(**overrides):
    value = {
        "product_id": PRODUCT_ID,
        "sku": "CIRVANNA-TEST-1",
        "name": "Test garment",
        "description": "Fixture only",
        "category": "shirt",
        "brand": "Test brand",
        "price_minor": 150000,
        "currency": "KES",
        "attributes": {"style": "minimal", "material": "cotton", "color": "blue"},
        "image_urls": [],
        "status": "active",
        "catalog_version": 3,
    }
    value.update(overrides)
    return value


def request_body(**overrides):
    value = {
        "user_id": "user-test-1",
        "product_ids": [PRODUCT_ID],
        "context": {"age_years": 25, "location": "Nairobi", "occasion": "everyday", "climate": "warm"},
        "style_preferences": [{"attribute": "minimal", "weight": 1.0}, {"attribute": "cotton", "weight": 0.5}],
        "negative_preferences": [],
        "cultural_requirements": [],
        "hard_constraints": [],
    }
    value.update(overrides)
    return value


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setenv("CIRVANNA_AUDIT_DB", str(tmp_path / "audit.sqlite3"))
    monkeypatch.delenv("CATALOG_SERVICE_URL", raising=False)
    monkeypatch.delenv("CATALOG_API_TOKEN", raising=False)
    return TestClient(main.app)


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def calibrated_fit(user_id: str, product_id: str) -> main.FitConfidenceEstimate:
    return main.FitConfidenceEstimate(
        estimate_id=f"fit-test-{uuid.uuid4()}",
        user_id=user_id,
        candidate_id=product_id,
        model_version="test-fixture-only",
        calibrated=True,
        confidence=0.91,
        lower_bound=0.86,
        upper_bound=0.95,
        calibration_version="test-fixture-calibration",
        evidence_ids=("fixture-size-chart", "fixture-measurement"),
    )


def pass_safety(product_payload):
    return main.DecisionSignal(
        signal_id=f"test-safety:{product_payload['product_id']}",
        kind=main.SignalKind.SAFETY,
        state=main.SignalState.PASS,
        reason_code="TEST_SAFETY_GATE_PASSED",
        explanation="A test-only independent safety result was injected.",
        source_version="test-fixture-only",
    )


def test_decision_endpoint_requires_bearer_authentication(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    response = client.post("/v1/decisions", json=request_body())
    assert response.status_code == 401


def test_catalog_is_not_replaced_with_mock_data_when_unconfigured(client):
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CATALOG_NOT_CONFIGURED"


def test_missing_safety_and_fit_providers_fail_closed_to_review(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "review"
    assert decision["may_display"] is False
    assert any(reason["code"] == "REQUIRED_SIGNAL_UNKNOWN" for reason in decision["reasons"])
    assert "safety" in " ".join(reason["explanation"] for reason in decision["reasons"])
    assert "fit_confidence" in " ".join(reason["explanation"] for reason in decision["reasons"])


def test_explicit_negative_preference_blocks_candidate(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    body = request_body(negative_preferences=[{
        "preference_id": "avoid-blue",
        "target_type": "attribute",
        "target_value": "blue",
    }])
    response = client.post("/v1/decisions", json=body, headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "block"
    assert decision["may_display"] is False
    assert any(reason["code"] == "NPL_HARD_NEGATIVE" for reason in decision["reasons"])


def test_explicit_hard_cultural_requirement_blocks_without_inference(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    body = request_body(cultural_requirements=[{
        "requirement_id": "declared-covering",
        "declaration_id": "user-declaration-2026-01",
        "attribute": "full-coverage",
        "kind": "required_attribute",
        "hard": True,
    }])
    response = client.post("/v1/decisions", json=body, headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "block"
    assert decision["may_display"] is False
    assert any(reason["code"] == "CULTURAL_REQUIRED_ATTRIBUTE_MISSING" for reason in decision["reasons"])


def test_show_requires_all_required_gates_and_a_calibrated_fit_result(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    monkeypatch.setattr(main, "_safety_signal", pass_safety)
    monkeypatch.setattr(main, "_fit_estimate", calibrated_fit)
    monkeypatch.setattr(
        main, "_fit_evidence_fields",
        lambda _estimate: (
            ("body_measurements", "garment_size_chart", "garment_geometry"),
            ("body_measurements", "garment_size_chart", "garment_geometry"),
        ),
    )
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "show"
    assert decision["may_display"] is True
    assert any(reason["code"] == "ALL_REQUIRED_GATES_PASSED" for reason in decision["reasons"])
    assert decision["catalog_version"] == 3


def test_incomplete_catalog_metadata_cannot_confirm_user_hard_constraint(client, monkeypatch):
    incomplete = product(attributes={"style": "minimal"})
    monkeypatch.setattr(main, "fetch_product", lambda _: incomplete)
    body = request_body(hard_constraints=[{
        "constraint_id": "no-synthetic-fiber",
        "attribute": "synthetic",
        "kind": "forbidden_attribute",
    }])
    response = client.post("/v1/decisions", json=body, headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "review"
    assert decision["may_display"] is False


def test_audit_event_is_persisted_without_user_identity(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())
    assert response.status_code == 200

    audit_path = main._audit_path()
    with sqlite3.connect(str(audit_path)) as connection:
        row = connection.execute(
            "SELECT request_id, product_id, verdict, reason_codes_json FROM decision_audit"
        ).fetchone()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(decision_audit)")}
    assert row is not None
    assert row[1] == PRODUCT_ID
    assert row[2] == "review"
    assert "user_id" not in columns


def test_audit_failure_suppresses_decision_response(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())

    def fail_audit(**_kwargs):
        raise RuntimeError("simulated audit outage")

    monkeypatch.setattr(main, "_record_audit", fail_audit)
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DECISION_AUDIT_UNAVAILABLE"


def test_duplicate_product_ids_are_rejected_by_schema(client):
    body = request_body(product_ids=[PRODUCT_ID, PRODUCT_ID])
    response = client.post("/v1/decisions", json=body, headers=auth_headers())
    assert response.status_code == 422

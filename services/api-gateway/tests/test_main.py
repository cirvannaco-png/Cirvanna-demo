from __future__ import annotations

import hashlib
import hmac

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
        "image_urls": ["https://cdn.example.test/unverified-person-photo.jpg"],
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
    # Legacy request-scoped profile tests explicitly opt into local/demo mode.
    monkeypatch.setenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "false")
    monkeypatch.setattr(main, "_assess_cil_product_serving", lambda _product, purpose="commercial_recommendation": {"product_id": PRODUCT_ID, "catalog_version": 3, "purpose": purpose, "decisions": [], "all_eligible": True})
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


def test_purchase_authorization_returns_signed_offer_and_action_bound_receipt(client, monkeypatch):
    signing_key = "gateway-cal-receipt-test-key-more-than-thirty-two-bytes"
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", signing_key)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda token: "buyer-cal-1")
    monkeypatch.setattr(
        main,
        "evaluate_decisions",
        lambda payload, end_user_authorization=None: main.DecisionResponse(
            schema_version="1.0",
            request_id="decision-request-cal-1",
            created_at="2026-11-10T00:00:00+00:00",
            candidates=[
                main.CandidateDecisionOutput(
                    product_id=payload.product_ids[0],
                    catalog_version=7,
                    verdict="show",
                    may_display=True,
                    reasons=[main.ReasonOutput(code="CAL_SHOW", explanation="The candidate passed the test decision pipeline.")],
                    policy_version="cal-policy-test-v3",
                    arbitration_contract_version="arbitration-v1",
                    decision_pipeline_contract_version="pipeline-v1",
                )
            ],
        ),
    )
    product_id = str(uuid.uuid4())
    variant_id = str(uuid.uuid4())
    listing_id = str(uuid.uuid4())
    merchant_id = str(uuid.uuid4())
    payload = {
        "user_id": "buyer-cal-1",
        "authorizations": [{
            "catalog_product_id": product_id,
            "variant_id": variant_id,
            "listing_id": listing_id,
            "merchant_id": merchant_id,
            "action": "checkout",
            "offer_snapshot_sha256": "a" * 64,
            "market_country_code": "KE",
            "destination_key_sha256": "b" * 64,
            "fulfillment_mode": "courier_delivery",
            "display_currency": "KES",
            "quantity": 2,
            "unit_price_minor": 4500,
            "currency": "KES",
        }],
    }
    response = client.post(
        "/v1/purchase-authorizations",
        json=payload,
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer trusted-user-session"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    receipt = result["receipts"][0]
    assert receipt["subject_id"] == "buyer-cal-1"
    assert receipt["candidate_id"] == variant_id
    assert receipt["catalog_product_id"] == product_id
    assert receipt["listing_id"] == listing_id
    assert receipt["merchant_id"] == merchant_id
    assert receipt["action"] == "checkout"
    assert receipt["offer_snapshot_sha256"] == "a" * 64
    assert receipt["quantity"] == 2 and receipt["unit_price_minor"] == 4500
    assert receipt["decision"] == "SHOW" and receipt["may_display"] is True
    unsigned = {key: value for key, value in receipt.items() if key != "signature"}
    canonical = __import__("json").dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    expected = hmac.new(signing_key.encode(), canonical, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(receipt["signature"], expected)


def test_purchase_authorization_rejects_identity_mismatch_and_missing_signer(client, monkeypatch):
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", "gateway-cal-receipt-test-key-more-than-thirty-two-bytes")
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda token: "different-buyer")
    payload = {
        "user_id": "buyer-cal-1",
        "authorizations": [{
            "catalog_product_id": str(uuid.uuid4()),
            "variant_id": str(uuid.uuid4()),
            "listing_id": str(uuid.uuid4()),
            "merchant_id": str(uuid.uuid4()),
            "action": "cart_add",
            "offer_snapshot_sha256": "c" * 64,
            "quantity": 1,
            "unit_price_minor": 500,
            "currency": "KES",
        }],
    }
    mismatch = client.post(
        "/v1/purchase-authorizations",
        json=payload,
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer other-session"},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"]["code"] == "REQUEST_SUBJECT_MISMATCH"

    monkeypatch.setattr(main, "_resolve_verified_subject", lambda token: "buyer-cal-1")
    monkeypatch.delenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", raising=False)
    missing_key = client.post(
        "/v1/purchase-authorizations",
        json=payload,
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer trusted-user-session"},
    )
    assert missing_key.status_code == 503
    assert missing_key.json()["detail"]["code"] == "CAL_PURCHASE_RECEIPT_SIGNER_NOT_CONFIGURED"



def test_decision_requires_verified_identity_when_setting_is_absent(client, monkeypatch):
    monkeypatch.delenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", raising=False)
    monkeypatch.setattr(main, "fetch_product", lambda _: pytest.fail("must reject before Catalog access"))
    response = client.post(
        "/v1/decisions",
        json=request_body(),
        headers=auth_headers(),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "END_USER_BEARER_REQUIRED"


def test_decision_endpoint_requires_bearer_authentication(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    response = client.post("/v1/decisions", json=request_body())
    assert response.status_code == 401


def test_catalog_is_not_replaced_with_mock_data_when_unconfigured(client):
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CATALOG_NOT_CONFIGURED"



def test_npl_provider_snapshot_is_verified_and_bound_to_candidate(monkeypatch):
    from npl import NegativePreference, PreferenceSource, TargetType, canonical_npl_evidence_payload, preference_payload
    secret = "npl-provider-test-signing-secret-over-32-bytes"
    token = "npl-provider-test-service-token-over-32-bytes"
    monkeypatch.setenv("NPL_SERVICE_URL", "https://npl.internal")
    monkeypatch.setenv("NPL_SERVICE_TOKEN", token)
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", secret)
    preferences = [NegativePreference(
        preference_id="persisted-no-blue", user_id="user-001",
        target_type=TargetType.ATTRIBUTE, target_value="blue",
        source=PreferenceSource.USER_DECLARED,
    )]
    def response_for(url, headers, json):
        assert url == "https://npl.internal/v1/evaluate"
        assert headers["Authorization"] == f"Bearer {token}"
        canonical = canonical_npl_evidence_payload(
            json["request_id"], json["user_id"], json["candidate_id"],
            json["candidate_attributes"], preferences,
        )
        signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
        return FakeResponse({
            "request_id": json["request_id"], "user_id": json["user_id"],
            "candidate_id": json["candidate_id"], "blocked": True,
            "negative_preferences": [preference_payload(p) for p in preferences],
            "npl_evidence_signature": signature,
        })
    class FakeResponse:
        status_code = 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, headers, json): return response_for(url, headers, json)
    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    loaded = main._load_persisted_npl_preferences(
        request_id="request-1", user_id="user-001", product_id="product-1",
        attributes=("blue", "cotton"),
    )
    assert len(loaded) == 1
    assert loaded[0].preference_id == "persisted-no-blue"

def test_untrusted_npl_provider_signature_fails_closed(monkeypatch):
    token = "npl-provider-test-service-token-over-32-bytes"
    monkeypatch.setenv("NPL_SERVICE_URL", "https://npl.internal")
    monkeypatch.setenv("NPL_SERVICE_TOKEN", token)
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", "npl-provider-test-signing-secret-over-32-bytes")
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"request_id":"request-1","user_id":"user-001","candidate_id":"product-1",
                "negative_preferences":[],"npl_evidence_signature":"0"*64}
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def post(self,*args,**kwargs): return FakeResponse()
    monkeypatch.setattr(main.httpx,"Client",FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_persisted_npl_preferences(
            request_id="request-1",user_id="user-001",product_id="product-1",attributes=("blue",)
        )
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "NPL_PROVIDER_EVIDENCE_UNTRUSTED"


def test_cultural_provider_snapshot_is_verified_and_candidate_bound(monkeypatch):
    from cultural_identity import CulturalRequirement, RequirementKind, canonical_cultural_evidence_payload, requirement_payload
    secret = "culture-provider-signing-secret-longer-than-32"
    token = "culture-provider-service-token-longer-than-32"
    monkeypatch.setenv("CULTURAL_IDENTITY_SERVICE_URL", "https://culture.internal")
    monkeypatch.setenv("CULTURAL_IDENTITY_SERVICE_TOKEN", token)
    monkeypatch.setenv("CULTURAL_IDENTITY_HMAC_SECRET", secret)
    reqs = (CulturalRequirement(
        requirement_id="declared-sleeves", declaration_id="decl-1",
        user_id="user-001", attribute="long-sleeve",
        kind=RequirementKind.REQUIRED_ATTRIBUTE, hard=True, active=True,
    ),)
    class FakeResponse:
        status_code=200
        def __init__(self,data): self.data=data
        def json(self): return self.data
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def post(self,url,headers,json):
            assert url=="https://culture.internal/v1/evaluate"
            assert headers["Authorization"]==f"Bearer {token}"
            canonical=canonical_cultural_evidence_payload(
                json["request_id"],json["user_id"],json["candidate_id"],
                json["candidate_attributes"],json["candidate_attributes_complete"],reqs,
            )
            signature=hmac.new(secret.encode(),canonical,hashlib.sha256).hexdigest()
            return FakeResponse({"request_id":json["request_id"],"user_id":json["user_id"],
                "candidate_id":json["candidate_id"],"cultural_requirements":[requirement_payload(reqs[0])],
                "cultural_evidence_signature":signature})
    monkeypatch.setattr(main.httpx,"Client",FakeClient)
    values=main._load_persisted_cultural_requirements(
        request_id="req-1",user_id="user-001",product_id="product-1",
        attributes=("cotton",),attributes_complete=True,
    )
    assert len(values)==1 and values[0].requirement_id=="declared-sleeves"

def test_untrusted_cultural_provider_signature_fails_closed(monkeypatch):
    monkeypatch.setenv("CULTURAL_IDENTITY_SERVICE_URL","https://culture.internal")
    monkeypatch.setenv("CULTURAL_IDENTITY_SERVICE_TOKEN","culture-provider-service-token-longer-than-32")
    monkeypatch.setenv("CULTURAL_IDENTITY_HMAC_SECRET","culture-provider-signing-secret-longer-than-32")
    class FakeResponse:
        status_code=200
        def json(self):
            return {"request_id":"req-1","user_id":"user-001","candidate_id":"product-1",
                "cultural_requirements":[],"cultural_evidence_signature":"0"*64}
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def post(self,*args,**kwargs): return FakeResponse()
    monkeypatch.setattr(main.httpx,"Client",FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_persisted_cultural_requirements(
            request_id="req-1",user_id="user-001",product_id="product-1",
            attributes=("cotton",),attributes_complete=True,
        )
    assert error.value.status_code==502
    assert error.value.detail["code"]=="CULTURAL_IDENTITY_EVIDENCE_UNTRUSTED"

def test_missing_safety_and_fit_providers_fail_closed_to_review(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product())
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())

    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "review"
    assert decision["may_display"] is False
    assert decision["name"] is None
    assert decision["sku"] is None
    assert decision["price_minor"] is None
    assert decision["image_urls"] == []
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
    assert decision["name"] is None
    assert decision["brand"] is None
    assert decision["price_minor"] is None
    assert decision["image_urls"] == []
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
    assert decision["name"] == "Test garment"
    assert decision["price_minor"] == 150000
    assert decision["image_urls"] == []


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



def test_my_learning_export_combines_only_the_verified_subject(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    calls = []
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda value: "signed-user-42")
    def identity(method, path, subject, payload=None):
        calls.append(("identity", method, path, subject, payload))
        return {"subject_id": subject, "events": [{"event_id": "tal-1"}]}
    def npl(method, path, payload=None):
        calls.append(("npl", method, path, payload))
        return {"user_id": "signed-user-42", "preferences": [{"preference_id": "avoid-blue"}]}
    monkeypatch.setattr(main, "_identity_service_request", identity)
    monkeypatch.setattr(main, "_npl_service_request", npl)
    response = TestClient(main.app).get(
        "/v1/me/learning/export",
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["subject_id"] == "signed-user-42"
    assert data["tal"]["events"][0]["event_id"] == "tal-1"
    assert data["npl"]["preferences"][0]["preference_id"] == "avoid-blue"
    assert calls[0][0:4] == ("identity", "GET", "/v1/tal/export/signed-user-42", "signed-user-42")
    assert calls[1][0:3] == ("npl", "GET", "/v1/users/signed-user-42/export")


def test_my_npl_retraction_binds_owner_server_side(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda value: "signed-user-42")
    seen = {}
    def npl(method, path, payload=None):
        seen.update({"method": method, "path": path, "payload": payload})
        return {"retracted": True, "correction_event_id": payload["correction_event_id"]}
    monkeypatch.setattr(main, "_npl_service_request", npl)
    response = TestClient(main.app).post(
        "/v1/me/npl/preferences/avoid-blue/retract",
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer signed-session"},
        json={"correction_event_id": "correction-123"},
    )
    assert response.status_code == 200, response.text
    assert seen == {
        "method": "POST",
        "path": "/v1/preferences/avoid-blue/retract",
        "payload": {"user_id": "signed-user-42", "correction_event_id": "correction-123"},
    }


def test_my_learning_delete_reports_partial_failure_and_never_claims_complete(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setattr(main, "_verified_actor_from_header", lambda value: "signed-user-42")
    calls = []
    monkeypatch.setattr(
        main, "_identity_service_request",
        lambda method, path, subject, payload=None: calls.append(("tal", method, path, subject)) or {"status": "deleted"},
    )
    def fail_npl(method, path, payload=None):
        calls.append(("npl", method, path, payload))
        raise main.HTTPException(503, detail={"code": "NPL_SERVICE_UNAVAILABLE"})
    monkeypatch.setattr(main, "_npl_service_request", fail_npl)
    response = TestClient(main.app).delete(
        "/v1/me/learning/data",
        headers={**auth_headers(), "X-End-User-Authorization": "Bearer signed-session"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LEARNING_DELETION_PARTIAL"
    assert response.json()["detail"]["tal_deleted"] is True
    assert response.json()["detail"]["npl_deleted"] is False
    assert calls[0] == ("tal", "DELETE", "/v1/tal/users/signed-user-42", "signed-user-42")


def test_my_learning_export_requires_verified_end_user_bearer(client):
    response = client.get("/v1/me/learning/export", headers=auth_headers())
    assert response.status_code == 401


def test_cil_feedback_adjustment_uses_only_available_minimum_cohort_signals():
    score, adjustment = main._feedback_adjusted_score(
        0.8,
        {"status": "available", "unsuitable_share": 0.5, "contributor_count": 30},
        0.10,
    )
    assert score == pytest.approx(0.76)
    assert adjustment["applied"] is True
    assert adjustment["penalty_fraction"] == pytest.approx(0.05)

    unchanged, suppressed = main._feedback_adjusted_score(
        0.8, {"status": "suppressed", "contributor_count": 12}, 0.10
    )
    assert unchanged == 0.8
    assert suppressed["applied"] is False
    assert suppressed["status"] == "suppressed"


def test_cil_feedback_context_key_uses_coarse_context_only():
    context = type("Context", (), {"climate": "Warm Humid", "occasion": "Everyday"})()
    assert main._cil_feedback_context_key(context) == "warm-humid-everyday"


def test_gateway_loads_only_validated_cil_feedback_signals(monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_SERVICE_TOKEN", "cil-service-token-that-is-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "signals": [
                    {"product_id": "p1", "context_key": "warm-everyday", "status": "available",
                     "contributor_count": 35, "unsuitable_share": 0.4},
                    {"product_id": "p2", "context_key": "warm-everyday", "status": "suppressed",
                     "contributor_count": 12, "unsuitable_share": None},
                    {"product_id": "foreign", "context_key": "warm-everyday", "status": "available",
                     "contributor_count": 50, "unsuitable_share": 0.1},
                ]
            }

    def fake_post(url, **kwargs):
        assert url == "https://cil.internal/learning/signals"
        assert kwargs["json"] == {"product_ids": ["p1", "p2"], "context_key": "warm-everyday"}
        assert kwargs["headers"]["Authorization"].startswith("Bearer cil-service-token")
        return FakeResponse()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    signals, status = main._load_cil_feedback_signals(["p1", "p2"], "warm-everyday")
    assert status == "available"
    assert set(signals) == {"p1", "p2"}
    assert signals["p1"]["unsuitable_share"] == 0.4
    assert signals["p2"]["status"] == "suppressed"


def test_cil_serving_assessment_requires_exact_product_version_and_eligible_evidence(monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "cil-catalog-token-that-is-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "product_id": PRODUCT_ID,
                "catalog_version": 3,
                "purpose": "commercial_recommendation",
                "decisions": [
                    {"item_id": "claim-1", "eligible": True},
                    {"item_id": "inci-1", "eligible": True},
                ],
                "all_eligible": True,
            }

    seen = {}
    def fake_post(url, **kwargs):
        seen.update({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    result = main._assess_cil_product_serving(product(
        claims=[{"claim_id": "claim-1"}],
        ingredient_declarations=[{"inci_name": "inci-1"}],
    ))
    assert result["all_eligible"] is True
    assert seen["url"] == "https://cil.internal/serving/assessment"
    assert seen["headers"]["Authorization"].startswith("Bearer cil-catalog-token")
    assert seen["json"]["product_id"] == PRODUCT_ID
    assert seen["json"]["catalog_version"] == 3
    assert len(seen["json"]["claims"]) == 1
    assert len(seen["json"]["ingredient_declarations"]) == 1


def test_cil_serving_assessment_fails_closed_when_evidence_is_not_eligible(monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "cil-catalog-token-that-is-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "product_id": PRODUCT_ID,
                "catalog_version": 3,
                "purpose": "commercial_recommendation",
                "decisions": [{"item_id": "claim-1", "eligible": False}],
                "all_eligible": False,
            }

    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse())
    result = main._assess_cil_product_serving(product(claims=[{"claim_id": "claim-1"}]))
    assert result["all_eligible"] is False
    assert result["decisions"][0]["eligible"] is False


def test_cil_serving_assessment_rejects_stale_or_mismatched_catalog_version(monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "cil-catalog-token-that-is-at-least-32-bytes")

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "product_id": PRODUCT_ID,
                "catalog_version": 2,
                "purpose": "commercial_recommendation",
                "decisions": [],
                "all_eligible": True,
            }

    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(main.HTTPException) as exc:
        main._assess_cil_product_serving(product())
    assert exc.value.status_code == 502


def test_cil_serving_assessment_fails_closed_when_service_is_unavailable(monkeypatch):
    monkeypatch.setenv("CIL_SERVICE_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "cil-catalog-token-that-is-at-least-32-bytes")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(main.httpx.ConnectError("offline")))
    with pytest.raises(main.HTTPException) as exc:
        main._assess_cil_product_serving(product())
    assert exc.value.status_code == 503


def test_cal_show_is_withheld_when_cil_evidence_or_rights_review_is_required(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_product", lambda _: product(claims=[{"claim_id": "claim-unlicensed"}]))
    monkeypatch.setattr(main, "_safety_signal", pass_safety)
    monkeypatch.setattr(main, "_fit_estimate", calibrated_fit)
    monkeypatch.setattr(
        main, "_fit_evidence_fields",
        lambda _estimate: (
            ("body_measurements", "garment_size_chart", "garment_geometry"),
            ("body_measurements", "garment_size_chart", "garment_geometry"),
        ),
    )
    monkeypatch.setattr(main, "_assess_cil_product_serving", lambda *_args, **_kwargs: {
        "product_id": PRODUCT_ID, "catalog_version": 3,
        "purpose": "commercial_recommendation",
        "decisions": [{"item_id": "claim-unlicensed", "eligible": False}],
        "all_eligible": False,
    })
    response = client.post("/v1/decisions", json=request_body(), headers=auth_headers())
    assert response.status_code == 200
    decision = response.json()["candidates"][0]
    assert decision["verdict"] == "show"
    assert decision["may_display"] is False
    assert decision["cil_serving_status"] == "review"
    assert decision["name"] is None
    assert any(reason["code"] == "CIL_EVIDENCE_OR_RIGHTS_REVIEW_REQUIRED" for reason in decision["reasons"])


def test_complementer_requires_verified_end_user_subject(client, monkeypatch):
    response = client.post(
        "/v1/complementer/recommend",
        json={
            "request_id": "complementer-test-003",
            "user_id": "customer-1",
            "preferences": {},
            "look": {"description": "blue shirt"},
        },
        headers=auth_headers(),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "END_USER_BEARER_REQUIRED"


def test_complementer_rejects_user_id_not_bound_to_commerce_subject(client, monkeypatch):
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _authorization: "verified-customer-42")
    monkeypatch.setattr(main, "_complementer_advisory", lambda _payload: pytest.fail("Mismatched identity must not reach Complementer"))
    response = client.post(
        "/v1/complementer/recommend",
        json={
            "request_id": "complementer-test-004",
            "user_id": "attacker-controlled-user",
            "preferences": {},
            "look": {"description": "blue shirt"},
        },
        headers={
            **auth_headers(),
            "X-End-User-Authorization": "Bearer signed-customer-session",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REQUEST_SUBJECT_MISMATCH"

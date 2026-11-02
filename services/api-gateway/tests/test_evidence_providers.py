import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import main


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sign(value, secret):
    return hmac.new(secret.encode(), canonical(value), hashlib.sha256).hexdigest()


def configure(monkeypatch, prefix):
    monkeypatch.setenv(prefix + "_SERVICE_URL", "https://" + prefix.lower() + ".internal")
    monkeypatch.setenv(prefix + "_SERVICE_TOKEN", prefix.lower() + "-service-token-with-at-least-32-bytes")
    monkeypatch.setenv(prefix + "_EVIDENCE_HMAC_SECRET", prefix.lower() + "-evidence-secret-with-at-least-32-bytes")
    monkeypatch.setenv(prefix + "_VALIDATION_HMAC_SECRET", prefix.lower() + "-validation-secret-with-at-least-32-bytes")
    monkeypatch.setenv(prefix + "_VALIDATION_REPORT_SHA256", "a" * 64)


def manifest(prefix, scope, model):
    now = datetime.now(timezone.utc)
    value = {
        "report_sha256": "a" * 64,
        "scope": scope,
        "model_version": model,
        "independent_validation": True,
        "evaluator_id": "independent-auditor",
        "validated_at": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
    }
    value["signature"] = sign(value, prefix.lower() + "-validation-secret-with-at-least-32-bytes")
    return value


def signed_response(value, prefix):
    value["evidence_signature"] = sign(value, prefix.lower() + "-evidence-secret-with-at-least-32-bytes")
    return value


class FakeResponse:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class FakeClient:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def post(self, url, headers, json):
        assert url.endswith("/v1/evaluate")
        assert headers["Authorization"].startswith("Bearer ")
        return FakeResponse(self.payload)


def test_safety_provider_requires_valid_independent_attestation(monkeypatch):
    configure(monkeypatch, "SAFETY")
    product = {"product_id": "product-1", "name": "shirt", "attributes": {"material": "cotton"}}
    snapshot = hashlib.sha256(main._canonical_provider_json(product)).hexdigest()
    result = signed_response({
        "request_id": "req-1", "user_id": "subject-1", "candidate_id": "product-1",
        "product_snapshot_sha256": snapshot, "state": "pass", "reason_code": "SAFETY_CHECKED",
        "explanation": "Independent safety policy found no configured restriction.",
        "evidence_id": "safety-evidence-1", "model_version": "safety-v1",
        "provider_id": "safety-provider", "validation_manifest": manifest("SAFETY", "product_safety", "safety-v1"),
    }, "SAFETY")
    FakeClient.payload = result
    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    signal = main._load_safety_signal(product, user_id="subject-1", request_id="req-1")
    assert signal.state is main.SignalState.PASS
    assert signal.kind is main.SignalKind.SAFETY


def test_safety_provider_rejects_wrong_candidate_snapshot(monkeypatch):
    configure(monkeypatch, "SAFETY")
    product = {"product_id": "product-1", "name": "shirt", "attributes": {}}
    snapshot = "0" * 64
    result = signed_response({
        "request_id": "req-1", "user_id": "subject-1", "candidate_id": "product-1",
        "product_snapshot_sha256": snapshot, "state": "pass", "reason_code": "SAFETY_CHECKED",
        "explanation": "test", "evidence_id": "e1", "model_version": "safety-v1",
        "provider_id": "safety-provider", "validation_manifest": manifest("SAFETY", "product_safety", "safety-v1"),
    }, "SAFETY")
    FakeClient.payload = result
    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_safety_signal(product, user_id="subject-1", request_id="req-1")
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "SAFETY_PROVIDER_EVIDENCE_UNTRUSTED"


def test_fci_provider_requires_calibration_and_independent_attestation(monkeypatch):
    configure(monkeypatch, "FCI")
    product = {"product_id": "product-1", "name": "shirt", "attributes": {}}
    snapshot = hashlib.sha256(main._canonical_provider_json(product)).hexdigest()
    result = signed_response({
        "request_id": "req-1", "user_id": "subject-1", "candidate_id": "product-1",
        "product_snapshot_sha256": snapshot, "estimate_id": "fci-1", "model_version": "fci-v1",
        "calibrated": True, "confidence": 0.82, "lower_bound": 0.75, "upper_bound": 0.89,
        "calibration_version": "cal-2026-10", "interval_level": 0.95,
        "evidence_ids": ["measurements-1", "garment-chart-1"],
        "required_evidence_fields": ["body_measurements", "garment_size_chart"],
        "observed_evidence_fields": ["body_measurements", "garment_size_chart"],
        "provider_id": "fci-provider", "validation_manifest": manifest("FCI", "fit_confidence", "fci-v1"),
    }, "FCI")
    FakeClient.payload = result
    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    estimate = main._load_fci_estimate("subject-1", "product-1", "req-1", product)
    assert estimate.calibrated is True
    assert estimate.confidence == 0.82
    assert main._fit_evidence_fields(estimate) == (
        ("body_measurements", "garment_size_chart"),
        ("body_measurements", "garment_size_chart"),
    )


def test_fci_provider_rejects_expired_validation_manifest(monkeypatch):
    configure(monkeypatch, "FCI")
    product = {"product_id": "product-1", "name": "shirt", "attributes": {}}
    snapshot = hashlib.sha256(main._canonical_provider_json(product)).hexdigest()
    expired = manifest("FCI", "fit_confidence", "fci-v1")
    expired["valid_until"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    expired["signature"] = sign({k: v for k, v in expired.items() if k != "signature"}, "fci-validation-secret-with-at-least-32-bytes")
    result = signed_response({
        "request_id": "req-1", "user_id": "subject-1", "candidate_id": "product-1",
        "product_snapshot_sha256": snapshot, "estimate_id": "fci-1", "model_version": "fci-v1",
        "calibrated": True, "confidence": 0.82, "lower_bound": 0.75, "upper_bound": 0.89,
        "calibration_version": "cal-2026-10", "evidence_ids": ["measurement-1"],
        "required_evidence_fields": ["body_measurements"], "observed_evidence_fields": ["body_measurements"],
        "provider_id": "fci-provider", "validation_manifest": expired,
    }, "FCI")
    FakeClient.payload = result
    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as error:
        main._load_fci_estimate("subject-1", "product-1", "req-1", product)
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "FCI_PROVIDER_EVIDENCE_UNTRUSTED"


def test_absent_providers_remain_unknown_not_pass(monkeypatch):
    for key in (
        "SAFETY_SERVICE_URL", "SAFETY_SERVICE_TOKEN", "SAFETY_EVIDENCE_HMAC_SECRET",
        "SAFETY_VALIDATION_HMAC_SECRET", "SAFETY_VALIDATION_REPORT_SHA256",
        "FCI_SERVICE_URL", "FCI_SERVICE_TOKEN", "FCI_EVIDENCE_HMAC_SECRET",
        "FCI_VALIDATION_HMAC_SECRET", "FCI_VALIDATION_REPORT_SHA256",
    ):
        monkeypatch.delenv(key, raising=False)
    product = {"product_id": "product-1", "name": "shirt", "attributes": {}}
    signal = main._load_safety_signal(product, user_id="subject-1", request_id="req-1")
    estimate = main._load_fci_estimate("subject-1", "product-1", "req-1", product)
    assert signal.state is main.SignalState.UNKNOWN
    assert estimate.calibrated is False

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from age_evidence.store import AgeEvidenceStore, metadata
from age_evidence import api as age_api
import json
from app import main

REDEMPTION_TOKEN = "age-evidence-redemption-test-token-at-least-32-bytes"
NOW = datetime.now(timezone.utc)


def seed_attestation(url: str) -> tuple[str, str]:
    engine = create_engine(url)
    metadata.create_all(engine.execution_options(schema_translate_map={"identity_private": None}))
    store = AgeEvidenceStore(url)
    sid = store.create_session(
        subject_id="subject-api-1", request_id="request-api-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18,
        provider_reference="opaque-ref-" + uuid.uuid4().hex, now=NOW,
    )
    provider_session = str(uuid.uuid4())
    store.attach_provider_session(sid, provider_session, NOW + timedelta(minutes=15), now=NOW)
    store.record_provider_result(
        sid, state="COMPLETE", threshold_met=True, evidence_id="yoti-evidence-1",
        provider_session_id=provider_session, now=NOW + timedelta(seconds=1),
    )
    jti, signature = str(uuid.uuid4()), "f" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=signature, attestation_payload=attestation_payload_for(store, sid, jti),
        issued_at=NOW - timedelta(seconds=2), expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )
    return jti, signature


def attestation_payload_for(store, session_id, jti):
    row = store.get_session(session_id)
    return {
        "jti": jti, "subject_id": row["subject_id"], "request_id": row["request_id"],
        "purpose": row["purpose"], "policy_id": row["policy_id"],
        "policy_version": row["policy_version"], "threshold": row["threshold"],
        "threshold_met": row["threshold_met"],
        "provider_session_id": str(row["provider_session_id"]),
        "provider_evidence_id": row["provider_evidence_id"],
    }


def test_redemption_endpoint_consumes_attestation_once(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "age-api.db")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)
    monkeypatch.setenv("AGE_EVIDENCE_REDEMPTION_TOKEN", REDEMPTION_TOKEN)
    jti, signature = seed_attestation(url)
    payload = {
        "jti": jti, "subject_id": "subject-api-1", "request_id": "request-api-1",
        "purpose": "shopper_eligibility", "policy_id": "adult-market",
        "policy_version": "v1", "threshold": 18, "signature": signature,
    }
    with TestClient(main.app) as client:
        first = client.post(
            "/internal/v1/age-evidence/attestations/redeem",
            headers={"Authorization": "Bearer " + REDEMPTION_TOKEN}, json=payload,
        )
        second = client.post(
            "/internal/v1/age-evidence/attestations/redeem",
            headers={"Authorization": "Bearer " + REDEMPTION_TOKEN}, json=payload,
        )
    assert first.status_code == 200, first.text
    assert first.json() == {"redeemed": True}
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "AGE_EVIDENCE_REPLAY_REVOKED_OR_EXPIRED"


def test_redemption_endpoint_requires_dedicated_internal_credential(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "age-api-auth.db")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)
    monkeypatch.setenv("AGE_EVIDENCE_REDEMPTION_TOKEN", REDEMPTION_TOKEN)
    with TestClient(main.app) as client:
        response = client.post(
            "/internal/v1/age-evidence/attestations/redeem",
            headers={"Authorization": "Bearer wrong-token"},
            json={
                "jti": str(uuid.uuid4()), "subject_id": "s", "request_id": "r",
                "purpose": "shopper_eligibility", "policy_id": "p",
                "policy_version": "1", "threshold": 18, "signature": "a" * 64,
            },
        )
    assert response.status_code == 401


def test_yoti_session_policy_is_selected_only_by_server(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "age-policy.db")
    monkeypatch.setenv("IDENTITY_DATABASE_URL", url)
    monkeypatch.setenv("AGE_EVIDENCE_ORCHESTRATOR_TOKEN", "age-evidence-orchestrator-token-at-least-32-bytes")
    monkeypatch.setenv("EEPL_POLICY_ID", "adult-market")
    monkeypatch.setenv("EEPL_POLICY_REGISTRY_JSON", json.dumps({
        "adult-market": {
            "policy_version": "v2", "minimum_age": 18, "maximum_age": None,
            "allowed_locations": [], "allowed_occasions": [],
            "allowed_climates": [], "required_context": [],
        },
        "youth-market": {
            "policy_version": "v1", "minimum_age": 13, "maximum_age": None,
            "allowed_locations": [], "allowed_occasions": [],
            "allowed_climates": [], "required_context": [],
        },
    }))
    monkeypatch.setattr(age_api, "_service", lambda: type("Fake", (), {
        "start": staticmethod(lambda **kwargs: {
            "threshold": kwargs["threshold"], "policy_id": kwargs["policy_id"],
            "policy_version": kwargs["policy_version"],
        }),
        "close": staticmethod(lambda: None),
    })())
    with TestClient(main.app) as client:
        response = client.post(
            "/internal/v1/age-evidence/sessions",
            headers={"Authorization": "Bearer age-evidence-orchestrator-token-at-least-32-bytes"},
            json={"subject_id": "subject-1", "request_id": "request-1",
                  "purpose": "shopper_eligibility"},
        )
        caller_selected_policy = client.post(
            "/internal/v1/age-evidence/sessions",
            headers={"Authorization": "Bearer age-evidence-orchestrator-token-at-least-32-bytes"},
            json={"subject_id": "subject-1", "request_id": "request-2",
                  "purpose": "shopper_eligibility", "policy_id": "youth-market",
                  "policy_version": "v1"},
        )
        caller_selected_threshold = client.post(
            "/internal/v1/age-evidence/sessions",
            headers={"Authorization": "Bearer age-evidence-orchestrator-token-at-least-32-bytes"},
            json={"subject_id": "subject-1", "request_id": "request-3",
                  "purpose": "shopper_eligibility", "threshold": 1},
        )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "threshold": 18, "policy_id": "adult-market", "policy_version": "v2",
    }
    assert caller_selected_policy.status_code == 422
    assert caller_selected_threshold.status_code == 422

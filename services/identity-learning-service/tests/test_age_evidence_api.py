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
        session_id=sid, jti=jti, signature=signature,
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(minutes=5),
        now=NOW + timedelta(seconds=2),
    )
    return jti, signature


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

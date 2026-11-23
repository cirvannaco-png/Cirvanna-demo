from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "identity-intelligence"))

from age_evidence.service import AgeEvidenceService
from age_evidence.store import AgeEvidenceStore, metadata

NOW = datetime.now(timezone.utc)


class FakeYoti:
    def __init__(self, state="PENDING", threshold_met=None):
        self.state = state
        self.threshold_met = threshold_met
        self.calls = 0
        self.closed = False
        self.session_id = str(uuid.uuid4())

    def create_over_session(self, **kwargs):
        self.reference_id = kwargs["reference_id"]
        self.threshold = kwargs["threshold"]
        return SimpleNamespace(
            session_id=self.session_id,
            expires_at=(NOW + timedelta(minutes=15)).isoformat(),
            user_view_url="https://age.yoti.com/session",
        )

    def get_threshold_result(self, **kwargs):
        self.calls += 1
        assert kwargs["session_id"] == self.session_id
        assert kwargs["expected_reference_id"] == self.reference_id
        assert kwargs["threshold"] == self.threshold
        return SimpleNamespace(
            state=self.state, threshold_met=self.threshold_met,
            evidence_id="yoti-evidence-" + uuid.uuid4().hex,
        )

    def close(self):
        self.closed = True


def make_service(tmp_path, fake):
    url = "sqlite:///" + str(tmp_path / "age-service.db")
    engine = create_engine(url)
    metadata.create_all(engine.execution_options(schema_translate_map={"identity_private": None}))
    return AgeEvidenceService(
        store=AgeEvidenceStore(url), yoti=fake,
        signing_secret="age-evidence-service-test-secret-at-least-32-bytes",
        redirect_url="https://cirvanna.example/age/callback",
        cancel_url="https://cirvanna.example/age/cancel",
        privacy_policy_url="https://cirvanna.example/privacy",
        terms_url="https://cirvanna.example/terms",
    )


def start(service):
    return service.start(
        subject_id="subject-service-1", request_id="request-service-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18,
    )


def test_pending_yoti_result_never_issues_attestation(tmp_path):
    fake = FakeYoti()
    service = make_service(tmp_path, fake)
    session = start(service)
    assert session["state"] == "pending"
    result = service.poll(session["session_id"])
    assert result == {"session_id": session["session_id"], "state": "pending"}
    assert service.store.get_session(session["session_id"])["state"] == "pending"
    service.close()
    assert fake.closed is True


def test_complete_yoti_result_issues_one_signed_single_use_attestation(tmp_path):
    fake = FakeYoti(state="COMPLETE", threshold_met=True)
    service = make_service(tmp_path, fake)
    session = start(service)
    result = service.poll(session["session_id"])
    assert result["state"] == "verified"
    attestation = result["attestation"]
    assert attestation["threshold"] == 18
    assert attestation["threshold_met"] is True
    assert "age_years" not in attestation and "date_of_birth" not in attestation
    assert service.store.consume_attestation(
        jti=attestation["jti"], subject_id=attestation["subject_id"],
        request_id=attestation["request_id"], purpose=attestation["purpose"],
        policy_id=attestation["policy_id"], policy_version=attestation["policy_version"],
        threshold=attestation["threshold"], signature=result["signature"],
    ) is True
    assert service.store.consume_attestation(
        jti=attestation["jti"], subject_id=attestation["subject_id"],
        request_id=attestation["request_id"], purpose=attestation["purpose"],
        policy_id=attestation["policy_id"], policy_version=attestation["policy_version"],
        threshold=attestation["threshold"], signature=result["signature"],
    ) is False
    again = service.poll(session["session_id"])
    assert again["attestation_issued"] is True
    assert again["attestation"] == attestation
    assert again["signature"] == result["signature"]
    assert fake.calls == 1
    service.close()


def test_under_threshold_yoti_result_issues_signed_negative_threshold_evidence(tmp_path):
    fake = FakeYoti(state="FAIL", threshold_met=False)
    service = make_service(tmp_path, fake)
    session = start(service)
    result = service.poll(session["session_id"])
    assert result["state"] == "denied"
    assert result["attestation"]["threshold_met"] is False
    assert result["attestation"]["threshold"] == 18
    again = service.poll(session["session_id"])
    assert again["state"] == "denied"
    assert again["attestation"] == result["attestation"]
    assert again["signature"] == result["signature"]
    assert fake.calls == 1
    service.close()


def test_revoked_yoti_session_cannot_be_polled_or_issue_attestation(tmp_path):
    fake = FakeYoti(state="COMPLETE", threshold_met=True)
    service = make_service(tmp_path, fake)
    session = start(service)
    assert service.revoke(session["session_id"]) is True
    result = service.poll(session["session_id"])
    assert result["state"] == "revoked"
    assert fake.calls == 0
    service.close()

from __future__ import annotations

import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "identity-intelligence"))
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from age_evidence.store import AgeEvidenceStore, metadata

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def make_store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    engine = engine.execution_options(schema_translate_map={"identity_private": None})
    metadata.create_all(engine)
    return AgeEvidenceStore("sqlite://", engine=engine)


def verified_session(store):
    sid = store.create_session(
        subject_id="subject-1", request_id="request-1", purpose="shopper_eligibility",
        policy_id="adult-market", policy_version="4", threshold=18,
        provider_reference="opaque-reference-" + uuid.uuid4().hex, now=NOW,
    )
    store.attach_provider_session(
        sid, str(uuid.uuid4()),
        NOW + timedelta(minutes=15), now=NOW,
    )
    row = store.get_session(sid)
    store.record_provider_result(
        sid, state="COMPLETE", threshold_met=True, evidence_id="evidence-1",
        provider_session_id=row["provider_session_id"], now=NOW + timedelta(seconds=1),
    )
    return sid


def test_attestation_is_single_use_and_bound_to_every_claim():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "a" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=sig,
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(minutes=5),
        now=NOW + timedelta(seconds=2),
    )
    kwargs = dict(
        jti=jti, subject_id="subject-1", request_id="request-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="4", threshold=18, signature=sig,
        now=NOW + timedelta(seconds=3),
    )
    assert store.consume_attestation(**kwargs) is True
    assert store.consume_attestation(**kwargs) is False


def test_attestation_rejects_wrong_subject_request_policy_and_signature():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "b" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=sig,
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(minutes=5),
        now=NOW + timedelta(seconds=2),
    )
    base = dict(
        jti=jti, subject_id="subject-1", request_id="request-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="4", threshold=18, signature=sig,
        now=NOW + timedelta(seconds=3),
    )
    for field, value in (("subject_id", "other"), ("request_id", "other"),
                         ("policy_id", "other"), ("policy_version", "other"),
                         ("threshold", 21), ("signature", "c" * 64)):
        altered = {**base, field: value}
        assert store.consume_attestation(**altered) is False


def test_revoked_session_invalidates_unredeemed_attestation():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "d" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=sig,
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(minutes=5),
        now=NOW + timedelta(seconds=2),
    )
    assert store.revoke_session(sid, now=NOW + timedelta(seconds=3)) is True
    assert store.consume_attestation(
        jti=jti, subject_id="subject-1", request_id="request-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="4", threshold=18, signature=sig,
        now=NOW + timedelta(seconds=4),
    ) is False


def test_provider_session_terminal_result_is_immutable():
    store = make_store()
    sid = verified_session(store)
    row = store.get_session(sid)
    try:
        store.record_provider_result(
            sid, state="FAIL", threshold_met=False, evidence_id="different",
            provider_session_id=row["provider_session_id"], now=NOW + timedelta(seconds=2),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("terminal result mutation must be rejected")


def test_expired_attestation_cannot_be_redeemed():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "e" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=sig,
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(seconds=5),
        now=NOW + timedelta(seconds=2),
    )
    assert store.consume_attestation(
        jti=jti, subject_id="subject-1", request_id="request-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="4", threshold=18, signature=sig,
        now=NOW + timedelta(seconds=6),
    ) is False

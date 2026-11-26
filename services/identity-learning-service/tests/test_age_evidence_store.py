from __future__ import annotations

import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "identity-intelligence"))
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from age_evidence.store import AgeEvidenceConflict, AgeEvidenceStore, metadata

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


def test_attestation_is_single_use_and_bound_to_every_claim():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "a" * 64
    store.issue_attestation(
        session_id=sid, jti=jti, signature=sig, attestation_payload=attestation_payload_for(store, sid, jti),
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
        session_id=sid, jti=jti, signature=sig, attestation_payload=attestation_payload_for(store, sid, jti),
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
        session_id=sid, jti=jti, signature=sig, attestation_payload=attestation_payload_for(store, sid, jti),
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
        session_id=sid, jti=jti, signature=sig, attestation_payload=attestation_payload_for(store, sid, jti),
        issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(seconds=5),
        now=NOW + timedelta(seconds=2),
    )
    assert store.consume_attestation(
        jti=jti, subject_id="subject-1", request_id="request-1",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="4", threshold=18, signature=sig,
        now=NOW + timedelta(seconds=6),
    ) is False


def test_provider_expiry_and_failure_are_terminal_and_cannot_issue_attestations():
    store = make_store()
    sid = store.create_session(
        subject_id="subject-2", request_id="request-2", purpose="shopper_eligibility",
        policy_id="adult-market", policy_version="4", threshold=18,
        provider_reference="opaque-reference-" + uuid.uuid4().hex, now=NOW,
    )
    provider_session = str(uuid.uuid4())
    store.attach_provider_session(sid, provider_session, NOW + timedelta(minutes=15), now=NOW)
    assert store.mark_provider_terminal(
        sid, provider_session, "expired", now=NOW + timedelta(seconds=1),
    ) is True
    row = store.get_session(sid)
    assert row["state"] == "expired"
    try:
        store.issue_attestation(
            session_id=sid, jti=str(uuid.uuid4()), signature="a" * 64,
            attestation_payload={}, issued_at=NOW + timedelta(seconds=2), expires_at=NOW + timedelta(minutes=3),
            now=NOW + timedelta(seconds=2),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expired provider sessions must never issue attestations")


def test_duplicate_request_cannot_create_multiple_provider_sessions():
    store = make_store()
    bindings = dict(
        subject_id="subject-idempotent", request_id="request-idempotent",
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18,
    )
    store.create_session(
        **bindings, provider_reference="opaque-reference-" + uuid.uuid4().hex, now=NOW,
    )
    try:
        store.create_session(
            **bindings, provider_reference="opaque-reference-" + uuid.uuid4().hex, now=NOW,
        )
    except AgeEvidenceConflict:
        pass
    else:
        raise AssertionError("duplicate request must not create another provider session")


def test_attestation_issue_is_idempotent_for_same_payload():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "e" * 64
    payload = attestation_payload_for(store, sid, jti)
    args = dict(
        session_id=sid, jti=jti, signature=sig, attestation_payload=payload,
        issued_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5), now=NOW + timedelta(seconds=2),
    )
    store.issue_attestation(**args)
    store.issue_attestation(**args)
    persisted = store.get_attestation(sid)
    assert persisted["attestation"] == payload
    assert persisted["signature"] == sig


def test_attestation_issue_rejects_different_payload_for_same_session():
    store = make_store()
    sid = verified_session(store)
    jti, sig = str(uuid.uuid4()), "f" * 64
    args = dict(
        session_id=sid, jti=jti, signature=sig,
        issued_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5), now=NOW + timedelta(seconds=2),
    )
    store.issue_attestation(**args, attestation_payload=attestation_payload_for(store, sid, jti))
    different_jti = str(uuid.uuid4())
    try:
        store.issue_attestation(
            **{**args, "jti": different_jti},
            attestation_payload=attestation_payload_for(store, sid, different_jti),
        )
    except AgeEvidenceConflict:
        pass
    else:
        raise AssertionError("a session must not issue a second different attestation")

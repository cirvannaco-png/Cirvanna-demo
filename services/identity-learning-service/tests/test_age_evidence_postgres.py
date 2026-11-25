from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
import uuid
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "identity-intelligence"))
from age_evidence.store import AgeEvidenceStore

DATABASE_URL = os.getenv("AGE_EVIDENCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL migration integration URL not configured")


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


def test_postgres_age_evidence_session_redemption_and_revocation_are_atomic():
    store = AgeEvidenceStore(DATABASE_URL)
    now = datetime.now(timezone.utc)
    signature = "9" * 64

    def verified_session():
        sid = store.create_session(
            subject_id="pg-subject-" + uuid.uuid4().hex,
            request_id="pg-request-" + uuid.uuid4().hex,
            purpose="shopper_eligibility", policy_id="adult-market",
            policy_version="v1", threshold=18,
            provider_reference="pg-" + uuid.uuid4().hex + uuid.uuid4().hex[:8], now=now,
        )
        provider_session = str(uuid.uuid4())
        store.attach_provider_session(sid, provider_session, now + timedelta(minutes=15), now=now)
        store.record_provider_result(
            sid, state="COMPLETE", threshold_met=True,
            evidence_id="yoti-evidence-" + uuid.uuid4().hex,
            provider_session_id=provider_session, now=now + timedelta(seconds=1),
        )
        return sid

    sid = verified_session()
    jti = str(uuid.uuid4())
    store.issue_attestation(
        session_id=sid, jti=jti, signature=signature, attestation_payload=attestation_payload_for(store, sid, jti),
        issued_at=now, expires_at=now + timedelta(minutes=5), now=now,
    )
    row = store.get_session(sid)
    bindings = dict(
        jti=jti, subject_id=row["subject_id"], request_id=row["request_id"],
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18, signature=signature,
    )
    assert store.consume_attestation(**bindings) is True
    assert store.consume_attestation(**bindings) is False

    sid_concurrent = verified_session()
    jti_concurrent = str(uuid.uuid4())
    store.issue_attestation(
        session_id=sid_concurrent, jti=jti_concurrent, signature=signature, attestation_payload=attestation_payload_for(store, sid_concurrent, jti_concurrent),
        issued_at=now, expires_at=now + timedelta(minutes=5), now=now,
    )
    row_concurrent = store.get_session(sid_concurrent)
    concurrent_bindings = dict(
        jti=jti_concurrent, subject_id=row_concurrent["subject_id"],
        request_id=row_concurrent["request_id"], purpose="shopper_eligibility",
        policy_id="adult-market", policy_version="v1", threshold=18,
        signature=signature,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.consume_attestation(**concurrent_bindings), range(2)))
    assert sorted(results) == [False, True]

    sid2 = verified_session()
    jti2 = str(uuid.uuid4())
    store.issue_attestation(
        session_id=sid2, jti=jti2, signature=signature, attestation_payload=attestation_payload_for(store, sid2, jti2),
        issued_at=now, expires_at=now + timedelta(minutes=5), now=now,
    )
    row2 = store.get_session(sid2)
    assert store.revoke_session(sid2, now=now + timedelta(seconds=2)) is True
    assert store.consume_attestation(
        jti=jti2, subject_id=row2["subject_id"], request_id=row2["request_id"],
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18, signature=signature,
    ) is False

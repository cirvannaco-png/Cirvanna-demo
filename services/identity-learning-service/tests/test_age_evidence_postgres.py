from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from age_evidence.store import AgeEvidenceStore

DATABASE_URL = os.getenv("AGE_EVIDENCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL migration integration URL not configured")


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
        session_id=sid, jti=jti, signature=signature,
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

    sid2 = verified_session()
    jti2 = str(uuid.uuid4())
    store.issue_attestation(
        session_id=sid2, jti=jti2, signature=signature,
        issued_at=now, expires_at=now + timedelta(minutes=5), now=now,
    )
    row2 = store.get_session(sid2)
    assert store.revoke_session(sid2, now=now + timedelta(seconds=2)) is True
    assert store.consume_attestation(
        jti=jti2, subject_id=row2["subject_id"], request_id=row2["request_id"],
        purpose="shopper_eligibility", policy_id="adult-market",
        policy_version="v1", threshold=18, signature=signature,
    ) is False

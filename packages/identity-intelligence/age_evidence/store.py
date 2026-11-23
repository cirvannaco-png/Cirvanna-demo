"""Durable age-evidence lifecycle storage.

Only opaque provider/session identifiers and threshold outcomes are retained.
No DOB, raw age, document image, selfie or biometric template is stored.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table,
    and_, create_engine, exists, insert, select, update,
)

metadata = MetaData()
sessions = Table(
    "identity_age_verification_sessions", metadata,
    Column("session_id", String(36), primary_key=True),
    Column("subject_id", String(128), nullable=False),
    Column("request_id", String(128), nullable=False),
    Column("purpose", String(80), nullable=False),
    Column("policy_id", String(100), nullable=False),
    Column("policy_version", String(64), nullable=False),
    Column("threshold", Integer, nullable=False),
    Column("provider", String(24), nullable=False),
    Column("provider_session_id", String(36), unique=True),
    Column("provider_reference_sha256", String(64), nullable=False, unique=True),
    Column("provider_evidence_id", String(160)),
    Column("state", String(20), nullable=False),
    Column("threshold_met", Boolean),
    Column("expires_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("verified_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    schema="identity_private",
)
attestations = Table(
    "identity_age_threshold_attestations", metadata,
    Column("jti", String(36), primary_key=True),
    Column("session_id", String(36), ForeignKey("identity_private.identity_age_verification_sessions.session_id", ondelete="CASCADE"), nullable=False),
    Column("subject_id", String(128), nullable=False),
    Column("request_id", String(128), nullable=False),
    Column("purpose", String(80), nullable=False),
    Column("policy_id", String(100), nullable=False),
    Column("policy_version", String(64), nullable=False),
    Column("threshold", Integer, nullable=False),
    Column("threshold_met", Boolean, nullable=False),
    Column("signature_sha256", String(64), nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    schema="identity_private",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class AgeEvidenceStore:
    """Transactional lifecycle store; redemption is a single conditional UPDATE."""

    def __init__(self, database_url: str, *, engine=None):
        if engine is None:
            if not database_url:
                raise ValueError("age evidence database URL is required")
            engine = create_engine(database_url, pool_pre_ping=True)
        self.engine = engine.execution_options(schema_translate_map={"identity_private": None})

    def create_session(
        self, *, subject_id: str, request_id: str, purpose: str,
        policy_id: str, policy_version: str, threshold: int,
        provider_reference: str, now: datetime | None = None,
    ) -> str:
        if not all(isinstance(v, str) and v.strip() for v in (
            subject_id, request_id, purpose, policy_id, policy_version, provider_reference
        )):
            raise ValueError("session bindings must be non-empty strings")
        if not isinstance(threshold, int) or isinstance(threshold, bool) or not 13 <= threshold <= 125:
            raise ValueError("threshold must be an integer from 13 to 125")
        now = _aware(now or utcnow())
        session_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(insert(sessions).values(
                session_id=session_id, subject_id=subject_id, request_id=request_id,
                purpose=purpose, policy_id=policy_id, policy_version=policy_version,
                threshold=threshold, provider="yoti",
                provider_reference_sha256=hashlib.sha256(provider_reference.encode()).hexdigest(),
                state="created", created_at=now, updated_at=now,
            ))
        return session_id

    def attach_provider_session(
        self, session_id: str, provider_session_id: str, expires_at: datetime,
        *, now: datetime | None = None,
    ) -> None:
        now, expires_at = _aware(now or utcnow()), _aware(expires_at)
        if expires_at <= now:
            raise ValueError("provider session must expire in the future")
        with self.engine.begin() as conn:
            result = conn.execute(update(sessions).where(
                and_(sessions.c.session_id == session_id, sessions.c.state == "created",
                     sessions.c.revoked_at.is_(None))
            ).values(provider_session_id=provider_session_id, expires_at=expires_at,
                     state="pending", updated_at=now))
            if result.rowcount != 1:
                raise ValueError("session is not in a creatable state")

    def record_provider_result(
        self, session_id: str, *, state: str, threshold_met: bool | None,
        evidence_id: str | None, provider_session_id: str,
        now: datetime | None = None,
    ) -> None:
        now = _aware(now or utcnow())
        if state not in {"PENDING", "COMPLETE", "FAIL"}:
            raise ValueError("unsupported provider state")
        if (state == "PENDING" and threshold_met is not None) or (
            state == "COMPLETE" and threshold_met is not True
        ) or (state == "FAIL" and threshold_met is not False):
            raise ValueError("provider state and threshold result disagree")
        next_state = {"PENDING": "pending", "COMPLETE": "verified", "FAIL": "denied"}[state]
        with self.engine.begin() as conn:
            row = conn.execute(select(sessions).where(
                sessions.c.session_id == session_id
            ).with_for_update()).mappings().first()
            if not row or row["state"] not in {"pending", "verified"}:
                raise ValueError("session is missing or no longer active")
            if row["provider_session_id"] != provider_session_id:
                raise ValueError("provider session binding mismatch")
            if row["revoked_at"] is not None or row["expires_at"] is None or _aware(row["expires_at"]) <= now:
                raise ValueError("provider session is revoked or expired")
            if row["state"] == "verified" and (
                row["threshold_met"] != threshold_met or row["provider_evidence_id"] != evidence_id
            ):
                raise ValueError("terminal provider result is immutable")
            conn.execute(update(sessions).where(sessions.c.session_id == session_id).values(
                state=next_state, threshold_met=threshold_met,
                provider_evidence_id=evidence_id, updated_at=now,
                verified_at=now if next_state == "verified" else None,
            ))

    def issue_attestation(
        self, *, session_id: str, jti: str, signature: str,
        issued_at: datetime, expires_at: datetime, now: datetime | None = None,
    ) -> None:
        now, issued_at, expires_at = _aware(now or utcnow()), _aware(issued_at), _aware(expires_at)
        if expires_at <= now or issued_at > now or (expires_at - issued_at).total_seconds() > 900:
            raise ValueError("attestation issuance or expiry is invalid")
        try:
            uuid.UUID(jti)
        except (ValueError, TypeError) as exc:
            raise ValueError("jti must be a UUID") from exc
        with self.engine.begin() as conn:
            row = conn.execute(select(sessions).where(
                sessions.c.session_id == session_id
            ).with_for_update()).mappings().first()
            if not row or row["state"] != "verified" or row["revoked_at"] is not None:
                raise ValueError("only active verified sessions can issue attestations")
            if row["expires_at"] is None or _aware(row["expires_at"]) <= now:
                raise ValueError("verified provider session has expired")
            conn.execute(insert(attestations).values(
                jti=jti, session_id=session_id, subject_id=row["subject_id"],
                request_id=row["request_id"], purpose=row["purpose"],
                policy_id=row["policy_id"], policy_version=row["policy_version"],
                threshold=row["threshold"], threshold_met=row["threshold_met"],
                signature_sha256=hashlib.sha256(signature.encode()).hexdigest(),
                issued_at=issued_at, expires_at=expires_at,
            ))

    def consume_attestation(
        self, *, jti: str, subject_id: str, request_id: str, purpose: str,
        policy_id: str, policy_version: str, threshold: int,
        signature: str, now: datetime | None = None,
    ) -> bool:
        """Atomically redeem once, only while both attestation and source session remain valid."""
        now = _aware(now or utcnow())
        signature_hash = hashlib.sha256(signature.encode()).hexdigest()
        active_session = exists(select(sessions.c.session_id).where(and_(
            sessions.c.session_id == attestations.c.session_id,
            sessions.c.state == "verified", sessions.c.revoked_at.is_(None),
            sessions.c.expires_at > now,
        )))
        predicate = and_(
            attestations.c.jti == jti,
            attestations.c.subject_id == subject_id,
            attestations.c.request_id == request_id,
            attestations.c.purpose == purpose,
            attestations.c.policy_id == policy_id,
            attestations.c.policy_version == policy_version,
            attestations.c.threshold == threshold,
            attestations.c.signature_sha256 == signature_hash,
            attestations.c.issued_at <= now,
            attestations.c.expires_at > now,
            attestations.c.consumed_at.is_(None),
            attestations.c.revoked_at.is_(None),
            active_session,
        )
        with self.engine.begin() as conn:
            result = conn.execute(update(attestations).where(predicate).values(consumed_at=now))
            return result.rowcount == 1

    def revoke_session(self, session_id: str, *, now: datetime | None = None) -> bool:
        now = _aware(now or utcnow())
        with self.engine.begin() as conn:
            result = conn.execute(update(sessions).where(
                and_(sessions.c.session_id == session_id, sessions.c.revoked_at.is_(None))
            ).values(state="revoked", revoked_at=now, updated_at=now))
            conn.execute(update(attestations).where(
                and_(attestations.c.session_id == session_id, attestations.c.revoked_at.is_(None))
            ).values(revoked_at=now))
            return result.rowcount == 1

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(sessions).where(
                sessions.c.session_id == session_id
            )).mappings().first()
            return dict(row) if row else None

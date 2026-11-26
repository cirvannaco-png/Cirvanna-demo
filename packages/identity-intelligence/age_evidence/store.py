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
    Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, JSON,
    and_, create_engine, insert, select, update, UniqueConstraint, Uuid,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
sessions = Table(
    "identity_age_verification_sessions", metadata,
    Column("session_id", Uuid(as_uuid=False), primary_key=True),
    Column("subject_id", String(128), nullable=False),
    Column("request_id", String(128), nullable=False),
    Column("purpose", String(80), nullable=False),
    Column("policy_id", String(100), nullable=False),
    Column("policy_version", String(64), nullable=False),
    Column("threshold", Integer, nullable=False),
    Column("provider", String(24), nullable=False),
    Column("provider_session_id", Uuid(as_uuid=False), unique=True),
    Column("provider_reference", String(96), nullable=False, unique=True),
    Column("provider_reference_sha256", String(64), nullable=False, unique=True),
    Column("provider_evidence_id", String(160)),
    Column("state", String(20), nullable=False),
    Column("threshold_met", Boolean),
    Column("expires_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("verified_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    UniqueConstraint("subject_id", "request_id", "purpose", "policy_id", "policy_version", name="uq_identity_age_session_request_policy"),
    schema="identity_private",
)
attestations = Table(
    "identity_age_threshold_attestations", metadata,
    Column("jti", Uuid(as_uuid=False), primary_key=True),
    Column("session_id", Uuid(as_uuid=False), ForeignKey("identity_private.identity_age_verification_sessions.session_id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("subject_id", String(128), nullable=False),
    Column("request_id", String(128), nullable=False),
    Column("purpose", String(80), nullable=False),
    Column("policy_id", String(100), nullable=False),
    Column("policy_version", String(64), nullable=False),
    Column("threshold", Integer, nullable=False),
    Column("threshold_met", Boolean, nullable=False),
    Column("signature_sha256", String(64), nullable=False),
    Column("attestation_payload", JSON, nullable=False),
    Column("signature", String(128), nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    schema="identity_private",
)


def _uuid_text(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("identifier must be a UUID") from exc


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class AgeEvidenceConflict(RuntimeError):
    pass


class AgeEvidenceStore:
    """Transactional lifecycle store; redemption is a single conditional UPDATE."""

    def __init__(self, database_url: str, *, engine=None):
        if engine is None:
            if not database_url:
                raise ValueError("age evidence database URL is required")
            engine = create_engine(database_url, pool_pre_ping=True)
        self.engine = (engine.execution_options(schema_translate_map={"identity_private": None})
                       if engine.dialect.name == "sqlite" else engine)

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
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(sessions).values(
                    session_id=session_id, subject_id=subject_id, request_id=request_id,
                    purpose=purpose, policy_id=policy_id, policy_version=policy_version,
                    threshold=threshold, provider="yoti",
                    provider_reference=provider_reference,
                    provider_reference_sha256=hashlib.sha256(provider_reference.encode()).hexdigest(),
                    state="created", created_at=now, updated_at=now,
                ))
        except IntegrityError as exc:
            raise AgeEvidenceConflict("a verification session already exists for this request and policy") from exc
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
                and_(sessions.c.session_id == _uuid_text(session_id), sessions.c.state == "created",
                     sessions.c.revoked_at.is_(None))
            ).values(provider_session_id=_uuid_text(provider_session_id), expires_at=expires_at,
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
                sessions.c.session_id == _uuid_text(session_id)
            ).with_for_update()).mappings().first()
            if not row or row["state"] not in {"pending", "verified"}:
                raise ValueError("session is missing or no longer active")
            if _uuid_text(row["provider_session_id"]) != _uuid_text(provider_session_id):
                raise ValueError("provider session binding mismatch")
            if row["revoked_at"] is not None or row["expires_at"] is None or (row["expires_at"].replace(tzinfo=timezone.utc) if row["expires_at"].tzinfo is None else _aware(row["expires_at"])) <= now:
                raise ValueError("provider session is revoked or expired")
            if row["state"] == "verified" and (
                row["threshold_met"] != threshold_met or row["provider_evidence_id"] != evidence_id
            ):
                raise ValueError("terminal provider result is immutable")
            conn.execute(update(sessions).where(sessions.c.session_id == _uuid_text(session_id)).values(
                state=next_state, threshold_met=threshold_met,
                provider_evidence_id=evidence_id, updated_at=now,
                verified_at=now if next_state in {"verified", "denied"} else None,
            ))

    def issue_attestation(
        self, *, session_id: str, jti: str, signature: str,
        attestation_payload: dict[str, Any], issued_at: datetime,
        expires_at: datetime, now: datetime | None = None,
    ) -> None:
        now, issued_at, expires_at = _aware(now or utcnow()), _aware(issued_at), _aware(expires_at)
        if expires_at <= now or issued_at > now or (expires_at - issued_at).total_seconds() > 900:
            raise ValueError("attestation issuance or expiry is invalid")
        try:
            _uuid_text(jti)
        except ValueError as exc:
            raise ValueError("jti must be a UUID") from exc

        try:
            with self.engine.begin() as conn:
                row = conn.execute(select(sessions).where(
                    sessions.c.session_id == _uuid_text(session_id)
                ).with_for_update()).mappings().first()
                if not row or row["state"] not in {"verified", "denied"} or row["revoked_at"] is not None:
                    raise ValueError("only active verified sessions can issue attestations")
                expected = {
                    "jti": _uuid_text(jti), "subject_id": row["subject_id"],
                    "request_id": row["request_id"], "purpose": row["purpose"],
                    "policy_id": row["policy_id"], "policy_version": row["policy_version"],
                    "threshold": row["threshold"], "threshold_met": row["threshold_met"],
                    "provider_session_id": str(uuid.UUID(str(row["provider_session_id"]))),
                    "provider_evidence_id": row["provider_evidence_id"],
                }
                if not isinstance(attestation_payload, dict) or any(
                    attestation_payload.get(key) != value for key, value in expected.items()
                ):
                    raise ValueError("attestation payload does not match durable session bindings")
                session_expiry = row["expires_at"]
                if session_expiry is None:
                    raise ValueError("verified provider session has no expiry")
                if session_expiry.tzinfo is None:
                    session_expiry = session_expiry.replace(tzinfo=timezone.utc)
                else:
                    session_expiry = _aware(session_expiry)
                if session_expiry <= now:
                    raise ValueError("verified provider session has expired")
                conn.execute(insert(attestations).values(
                    jti=_uuid_text(jti), session_id=_uuid_text(session_id),
                    subject_id=row["subject_id"], request_id=row["request_id"],
                    purpose=row["purpose"], policy_id=row["policy_id"],
                    policy_version=row["policy_version"], threshold=row["threshold"],
                    threshold_met=row["threshold_met"],
                    signature_sha256=hashlib.sha256(signature.encode()).hexdigest(),
                    attestation_payload=attestation_payload, signature=signature,
                    issued_at=issued_at, expires_at=expires_at,
                ))
        except IntegrityError as exc:
            existing = self.get_attestation(session_id)
            if (existing is not None
                    and existing["attestation"] == attestation_payload
                    and existing["signature"] == signature):
                return
            raise AgeEvidenceConflict("a different attestation already exists for this session") from exc

    def get_attestation(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(attestations).where(
                attestations.c.session_id == _uuid_text(session_id)
            )).mappings().first()
            if row is None or row["revoked_at"] is not None:
                return None
            return {"attestation": row["attestation_payload"], "signature": row["signature"], "expires_at": row["expires_at"]}

    def consume_attestation(
        self, *, jti: str, subject_id: str, request_id: str, purpose: str,
        policy_id: str, policy_version: str, threshold: int,
        signature: str, now: datetime | None = None,
    ) -> bool:
        """Redeem once while serializing against session revocation.

        Lock order is always session then attestation, matching revoke_session.
        This makes revocation/redemption linearizable under PostgreSQL.
        """
        now = _aware(now or utcnow())
        jti = _uuid_text(jti)
        signature_hash = hashlib.sha256(signature.encode()).hexdigest()
        with self.engine.begin() as conn:
            lookup = conn.execute(select(attestations.c.session_id).where(
                attestations.c.jti == jti
            )).first()
            if lookup is None:
                return False
            session = conn.execute(select(sessions).where(
                sessions.c.session_id == lookup[0]
            ).with_for_update()).mappings().first()
            attestation = conn.execute(select(attestations).where(
                attestations.c.jti == jti
            ).with_for_update()).mappings().first()
            if session is None or attestation is None:
                return False
            session_expiry = session["expires_at"]
            if session_expiry is not None and session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            attestation_expiry = attestation["expires_at"]
            if attestation_expiry.tzinfo is None:
                attestation_expiry = attestation_expiry.replace(tzinfo=timezone.utc)
            issued_at = attestation["issued_at"]
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=timezone.utc)
            if (
                session["state"] not in {"verified", "denied"}
                or session["revoked_at"] is not None
                or session_expiry is None or session_expiry <= now
                or attestation["session_id"] != session["session_id"]
                or attestation["subject_id"] != subject_id
                or attestation["request_id"] != request_id
                or attestation["purpose"] != purpose
                or attestation["policy_id"] != policy_id
                or attestation["policy_version"] != policy_version
                or attestation["threshold"] != threshold
                or attestation["signature_sha256"] != signature_hash
                or issued_at > now or attestation_expiry <= now
                or attestation["consumed_at"] is not None
                or attestation["revoked_at"] is not None
            ):
                return False
            result = conn.execute(update(attestations).where(and_(
                attestations.c.jti == jti,
                attestations.c.consumed_at.is_(None),
                attestations.c.revoked_at.is_(None),
            )).values(consumed_at=now))
            return result.rowcount == 1

    def mark_provider_terminal(
        self, session_id: str, provider_session_id: str, state: str,
        *, now: datetime | None = None,
    ) -> bool:
        if state not in {"expired", "failed"}:
            raise ValueError("provider terminal state must be expired or failed")
        now = _aware(now or utcnow())
        with self.engine.begin() as conn:
            result = conn.execute(update(sessions).where(
                and_(sessions.c.session_id == _uuid_text(session_id),
                     sessions.c.provider_session_id == _uuid_text(provider_session_id),
                     sessions.c.state == "pending", sessions.c.revoked_at.is_(None))
            ).values(state=state, updated_at=now))
            return result.rowcount == 1

    def fail_session(self, session_id: str, *, now: datetime | None = None) -> bool:
        now = _aware(now or utcnow())
        with self.engine.begin() as conn:
            result = conn.execute(update(sessions).where(
                and_(sessions.c.session_id == _uuid_text(session_id), sessions.c.state == "created")
            ).values(state="failed", updated_at=now))
            return result.rowcount == 1

    def revoke_session(self, session_id: str, *, now: datetime | None = None) -> bool:
        now = _aware(now or utcnow())
        with self.engine.begin() as conn:
            result = conn.execute(update(sessions).where(
                and_(sessions.c.session_id == _uuid_text(session_id), sessions.c.revoked_at.is_(None))
            ).values(state="revoked", revoked_at=now, updated_at=now))
            conn.execute(update(attestations).where(
                and_(attestations.c.session_id == _uuid_text(session_id), attestations.c.revoked_at.is_(None))
            ).values(revoked_at=now))
            return result.rowcount == 1

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(sessions).where(
                sessions.c.session_id == _uuid_text(session_id)
            )).mappings().first()
            return dict(row) if row else None

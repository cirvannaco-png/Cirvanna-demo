"""Internal USI profile and TAL persistence API.

This service trusts only the API Gateway's machine credential. The gateway must
resolve end-user subjects through Commerce /me before forwarding a subject_id.
It owns prefixed tables in the existing shared managed Postgres database; it
does not provision a second database or expose a public end-user identity API.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Iterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint, create_engine, select, delete, update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-identity-learning-service"
bearer = HTTPBearer(auto_error=False)
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
SCOPES = {"personalization", "style_learning", "profile_storage", "image_processing", "body_measurements", "twin_storage", "virtual_try_on", "click_it"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def engine_for_url(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def _engine(url: str):
    return engine_for_url(url)


@lru_cache(maxsize=4)
def _session_factory(url: str):
    return sessionmaker(bind=_engine(url), autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class USIProfileRow(Base):
    __tablename__ = "identity_usi_profiles"
    subject_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ConsentReceipt(Base):
    __tablename__ = "identity_tal_consent_receipts"
    __table_args__ = (
        Index("ix_identity_tal_consent_subject_scope", "subject_id", "scope", "granted"),
        Index("ix_identity_tal_consent_bundle", "subject_id", "consent_id", "scope", "granted", "revoked_at"),
        Index("ix_identity_tal_consent_resource", "subject_id", "consent_id", "resource_id"),
    )
    receipt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TALEvent(Base):
    __tablename__ = "identity_tal_events"
    __table_args__ = (
        UniqueConstraint("subject_id", "idempotency_key", name="uq_identity_tal_subject_idempotency"),
        Index("ix_identity_tal_subject_observed", "subject_id", "observed_at"),
        Index("ix_identity_tal_expiry", "expires_at"),
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_receipt_id: Mapped[str] = mapped_column(ForeignKey("identity_tal_consent_receipts.receipt_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="observation")
    supersedes_event_id: Mapped[str | None] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TALDeletionReceipt(Base):
    __tablename__ = "identity_tal_deletion_receipts"
    receipt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_profile: Mapped[bool] = mapped_column(Boolean, nullable=False)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreferenceIn(StrictModel):
    preference_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0, le=1)
    active: bool = True


class ProfilePut(StrictModel):
    expected_version: int | None = Field(default=None, ge=0)
    preferences: list[PreferenceIn] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.preference_id.strip() for x in self.preferences]
        if len(ids) != len(set(ids)):
            raise ValueError("preference_id values must be unique")
        return self


ConsentScope = Literal[
    "personalization", "style_learning", "profile_storage",
    "image_processing", "body_measurements", "twin_storage", "virtual_try_on", "click_it", "wardrobe_image_storage",
]


class ConsentPut(StrictModel):
    receipt_id: str = Field(min_length=8, max_length=128)
    consent_id: str | None = Field(default=None, min_length=8, max_length=128)
    resource_id: str | None = Field(default=None, min_length=3, max_length=160)
    scope: ConsentScope
    consent_version: str = Field(min_length=1, max_length=80)
    granted: bool


class ConsentVerifyIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    required_scopes: list[ConsentScope] = Field(min_length=1, max_length=8)
    resource_id: str | None = Field(default=None, min_length=3, max_length=160)

    @model_validator(mode="after")
    def unique_scopes(self):
        if len(self.required_scopes) != len(set(self.required_scopes)):
            raise ValueError("required_scopes must be unique")
        return self


class EventPut(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=160)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    feature_key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    observed_at: str
    expires_at: str | None = None
    event_kind: Literal["observation", "correction"] = "observation"
    supersedes_event_id: str | None = Field(default=None, max_length=128)

    @field_validator("observed_at")
    @classmethod
    def valid_observed(cls, value):
        parse_time(value)
        return value

    @field_validator("expires_at")
    @classmethod
    def valid_expiry(cls, value):
        if value is not None:
            parse_time(value)
        return value

    @model_validator(mode="after")
    def validate_correction(self):
        if self.event_kind == "correction" and not self.supersedes_event_id:
            raise ValueError("corrections must identify supersedes_event_id")
        if self.event_kind == "observation" and self.supersedes_event_id:
            raise ValueError("observation cannot supersede another event")
        if self.expires_at and parse_time(self.expires_at) <= parse_time(self.observed_at):
            raise ValueError("expires_at must be later than observed_at")
        return self


def get_db() -> Iterator[Session]:
    url = os.getenv("IDENTITY_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "IDENTITY_DATABASE_NOT_CONFIGURED"})
    db = _session_factory(url)()
    try:
        yield db
    finally:
        db.close()


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def subject_or_404(subject_id: str) -> str:
    subject = subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_VERIFIED_SUBJECT"})
    return subject


def _event_hash(payload: EventPut) -> str:
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


app = FastAPI(
    title="Cirvanna USI and TAL service",
    version="1.0.0",
    description="Internal-only persistent explicit preferences and consented temporal learning.",
)


@app.on_event("startup")
def startup() -> None:
    if os.getenv("IDENTITY_AUTO_CREATE_SCHEMA", "false").lower() == "true":
        url = os.getenv("IDENTITY_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("IDENTITY_DATABASE_URL is required")
        Base.metadata.create_all(bind=_engine(url))


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", dependencies=[Depends(require_internal_token)])
def readiness(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(select(USIProfileRow.subject_id).limit(1))
        db.execute(select(ConsentReceipt.receipt_id).limit(1))
        db.execute(select(TALEvent.event_id).limit(1))
        return {"status": "ready", "service": SERVICE, "database": "reachable", "durable_usi": True, "durable_tal": True, "ready": True}
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "IDENTITY_SCHEMA_NOT_READY"})


@app.get("/v1/profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def get_profile(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    active = db.scalar(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject, ConsentReceipt.scope == "profile_storage", ConsentReceipt.granted.is_(True), ConsentReceipt.revoked_at.is_(None)).limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(USIProfileRow, subject)
    if row is None:
        return {"subject_id": subject, "profile_version": 0, "preferences": []}
    return {"subject_id": subject, "profile_version": row.profile_version, "preferences": row.preferences, "updated_at": row.updated_at.isoformat()}


@app.put("/v1/profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def put_profile(subject_id: str, payload: ProfilePut, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    active = db.scalar(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject, ConsentReceipt.scope == "profile_storage", ConsentReceipt.granted.is_(True), ConsentReceipt.revoked_at.is_(None)).limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(USIProfileRow, subject)
    current = row.profile_version if row else 0
    if payload.expected_version is not None and payload.expected_version != current:
        raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": current})
    preferences = [item.model_dump() for item in payload.preferences]
    now = utcnow()
    if row is None:
        row = USIProfileRow(subject_id=subject, profile_version=1, preferences=preferences, updated_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            latest = db.scalar(select(USIProfileRow.profile_version).where(USIProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": latest})
    else:
        statement = update(USIProfileRow).where(USIProfileRow.subject_id == subject)
        if payload.expected_version is not None:
            statement = statement.where(USIProfileRow.profile_version == payload.expected_version)
        result = db.execute(statement.values(
            profile_version=USIProfileRow.profile_version + 1,
            preferences=preferences,
            updated_at=now,
        ))
        if result.rowcount != 1:
            db.rollback()
            latest = db.scalar(select(USIProfileRow.profile_version).where(USIProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": latest})
        db.commit()
        db.expire_all()
        row = db.get(USIProfileRow, subject)
    return {"subject_id": subject, "profile_version": row.profile_version, "preferences": row.preferences, "updated_at": row.updated_at.isoformat()}


@app.post("/v1/tal/consents", dependencies=[Depends(require_internal_token)])
def put_consent(subject_id: str = Query(min_length=1, max_length=128), payload: ConsentPut = None, db: Session = Depends(get_db)):
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "CONSENT_RECEIPT_REQUIRED"})
    consent_id = (payload.consent_id or payload.receipt_id).strip()
    resource_id = payload.resource_id.strip() if payload.resource_id else None
    existing = db.get(ConsentReceipt, payload.receipt_id)
    if existing is not None:
        if (
            existing.subject_id != subject or existing.scope != payload.scope
            or existing.consent_version != payload.consent_version
            or existing.granted != payload.granted
            or existing.consent_id != consent_id or existing.resource_id != resource_id
        ):
            raise HTTPException(409, detail={"code": "CONSENT_RECEIPT_IMMUTABLE"})
        return {
            "receipt_id": existing.receipt_id, "consent_id": existing.consent_id,
            "resource_id": existing.resource_id, "status": "replayed",
            "granted": existing.granted,
        }

    now = utcnow()
    if not payload.granted:
        # Resource-bound withdrawal is confined to this bundle and resource.
        # Legacy unscoped receipts retain their historical scope-wide semantics.
        withdrawal = update(ConsentReceipt).where(
            ConsentReceipt.subject_id == subject,
            ConsentReceipt.scope == payload.scope,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        )
        if resource_id is not None:
            withdrawal = withdrawal.where(
                ConsentReceipt.consent_id == consent_id,
                ConsentReceipt.resource_id == resource_id,
            )
        else:
            withdrawal = withdrawal.where(ConsentReceipt.resource_id.is_(None))
        db.execute(withdrawal.values(revoked_at=now))
    row = ConsentReceipt(
        receipt_id=payload.receipt_id, subject_id=subject, scope=payload.scope,
        consent_id=consent_id, resource_id=resource_id,
        consent_version=payload.consent_version, granted=payload.granted,
        granted_at=now if payload.granted else None,
        revoked_at=None if payload.granted else now,
    )
    db.add(row)
    db.commit()
    return {
        "receipt_id": row.receipt_id, "consent_id": row.consent_id,
        "resource_id": row.resource_id, "status": "recorded", "granted": row.granted,
    }


@app.post("/internal/v1/consents/verify", dependencies=[Depends(require_internal_token)])
def verify_consent(payload: ConsentVerifyIn, db: Annotated[Session, Depends(get_db)]):
    """Verify the current consent bundle and exact resource binding server-side."""
    subject = subject_or_404(payload.subject_id)
    rows = list(db.scalars(select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject,
        ConsentReceipt.consent_id == payload.consent_id,
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
    )).all())
    granted = {row.scope for row in rows if row.resource_id == payload.resource_id}
    if not set(payload.required_scopes).issubset(granted):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})
    matching_rows = [row for row in rows if row.resource_id == payload.resource_id and row.scope in payload.required_scopes]
    versions = sorted({row.consent_version for row in matching_rows})
    return {
        "verified": True, "active": True, "subject_id": subject,
        "consent_id": payload.consent_id, "resource_id": payload.resource_id,
        "granted_scopes": sorted(granted), "consent_versions": versions,
        "consent_version": "|".join(versions),
    }


@app.post("/v1/tal/consents/{receipt_id}/revoke", dependencies=[Depends(require_internal_token)])
def revoke_consent(
    receipt_id: str,
    subject_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    subject = subject_or_404(subject_id)
    receipt = db.get(ConsentReceipt, receipt_id)
    if receipt is None or receipt.subject_id != subject:
        raise HTTPException(404, detail={"code": "CONSENT_RECEIPT_NOT_FOUND"})
    if receipt.granted:
        # Parallel receipts cannot preserve withdrawn consent within this resource bundle.
        revoked_at = utcnow()
        withdrawal = update(ConsentReceipt).where(
            ConsentReceipt.subject_id == subject,
            ConsentReceipt.scope == receipt.scope,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        )
        if receipt.resource_id is not None:
            withdrawal = withdrawal.where(
                ConsentReceipt.consent_id == receipt.consent_id,
                ConsentReceipt.resource_id == receipt.resource_id,
            )
        else:
            withdrawal = withdrawal.where(ConsentReceipt.resource_id.is_(None))
        db.execute(withdrawal.values(revoked_at=revoked_at))
        db.commit()
        db.refresh(receipt)
    return {
        "receipt_id": receipt_id,
        "status": "revoked" if receipt.granted else "already_denied",
        "revoked_at": receipt.revoked_at.isoformat() if receipt.revoked_at else None,
    }


@app.post("/v1/tal/events", dependencies=[Depends(require_internal_token)])
def append_event(subject_id: str = Query(min_length=1, max_length=128), payload: EventPut = None, db: Session = Depends(get_db)):
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "TAL_EVENT_REQUIRED"})
    consent = db.get(ConsentReceipt, payload.consent_receipt_id)
    if consent is None or consent.subject_id != subject or not consent.granted or consent.revoked_at is not None or consent.scope not in {"personalization", "style_learning"}:
        raise HTTPException(403, detail={"code": "ACTIVE_TAL_CONSENT_REQUIRED"})
    digest = _event_hash(payload)
    existing = db.get(TALEvent, payload.event_id)
    if existing is not None:
        if existing.subject_id == subject and existing.payload_hash == digest:
            return {"status": "replayed", "event_id": existing.event_id}
        raise HTTPException(409, detail={"code": "TAL_EVENT_ID_CONFLICT"})
    prior = db.scalar(select(TALEvent).where(TALEvent.subject_id == subject, TALEvent.idempotency_key == payload.idempotency_key))
    if prior is not None:
        if prior.payload_hash == digest:
            return {"status": "replayed", "event_id": prior.event_id}
        raise HTTPException(409, detail={"code": "TAL_IDEMPOTENCY_CONFLICT"})
    if payload.event_kind == "correction":
        target = db.get(TALEvent, payload.supersedes_event_id)
        if target is None or target.subject_id != subject:
            raise HTTPException(404, detail={"code": "TAL_CORRECTION_TARGET_NOT_FOUND"})
        if target.feature_key != payload.feature_key:
            raise HTTPException(409, detail={"code": "TAL_CORRECTION_FEATURE_MISMATCH"})
    row = TALEvent(
        event_id=payload.event_id, subject_id=subject, consent_receipt_id=payload.consent_receipt_id,
        idempotency_key=payload.idempotency_key, payload_hash=digest, feature_key=payload.feature_key,
        value=payload.value, event_kind=payload.event_kind, supersedes_event_id=payload.supersedes_event_id,
        observed_at=parse_time(payload.observed_at), expires_at=parse_time(payload.expires_at) if payload.expires_at else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"code": "TAL_CONCURRENT_IDEMPOTENCY_CONFLICT"})
    return {"status": "recorded", "event_id": row.event_id, "durable_persistence": True}


@app.get("/v1/tal/export/{subject_id}", dependencies=[Depends(require_internal_token)])
def export_events(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    events = list(db.scalars(select(TALEvent).where(TALEvent.subject_id == subject).order_by(TALEvent.observed_at, TALEvent.event_id)).all())
    consents = list(db.scalars(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject).order_by(ConsentReceipt.created_at)).all())
    profile = db.get(USIProfileRow, subject)
    return {
        "subject_id": subject,
        "profile": {"profile_version": profile.profile_version, "preferences": profile.preferences} if profile else None,
        "consent_receipts": [{"receipt_id": x.receipt_id, "consent_id": x.consent_id, "resource_id": x.resource_id,
        "scope": x.scope, "consent_version": x.consent_version, "granted": x.granted, "granted_at": x.granted_at.isoformat() if x.granted_at else None, "revoked_at": x.revoked_at.isoformat() if x.revoked_at else None} for x in consents],
        "events": [{"event_id": x.event_id, "feature_key": x.feature_key, "value": x.value, "event_kind": x.event_kind, "supersedes_event_id": x.supersedes_event_id, "observed_at": x.observed_at.isoformat(), "expires_at": x.expires_at.isoformat() if x.expires_at else None, "consent_receipt_id": x.consent_receipt_id} for x in events],
    }


@app.delete("/v1/tal/users/{subject_id}", dependencies=[Depends(require_internal_token)])
def delete_user_data(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    event_ids = list(db.scalars(select(TALEvent.event_id).where(TALEvent.subject_id == subject)).all())
    profile = db.get(USIProfileRow, subject)
    db.execute(delete(TALEvent).where(TALEvent.subject_id == subject))
    db.execute(delete(ConsentReceipt).where(ConsentReceipt.subject_id == subject))
    if profile is not None:
        db.delete(profile)
    receipt = TALDeletionReceipt(
        receipt_id=str(uuid.uuid4()), subject_digest=hashlib.sha256(subject.encode()).hexdigest(),
        deleted_event_count=len(event_ids), deleted_profile=profile is not None,
    )
    db.add(receipt)
    db.commit()
    return {"status": "deleted", "deleted_events": len(event_ids), "deleted_profile": profile is not None, "deletion_receipt_id": receipt.receipt_id}


@app.post("/internal/retention/purge", dependencies=[Depends(require_internal_token)])
def purge_expired(db: Annotated[Session, Depends(get_db)], cron_token: Annotated[str | None, Header(alias="X-Identity-Cron-Token")] = None):
    expected = os.getenv("IDENTITY_CRON_TOKEN", "").strip()
    if len(expected.encode()) < 32 or not cron_token or not hmac.compare_digest(expected, cron_token):
        raise HTTPException(401, detail={"code": "RETENTION_CRON_AUTH_FAILED"})
    result = db.execute(delete(TALEvent).where(TALEvent.expires_at.is_not(None), TALEvent.expires_at <= utcnow()))
    db.commit()
    return {"status": "complete", "purged_events": result.rowcount or 0}


@app.get("/v1/tal/consents/{subject_id}", dependencies=[Depends(require_internal_token)])
def list_consents(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    rows = list(db.scalars(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject).order_by(ConsentReceipt.created_at)).all())
    return [{
        "receipt_id": x.receipt_id, "consent_id": x.consent_id, "resource_id": x.resource_id,
        "scope": x.scope, "consent_version": x.consent_version, "granted": x.granted,
        "granted_at": x.granted_at.isoformat() if x.granted_at else None,
        "revoked_at": x.revoked_at.isoformat() if x.revoked_at else None,
    } for x in rows]

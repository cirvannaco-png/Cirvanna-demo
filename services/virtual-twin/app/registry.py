"""Persistent, owner-scoped registry for validated Virtual Twin artifacts.

This module stores references and lifecycle metadata only. It does not generate
body meshes, store image bytes, infer identity, or certify fit. Registration is
blocked unless current purpose-specific consent and every asset authorization
are verified by trusted internal providers.
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
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    JSON, DateTime, Index, Integer, String, Text, UniqueConstraint,
    create_engine, select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

router = APIRouter(tags=["virtual-twin-registry"])
bearer = HTTPBearer(auto_error=False)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{2,127}$")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
TWIN_CONSENT_SCOPES = ["image_processing", "body_measurements", "virtual_twin_storage"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TwinRecord(Base):
    __tablename__ = "virtual_twin_records"
    __table_args__ = (
        UniqueConstraint("subject_id", "idempotency_key", name="uq_virtual_twin_subject_idempotency"),
        Index("ix_virtual_twin_subject_status", "subject_id", "status"),
    )

    twin_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    representation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_asset_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_image_asset_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    validation_receipt_id: Mapped[str] = mapped_column(String(160), nullable=False)
    consent_id: Mapped[str] = mapped_column(String(160), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TwinDeletionOutbox(Base):
    __tablename__ = "virtual_twin_deletion_outbox"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_virtual_twin_deletion_command"),
        Index("ix_virtual_twin_deletion_status_created", "status", "created_at"),
    )

    outbox_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    twin_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    command_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterTwinRequest(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    representation_type: Literal["full_body_mesh"]
    artifact_asset_id: str = Field(min_length=3, max_length=160)
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=6)
    model_version: str = Field(min_length=3, max_length=160)
    validation_receipt_id: str = Field(min_length=8, max_length=160)
    consent_id: str = Field(min_length=8, max_length=160)
    consent_version: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @field_validator("subject_id", "twin_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("Identifier is invalid.")
        return value

    @field_validator("artifact_asset_id")
    @classmethod
    def validate_artifact_asset(cls, value: str) -> str:
        value = value.strip()
        if not ASSET_ID_RE.fullmatch(value) or "://" in value or "/" in value or "\\\\" in value:
            raise ValueError("Asset references must be opaque internal identifiers.")
        return value

    @field_validator("source_image_asset_ids")
    @classmethod
    def validate_source_assets(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not ASSET_ID_RE.fullmatch(value) or "://" in value or "/" in value or "\\\\" in value for value in normalized):
            raise ValueError("Source asset references must be opaque internal identifiers.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Source asset references must be unique.")
        return normalized

    @model_validator(mode="after")
    def artifact_is_not_a_source(self):
        if self.artifact_asset_id in self.source_image_asset_ids:
            raise ValueError("The derived Twin artifact cannot also be a source image.")
        return self


class AuthorizeTwinRequest(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)


class DeactivateTwinRequest(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=160)


class RevokeConsentRequest(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=160)
    command_id: str = Field(min_length=8, max_length=100)


def _engine_for_url(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def get_engine(url: str):
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return _engine_for_url(url)


@lru_cache(maxsize=4)
def _session_factory(url: str):
    return sessionmaker(bind=get_engine(url), autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    url = os.getenv("VIRTUAL_TWIN_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "VIRTUAL_TWIN_DATABASE_NOT_CONFIGURED"})
    session = _session_factory(url)()
    try:
        yield session
    finally:
        session.close()


def create_schema_for_tests(url: str) -> None:
    """Create schema only from tests/local tooling; production uses reviewed migrations."""
    Base.metadata.create_all(bind=get_engine(url))


def require_registry_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("VIRTUAL_TWIN_REGISTRY_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "TWIN_REGISTRY_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_deletion_token(
    token: Annotated[str | None, Header(alias="X-Twin-Deletion-Token")] = None,
) -> None:
    expected = os.getenv("VIRTUAL_TWIN_DELETION_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_DELETION_AUTH_NOT_CONFIGURED"})
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "TWIN_DELETION_AUTH_REQUIRED"})


def _trusted_config(url_name: str, token_name: str) -> tuple[str, str] | None:
    raw = os.getenv(url_name, "").strip().rstrip("/")
    token = os.getenv(token_name, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        return None
    return raw, token


async def _verify_consent(subject_id: str, consent_id: str, consent_version: str) -> None:
    config = _trusted_config("CONSENT_API_URL", "CONSENT_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/consents/verify",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "subject_id": subject_id,
                    "consent_id": consent_id,
                    "consent_version": consent_version,
                    "required_scopes": TWIN_CONSENT_SCOPES,
                    "purpose": "virtual_twin_persistence",
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "CONSENT_VERIFICATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_INVALID_RESPONSE"}) from exc
    granted = receipt.get("granted_scopes") if isinstance(receipt, dict) else None
    if not (
        isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("consent_id") == consent_id
        and receipt.get("consent_version") == consent_version
        and isinstance(granted, list)
        and set(TWIN_CONSENT_SCOPES).issubset(set(granted))
    ):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})


async def _verify_mesh_artifact(
    subject_id: str,
    twin_id: str,
    artifact_asset_id: str,
    model_version: str,
    validation_receipt_id: str,
) -> None:
    """Require a separate validator to inspect the actual stored mesh artifact."""
    config = _trusted_config("TWIN_VALIDATION_API_URL", "TWIN_VALIDATION_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_MESH_VALIDATOR_NOT_CONFIGURED"})
    base, token = config
    request_body = {
        "subject_id": subject_id,
        "twin_id": twin_id,
        "artifact_asset_id": artifact_asset_id,
        "representation_type": "full_body_mesh",
        "model_version": model_version,
        "validation_receipt_id": validation_receipt_id,
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(6.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/twins/validate-mesh",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TWIN_MESH_VALIDATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TWIN_MESH_VALIDATOR_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "TWIN_MESH_NOT_VALIDATED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_MESH_VALIDATOR_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "TWIN_MESH_VALIDATOR_INVALID_RESPONSE"}) from exc
    if not (
        isinstance(receipt, dict)
        and receipt.get("validated") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("twin_id") == twin_id
        and receipt.get("artifact_asset_id") == artifact_asset_id
        and receipt.get("representation_type") == "full_body_mesh"
        and receipt.get("model_version") == model_version
        and receipt.get("validation_receipt_id") == validation_receipt_id
    ):
        raise HTTPException(403, detail={"code": "TWIN_MESH_NOT_VALIDATED"})


async def _authorize_assets(subject_id: str, asset_ids: list[str]) -> None:
    config = _trusted_config("TWIN_ASSET_API_URL", "TWIN_ASSET_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_AUTHORIZER_NOT_CONFIGURED"})
    base, token = config
    requested = sorted(set(asset_ids))
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/assets/authorize",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={"subject_id": subject_id, "asset_ids": requested, "purpose": "virtual_twin_storage"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TWIN_ASSET_AUTHORIZATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_AUTHORIZER_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "TWIN_ASSET_ACCESS_DENIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_AUTHORIZER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_AUTHORIZER_INVALID_RESPONSE"}) from exc
    authorized_ids = receipt.get("authorized_asset_ids") if isinstance(receipt, dict) else None
    if not (
        isinstance(receipt, dict)
        and receipt.get("authorized") is True
        and receipt.get("subject_id") == subject_id
        and isinstance(authorized_ids, list)
        and sorted(set(authorized_ids)) == requested
    ):
        raise HTTPException(403, detail={"code": "TWIN_ASSET_ACCESS_DENIED"})


async def _delete_assets(subject_id: str, asset_ids: list[str], idempotency_key: str) -> None:
    config = _trusted_config("TWIN_ASSET_API_URL", "TWIN_ASSET_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_NOT_CONFIGURED"})
    base, token = config
    requested = sorted(set(asset_ids))
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/assets/delete",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "subject_id": subject_id,
                    "asset_ids": requested,
                    "purpose": "virtual_twin_deletion",
                    "cascade_derived_assets": True,
                    "idempotency_key": idempotency_key,
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TWIN_ASSET_DELETION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_INVALID_RESPONSE"}) from exc
    deleted_ids = receipt.get("deleted_asset_ids") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("deleted") is not True
        or receipt.get("subject_id") != subject_id
        or not isinstance(deleted_ids, list)
        or not set(requested).issubset(set(deleted_ids))
    ):
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_INCOMPLETE"})


def _request_hash(payload: RegisterTwinRequest) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _asset_ids(record: TwinRecord) -> list[str]:
    return [record.artifact_asset_id, *record.source_image_asset_ids]


def _queue_deletion(db: Session, record: TwinRecord, command_id: str) -> TwinDeletionOutbox:
    existing = db.scalar(select(TwinDeletionOutbox).where(TwinDeletionOutbox.command_id == command_id))
    if existing is not None:
        return existing
    record.status = "deletion_pending"
    record.version += 1
    record.updated_at = utcnow()
    row = TwinDeletionOutbox(
        outbox_id=str(uuid.uuid4()),
        subject_id=record.subject_id,
        twin_id=record.twin_id,
        asset_ids=_asset_ids(record),
        command_id=command_id,
        status="pending",
        attempts=0,
    )
    db.add(row)
    return row


@router.post("/internal/v1/twins/register", status_code=201)
async def register_twin(
    payload: RegisterTwinRequest,
    response: Response,
    _: Annotated[None, Depends(require_registry_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Register only a validated full-body mesh; pose skeletons are rejected."""
    await _verify_consent(payload.subject_id, payload.consent_id, payload.consent_version)
    await _verify_mesh_artifact(payload.subject_id, payload.twin_id, payload.artifact_asset_id, payload.model_version, payload.validation_receipt_id)
    await _authorize_assets(payload.subject_id, [payload.artifact_asset_id, *payload.source_image_asset_ids])
    digest = _request_hash(payload)
    existing = db.scalar(
        select(TwinRecord).where(
            TwinRecord.subject_id == payload.subject_id,
            TwinRecord.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != digest:
            raise HTTPException(409, detail={"code": "TWIN_REGISTRATION_IDEMPOTENCY_CONFLICT"})
        if existing.status != "active":
            raise HTTPException(409, detail={"code": "TWIN_REGISTRATION_NO_LONGER_ACTIVE"})
        response.status_code = 200
        return {
            "status": "replayed",
            "subject_id": existing.subject_id,
            "twin_id": existing.twin_id,
            "version": existing.version,
            "representation_type": existing.representation_type,
        }
    row = TwinRecord(
        twin_id=payload.twin_id,
        subject_id=payload.subject_id,
        representation_type=payload.representation_type,
        artifact_asset_id=payload.artifact_asset_id,
        source_image_asset_ids=payload.source_image_asset_ids,
        model_version=payload.model_version,
        validation_receipt_id=payload.validation_receipt_id,
        consent_id=payload.consent_id,
        consent_version=payload.consent_version,
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        status="active",
        version=1,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "TWIN_REGISTRATION_CONFLICT"}) from exc
    return {
        "status": "registered",
        "subject_id": row.subject_id,
        "twin_id": row.twin_id,
        "version": row.version,
        "representation_type": row.representation_type,
        "model_version": row.model_version,
        "validation_receipt_id": row.validation_receipt_id,
    }


@router.post("/internal/v1/twins/authorize")
async def authorize_twin(
    payload: AuthorizeTwinRequest,
    _: Annotated[None, Depends(require_registry_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Return ownership only while the record, consent and all asset refs remain active."""
    record = db.get(TwinRecord, payload.twin_id)
    if record is None or record.subject_id != payload.subject_id or record.status != "active":
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})
    await _verify_consent(record.subject_id, record.consent_id, record.consent_version)
    await _verify_mesh_artifact(record.subject_id, record.twin_id, record.artifact_asset_id, record.model_version, record.validation_receipt_id)
    await _authorize_assets(record.subject_id, _asset_ids(record))
    return {
        "authorized": True,
        "active": True,
        "subject_id": record.subject_id,
        "twin_id": record.twin_id,
        "version": record.version,
        "representation_type": record.representation_type,
        "artifact_asset_id": record.artifact_asset_id,
        "model_version": record.model_version,
    }


@router.post("/internal/v1/twins/deactivate", status_code=202)
def deactivate_twin(
    payload: DeactivateTwinRequest,
    _: Annotated[None, Depends(require_registry_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    record = db.get(TwinRecord, payload.twin_id)
    if record is None or record.subject_id != payload.subject_id:
        raise HTTPException(404, detail={"code": "TWIN_RECORD_NOT_FOUND"})
    existing = db.scalar(select(TwinDeletionOutbox).where(TwinDeletionOutbox.command_id == payload.command_id))
    if existing is not None:
        return {"status": existing.status, "twin_id": record.twin_id, "deletion_queued": True, "version": record.version}
    if record.status == "deleted":
        return {"status": "complete", "twin_id": record.twin_id, "deletion_queued": False, "version": record.version}
    if record.status == "active" and payload.expected_version != record.version:
        raise HTTPException(409, detail={"code": "TWIN_VERSION_CONFLICT", "current_version": record.version})
    if record.status == "active":
        _queue_deletion(db, record, payload.command_id)
        db.commit()
    return {"status": "pending", "twin_id": record.twin_id, "deletion_queued": True, "version": record.version}


@router.post("/internal/v1/twins/revoke-consent", status_code=202)
def revoke_twin_consent(
    payload: RevokeConsentRequest,
    _: Annotated[None, Depends(require_registry_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Queue deletion for every Twin created under a withdrawn consent receipt."""
    records = db.scalars(
        select(TwinRecord).where(
            TwinRecord.subject_id == payload.subject_id,
            TwinRecord.consent_id == payload.consent_id,
            TwinRecord.status == "active",
        )
    ).all()
    for record in records:
        command_digest = hashlib.sha256(f"{payload.command_id}:{record.twin_id}".encode("utf-8")).hexdigest()
        _queue_deletion(db, record, "consent-revocation:" + command_digest)
    db.commit()
    return {"status": "pending" if records else "complete", "twins_queued": len(records)}


@router.post("/internal/v1/twins/deletions/dispatch")
def dispatch_twin_deletions(
    _: Annotated[None, Depends(require_deletion_token)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 20,
) -> dict[str, object]:
    """Idempotently dispatch asset deletion; never mark complete without provider proof."""
    if limit < 1 or limit > 100:
        raise HTTPException(422, detail={"code": "INVALID_DELETION_BATCH_SIZE"})
    pending = db.scalars(
        select(TwinDeletionOutbox)
        .where(TwinDeletionOutbox.status == "pending")
        .order_by(TwinDeletionOutbox.created_at)
        .limit(limit)
    ).all()
    completed = 0
    failed = 0
    for item in pending:
        try:
            # The asset provider must treat this key idempotently and cascade to
            # every derived artifact belonging to the subject/Twin.
            import anyio
            anyio.run(_delete_assets, item.subject_id, list(item.asset_ids), "twin-delete:" + item.outbox_id)
            item.status = "complete"
            item.last_error_code = None
            item.completed_at = utcnow()
            twin = db.get(TwinRecord, item.twin_id)
            if twin is not None and twin.status == "deletion_pending":
                twin.status = "deleted"
                twin.version += 1
                twin.updated_at = utcnow()
                twin.deleted_at = utcnow()
            completed += 1
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            item.attempts += 1
            item.last_error_code = str(detail.get("code", "TWIN_ASSET_DELETION_FAILED"))[:80]
            failed += 1
        except Exception:
            item.attempts += 1
            item.last_error_code = "TWIN_ASSET_DELETION_FAILED"
            failed += 1
    db.commit()
    return {"processed": len(pending), "completed": completed, "failed": failed}


@router.get("/internal/v1/twins/{twin_id}/status")
def twin_status(
    twin_id: str,
    subject_id: str,
    _: Annotated[None, Depends(require_registry_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    record = db.get(TwinRecord, twin_id)
    if record is None or record.subject_id != subject_id:
        raise HTTPException(404, detail={"code": "TWIN_RECORD_NOT_FOUND"})
    return {
        "twin_id": record.twin_id,
        "status": record.status,
        "version": record.version,
        "representation_type": record.representation_type,
        "model_version": record.model_version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
    }

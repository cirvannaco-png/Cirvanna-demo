"""Canonical, owner-bound Twin metadata registry.

This service stores Twin lineage and references only. Asset bytes remain in the
existing private Asset Service; no URL, path, object-store key, or public media
URL is accepted or returned.
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
from typing import Annotated, Iterator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-twin-registry"
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
bearer = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def engine_for_url(url: str):
    from sqlalchemy import create_engine
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


class TwinRecord(Base):
    __tablename__ = "twin_registry_twins"
    __table_args__ = (
        Index("ix_twin_registry_twin_owner_state", "subject_id", "state"),
    )

    twin_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mesh_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_image_asset_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    representation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full_body_mesh")
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    model_release_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TwinDeletionOutbox(Base):
    __tablename__ = "twin_registry_deletion_outbox"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_twin_registry_deletion_command"),
        Index("ix_twin_registry_deletion_status_created", "status", "created_at"),
    )

    outbox_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    twin_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("twin_registry_twins.twin_id"), nullable=False
    )
    asset_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    command_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TwinCreate(StrictModel):
    twin_id: str = Field(min_length=8, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    mesh_asset_id: str = Field(min_length=36, max_length=36)
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=12)
    consent_id: str = Field(min_length=8, max_length=128)
    model_id: str = Field(min_length=2, max_length=160)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    model_release_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_attestation_hmac: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("twin_id", "subject_id", "consent_id", "model_id")
    @classmethod
    def trim_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @field_validator("mesh_asset_id")
    @classmethod
    def valid_mesh_asset_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not UUID_RE.fullmatch(value):
            raise ValueError("mesh_asset_id must be an opaque Asset Service UUID")
        return value

    @field_validator("source_image_asset_ids")
    @classmethod
    def valid_source_asset_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        if any(not UUID_RE.fullmatch(value) for value in normalized):
            raise ValueError("source image IDs must be opaque Asset Service UUIDs")
        if len(normalized) != len(set(normalized)):
            raise ValueError("source_image_asset_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def mesh_not_in_source_list(self):
        if self.mesh_asset_id in self.source_image_asset_ids:
            raise ValueError("mesh asset must be distinct from source image assets")
        return self


class TwinDeactivate(StrictModel):
    twin_id: str = Field(min_length=8, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=0)
    command_id: str = Field(min_length=8, max_length=160)

    @field_validator("twin_id", "subject_id", "command_id")
    @classmethod
    def validate_deactivation_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value


class TwinConsentRevocation(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    command_id: str = Field(min_length=8, max_length=100)

    @field_validator("subject_id", "consent_id", "command_id")
    @classmethod
    def validate_revocation_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value


class TwinOwner(StrictModel):
    twin_id: str = Field(min_length=8, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)

    @field_validator("twin_id", "subject_id")
    @classmethod
    def trim_owner_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value


def get_db() -> Iterator[Session]:
    url = os.getenv("TWIN_REGISTRY_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_DATABASE_NOT_CONFIGURED"})
    db = _session_factory(url)()
    try:
        yield db
    finally:
        db.close()


def require_deletion_token(
    token: Annotated[str | None, Header(alias="X-Twin-Deletion-Token")] = None,
) -> None:
    expected = os.getenv("TWIN_REGISTRY_DELETION_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_DELETION_AUTH_NOT_CONFIGURED"})
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "TWIN_DELETION_AUTH_REQUIRED"})


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("TWIN_REGISTRY_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _trusted_config(url_name: str, token_name: str) -> tuple[str, str] | None:
    raw = os.getenv(url_name, "").strip().rstrip("/")
    token = os.getenv(token_name, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        if (
            not host or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
            or (parts.scheme != "https" and not (parts.scheme == "http" and local))
        ):
            return None
    except ValueError:
        return None
    return raw, token


async def _json_request(
    method: str, base: str, path: str, token: str, *,
    json_body: dict | None = None,
):
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            return await client.request(
                method,
                base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=json_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TWIN_DEPENDENCY_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TWIN_DEPENDENCY_UNAVAILABLE"}) from exc


def _verify_validation_attestation(payload: TwinCreate) -> None:
    secret = os.getenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_VALIDATION_ATTESTATION_NOT_CONFIGURED"})
    body = {
        "twin_id": payload.twin_id,
        "subject_id": payload.subject_id,
        "mesh_asset_id": payload.mesh_asset_id,
        "source_image_asset_ids": sorted(payload.source_image_asset_ids),
        "consent_id": payload.consent_id,
        "model_id": payload.model_id.strip(),
        "model_revision": payload.model_revision,
        "model_release_sha256": payload.model_release_sha256,
        "validation_report_sha256": payload.validation_report_sha256,
        "representation_type": "full_body_mesh",
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.validation_attestation_hmac):
        raise HTTPException(403, detail={"code": "TWIN_VALIDATION_ATTESTATION_INVALID"})


async def _verify_consent(
    *, subject_id: str, consent_id: str, twin_id: str, consent_version: str | None = None,
) -> dict:
    config = _trusted_config("CONSENT_API_URL", "CONSENT_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    base, token = config
    request_body: dict[str, object] = {
        "subject_id": subject_id,
        "consent_id": consent_id,
        "required_scopes": ["image_processing", "body_measurements", "virtual_twin_storage"],
        "resource_id": twin_id,
    }
    if consent_version:
        request_body["consent_version"] = consent_version
    response = await _json_request("POST", base, "/internal/v1/consents/verify", token, json_body=request_body)
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "TWIN_CONSENT_NOT_ACTIVE"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CONSENT_PROVIDER_INVALID_RESPONSE"}) from exc
    required = {"image_processing", "body_measurements", "virtual_twin_storage"}
    if not (
        isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("consent_id") == consent_id
        and receipt.get("resource_id") == twin_id
        and required.issubset(set(receipt.get("granted_scopes", [])))
        and isinstance(receipt.get("consent_version"), str)
        and bool(receipt.get("consent_version"))
        and (consent_version is None or receipt.get("consent_version") == consent_version)
    ):
        raise HTTPException(403, detail={"code": "TWIN_CONSENT_NOT_ACTIVE"})
    return receipt


async def _authorize_assets(
    *, subject_id: str, twin_id: str, mesh_asset_id: str, source_image_asset_ids: list[str],
) -> None:
    config = _trusted_config("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_NOT_CONFIGURED"})
    base, token = config
    expected_ids = sorted([mesh_asset_id, *source_image_asset_ids])
    response = await _json_request(
        "POST",
        base,
        "/internal/v1/assets/authorize",
        token,
        json_body={
            "subject_id": subject_id,
            "purpose": "virtual_twin_storage",
            "parent_id": twin_id,
            "asset_ids": expected_ids,
        },
    )
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "TWIN_ASSET_OWNERSHIP_REQUIRED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "ASSET_SERVICE_INVALID_RESPONSE"}) from exc
    granted_ids = receipt.get("authorized_asset_ids") if isinstance(receipt, dict) else None
    if not (
        isinstance(receipt, dict)
        and receipt.get("authorized") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("parent_id") == twin_id
        and receipt.get("purpose") == "virtual_twin_storage"
        and isinstance(granted_ids, list)
        and sorted(granted_ids) == expected_ids
    ):
        raise HTTPException(403, detail={"code": "TWIN_ASSET_OWNERSHIP_REQUIRED"})


async def _delete_assets(subject_id: str, twin_id: str, asset_ids: list[str], idempotency_key: str) -> None:
    """Delete a Twin and all derivatives through the canonical private Asset Service."""
    config = _trusted_config("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_NOT_CONFIGURED"})
    base, token = config
    requested = sorted(set(asset_ids))
    response = await _json_request(
        "POST",
        base,
        "/internal/v1/assets/delete",
        token,
        json_body={
            "subject_id": subject_id,
            "asset_ids": requested,
            "parent_id": twin_id,
            "purpose": "virtual_twin_deletion",
            "cascade_derived_assets": True,
            "idempotency_key": idempotency_key,
        },
    )
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "TWIN_ASSET_DELETION_INVALID_RESPONSE"}) from exc
    deleted_ids = receipt.get("deleted_asset_ids") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("deleted") is not True
        or receipt.get("subject_id") != subject_id
        or receipt.get("idempotency_key") != idempotency_key
        or not isinstance(deleted_ids, list)
        or not set(requested).issubset(set(deleted_ids))
    ):
        raise HTTPException(503, detail={"code": "TWIN_ASSET_DELETION_INCOMPLETE"})


def _queue_deletion(db: Session, record: TwinRecord, command_id: str) -> TwinDeletionOutbox:
    existing = db.scalar(select(TwinDeletionOutbox).where(
        TwinDeletionOutbox.command_id == command_id
    ))
    if existing is not None:
        if existing.subject_id != record.subject_id or existing.twin_id != record.twin_id:
            raise HTTPException(409, detail={"code": "TWIN_DELETION_COMMAND_CONFLICT"})
        return existing
    if record.state == "deleted":
        raise HTTPException(409, detail={"code": "TWIN_ALREADY_DELETED"})
    record.state = "deletion_pending"
    record.version += 1
    record.updated_at = utcnow()
    row = TwinDeletionOutbox(
        outbox_id=str(uuid.uuid4()),
        subject_id=record.subject_id,
        twin_id=record.twin_id,
        asset_ids=sorted({record.mesh_asset_id, *record.source_image_asset_ids}),
        command_id=command_id,
        status="pending",
        attempts=0,
    )
    db.add(row)
    return row


def _response(row: TwinRecord, *, status: str | None = None) -> dict:
    return {
        "twin_id": row.twin_id,
        "subject_id": row.subject_id,
        "status": status or row.state,
        "state": row.state,
        "active": row.state == "active",
        "authorized": row.state == "active",
        "version": row.version,
        "representation_type": row.representation_type,
        "mesh_asset_id": row.mesh_asset_id,
        "source_image_asset_ids": list(row.source_image_asset_ids),
        "model_id": row.model_id,
        "model_revision": row.model_revision,
        "model_release_sha256": row.model_release_sha256,
        "validation_report_sha256": row.validation_report_sha256,
        "consent_version": row.consent_version,
        "created_at": row.created_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


app = FastAPI(
    title="Cirvanna Twin Registry",
    version="2.0.0",
    description="Internal owner-bound persistent Twin lineage; bytes remain in private Asset Service.",
)


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


async def _dependency_ready(base: str, token: str) -> bool:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                base + "/ready",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        if response.status_code != 200:
            return False
        payload = response.json()
        return isinstance(payload, dict) and payload.get("ready") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


@app.get("/ready", dependencies=[Depends(require_internal_token)])
async def ready(db: Session = Depends(get_db)):
    consent_config = _trusted_config("CONSENT_API_URL", "CONSENT_API_TOKEN")
    asset_config = _trusted_config("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if consent_config is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    if asset_config is None:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_NOT_CONFIGURED"})
    if len(os.getenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", "").encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_VALIDATION_ATTESTATION_NOT_CONFIGURED"})
    if len(os.getenv("TWIN_REGISTRY_DELETION_TOKEN", "").encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_DELETION_AUTH_NOT_CONFIGURED"})
    try:
        db.execute(select(TwinRecord.twin_id).limit(1))
        db.execute(select(TwinDeletionOutbox.outbox_id).limit(1))
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_SCHEMA_NOT_READY"}) from exc
    consent_ready = await _dependency_ready(*consent_config)
    if not consent_ready:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_READY"})
    asset_ready = await _dependency_ready(*asset_config)
    if not asset_ready:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_NOT_READY"})
    return {
        "status": "ready",
        "service": SERVICE,
        "database": "reachable",
        "consent_provider": "ready",
        "asset_service": "ready",
        "validation_attestation_configured": True,
        "ready": True,
    }


@app.post("/internal/v1/twins", dependencies=[Depends(require_internal_token)])
async def create_twin(payload: TwinCreate, db: Session = Depends(get_db)):
    subject = payload.subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    _verify_validation_attestation(payload)
    consent = await _verify_consent(
        subject_id=subject, consent_id=payload.consent_id, twin_id=payload.twin_id,
    )
    await _authorize_assets(
        subject_id=subject,
        twin_id=payload.twin_id,
        mesh_asset_id=payload.mesh_asset_id,
        source_image_asset_ids=payload.source_image_asset_ids,
    )

    existing = db.get(TwinRecord, payload.twin_id)
    if existing is not None:
        same = (
            existing.subject_id == subject
            and existing.mesh_asset_id == payload.mesh_asset_id
            and sorted(existing.source_image_asset_ids) == sorted(payload.source_image_asset_ids)
            and existing.consent_id == payload.consent_id
            and existing.model_id == payload.model_id.strip()
            and existing.model_revision == payload.model_revision
            and existing.model_release_sha256 == payload.model_release_sha256
            and existing.validation_report_sha256 == payload.validation_report_sha256
        )
        if same and existing.state == "active":
            # Consent and Asset Service were rechecked before replay is accepted.
            return _response(existing, status="replayed")
        raise HTTPException(409, detail={"code": "TWIN_ID_IMMUTABLE"})

    row = TwinRecord(
        twin_id=payload.twin_id,
        subject_id=subject,
        mesh_asset_id=payload.mesh_asset_id,
        source_image_asset_ids=sorted(payload.source_image_asset_ids),
        representation_type="full_body_mesh",
        consent_id=payload.consent_id,
        consent_version=consent["consent_version"],
        model_id=payload.model_id.strip(),
        model_revision=payload.model_revision,
        model_release_sha256=payload.model_release_sha256,
        validation_report_sha256=payload.validation_report_sha256,
        state="active",
        version=1,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "TWIN_CREATE_CONFLICT"}) from exc
    return _response(row)


@app.post("/internal/v1/twins/authorize", dependencies=[Depends(require_internal_token)])
async def authorize_twin(payload: TwinOwner, db: Session = Depends(get_db)):
    subject = payload.subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    row = db.get(TwinRecord, payload.twin_id)
    if row is None or row.subject_id != subject or row.state != "active":
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})
    # Consent and all source assets are revalidated for every authorization.
    await _verify_consent(
        subject_id=subject,
        consent_id=row.consent_id,
        twin_id=row.twin_id,
        consent_version=row.consent_version,
    )
    await _authorize_assets(
        subject_id=subject,
        twin_id=row.twin_id,
        mesh_asset_id=row.mesh_asset_id,
        source_image_asset_ids=list(row.source_image_asset_ids),
    )
    return _response(row)


@app.post("/internal/v1/twins/deactivate", status_code=202, dependencies=[Depends(require_internal_token)])
def deactivate_twin(payload: TwinDeactivate, db: Session = Depends(get_db)):
    subject = payload.subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    row = db.get(TwinRecord, payload.twin_id)
    if row is None or row.subject_id != subject:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND"})
    existing = db.scalar(select(TwinDeletionOutbox).where(
        TwinDeletionOutbox.command_id == payload.command_id
    ))
    if existing is not None:
        if existing.subject_id != subject or existing.twin_id != row.twin_id:
            raise HTTPException(409, detail={"code": "TWIN_DELETION_COMMAND_CONFLICT"})
        return {"status": existing.status, "twin_id": row.twin_id, "deletion_queued": True, "version": row.version}
    if row.state == "deleted":
        return {"status": "complete", "twin_id": row.twin_id, "deletion_queued": False, "version": row.version}
    if row.state == "active" and payload.expected_version != row.version:
        raise HTTPException(409, detail={"code": "TWIN_VERSION_CONFLICT", "current_version": row.version})
    if row.state == "active":
        _queue_deletion(db, row, payload.command_id)
        db.commit()
    return {"status": "pending", "twin_id": row.twin_id, "deletion_queued": True, "version": row.version}


@app.post("/internal/v1/twins/revoke-consent", status_code=202, dependencies=[Depends(require_internal_token)])
def revoke_twin_consent(payload: TwinConsentRevocation, db: Session = Depends(get_db)):
    subject = payload.subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    records = db.scalars(select(TwinRecord).where(
        TwinRecord.subject_id == subject,
        TwinRecord.consent_id == payload.consent_id,
        TwinRecord.state == "active",
    )).all()
    for row in records:
        digest = hashlib.sha256(f"{payload.command_id}:{row.twin_id}".encode("utf-8")).hexdigest()
        _queue_deletion(db, row, "consent-revocation:" + digest)
    db.commit()
    return {"status": "pending" if records else "complete", "twins_queued": len(records)}


@app.post("/internal/v1/twins/deletions/dispatch", dependencies=[Depends(require_deletion_token)])
async def dispatch_twin_deletions(db: Session = Depends(get_db), limit: int = 20):
    if limit < 1 or limit > 100:
        raise HTTPException(422, detail={"code": "INVALID_DELETION_BATCH_SIZE"})
    pending = db.scalars(select(TwinDeletionOutbox).where(
        TwinDeletionOutbox.status == "pending"
    ).order_by(TwinDeletionOutbox.created_at).limit(limit)).all()
    completed = failed = 0
    for item in pending:
        try:
            await _delete_assets(
                item.subject_id, item.twin_id, list(item.asset_ids),
                "twin-delete:" + item.outbox_id,
            )
            item.status = "complete"
            item.last_error_code = None
            item.completed_at = utcnow()
            row = db.get(TwinRecord, item.twin_id)
            if row is not None and row.state == "deletion_pending":
                row.state = "deleted"
                row.version += 1
                row.updated_at = utcnow()
                row.deleted_at = utcnow()
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


@app.get("/internal/v1/twins/{twin_id}/status", dependencies=[Depends(require_internal_token)])
def twin_status(twin_id: str, subject_id: str, db: Session = Depends(get_db)):
    row = db.get(TwinRecord, twin_id)
    if row is None or row.subject_id != subject_id:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND"})
    return {
        "twin_id": row.twin_id,
        "subject_id": row.subject_id,
        "status": row.state,
        "version": row.version,
        "representation_type": row.representation_type,
        "model_version": row.model_id + "@" + row.model_revision,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


@app.post("/internal/v1/twins/revoke", dependencies=[Depends(require_internal_token)])
def revoke_twin(payload: TwinOwner, db: Session = Depends(get_db)):
    subject = payload.subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    row = db.get(TwinRecord, payload.twin_id)
    if row is None or row.subject_id != subject:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND"})
    if row.state == "deleted":
        return _response(row)
    if row.state == "active":
        _queue_deletion(db, row, "revoke:" + row.twin_id + ":" + str(row.version))
        db.commit()
    return _response(row, status="deletion_pending")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

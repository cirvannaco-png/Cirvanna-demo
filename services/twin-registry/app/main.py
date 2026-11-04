"""Persistent user-owned Twin and private asset metadata registry.

The registry stores ownership and lifecycle metadata only. Object bytes remain
in a private object store controlled by a trusted upload/renderer; this API never
accepts URLs, reads public files, or exposes signed download URLs.
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

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-twin-registry"
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
OPAQUE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MESH_TYPES = {"model/gltf+json", "model/gltf-binary", "application/octet-stream"}
bearer = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


class AssetRecord(Base):
    __tablename__ = "twin_registry_assets"
    __table_args__ = (
        UniqueConstraint("storage_object_key", name="uq_twin_registry_storage_key"),
        Index("ix_twin_registry_asset_owner_state", "owner_subject_id", "state"),
        Index("ix_twin_registry_asset_product_state", "product_id", "state"),
    )
    asset_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    owner_subject_id: Mapped[str | None] = mapped_column(String(128), index=True)
    tenant_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    asset_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    access_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    twin_id: Mapped[str | None] = mapped_column(String(128), index=True)
    product_id: Mapped[str | None] = mapped_column(String(128), index=True)
    storage_object_key: Mapped[str] = mapped_column(String(160), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TwinRecord(Base):
    __tablename__ = "twin_registry_twins"
    __table_args__ = (Index("ix_twin_registry_twin_owner_state", "subject_id", "state"),)
    twin_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mesh_asset_id: Mapped[str] = mapped_column(ForeignKey("twin_registry_assets.asset_id"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    model_release_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetRegister(StrictModel):
    owner_subject_id: str | None = Field(default=None, min_length=3, max_length=128)
    tenant_id: str = Field(min_length=3, max_length=160)
    asset_kind: Literal["twin_mesh", "person_reference", "catalog_garment", "user_garment", "try_on_output"]
    access_scope: Literal["private", "catalog"]
    twin_id: str | None = Field(default=None, min_length=3, max_length=128)
    product_id: str | None = Field(default=None, min_length=3, max_length=128)
    storage_object_key: str = Field(min_length=3, max_length=160)
    content_type: str = Field(min_length=3, max_length=100)
    byte_size: int = Field(gt=0, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("owner_subject_id", "twin_id", "product_id")
    @classmethod
    def clean_optional_ids(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("identifier must not be blank")
        return value

    @field_validator("storage_object_key")
    @classmethod
    def opaque_storage_key(cls, value):
        value = value.strip()
        if not OPAQUE_KEY_RE.fullmatch(value) or ".." in value or "/" in value or "\\" in value or "://" in value:
            raise ValueError("storage key must be an opaque provider-generated identifier")
        return value

    @model_validator(mode="after")
    def valid_asset_ownership(self):
        if self.access_scope == "private":
            if self.owner_subject_id is None:
                raise ValueError("private assets require an owner subject")
            if self.tenant_id != self.owner_subject_id:
                raise ValueError("private asset tenant must equal owner subject")
            if self.asset_kind == "twin_mesh" and not self.twin_id:
                raise ValueError("Twin mesh requires a Twin ID")
            if self.asset_kind in {"catalog_garment", "user_garment"} and not self.product_id:
                raise ValueError("garment asset requires a canonical product ID")
        else:
            if self.asset_kind != "catalog_garment" or not self.product_id or self.owner_subject_id is not None:
                raise ValueError("catalog-visible assets must be ownerless catalog garment assets with a product ID")
        expected_types = MESH_TYPES if self.asset_kind == "twin_mesh" else IMAGE_TYPES
        if self.content_type not in expected_types:
            raise ValueError("content type does not match the registered asset kind")
        return self


class TwinCreate(StrictModel):
    twin_id: str = Field(min_length=3, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    mesh_asset_id: str = Field(min_length=3, max_length=160)
    model_id: str = Field(min_length=2, max_length=160)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    model_release_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_attestation_hmac: str = Field(pattern=r"^[0-9a-f]{64}$")


class TwinOwner(StrictModel):
    twin_id: str = Field(min_length=3, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)


class AssetAuthorization(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    product_id: str = Field(min_length=3, max_length=128)
    person_image_asset_id: str = Field(min_length=3, max_length=160)
    garment_image_asset_id: str = Field(min_length=3, max_length=160)


class AssetRevoke(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    asset_id: str = Field(min_length=3, max_length=160)


def get_db() -> Iterator[Session]:
    url = os.getenv("TWIN_REGISTRY_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_DATABASE_NOT_CONFIGURED"})
    db = _session_factory(url)()
    try:
        yield db
    finally:
        db.close()


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("TWIN_REGISTRY_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _verify_validation_attestation(payload: TwinCreate) -> None:
    secret = os.getenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "TWIN_VALIDATION_ATTESTATION_NOT_CONFIGURED"})
    body = {
        "twin_id": payload.twin_id,
        "subject_id": payload.subject_id,
        "mesh_asset_id": payload.mesh_asset_id,
        "model_id": payload.model_id.strip(),
        "model_revision": payload.model_revision,
        "model_release_sha256": payload.model_release_sha256,
        "validation_report_sha256": payload.validation_report_sha256,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.validation_attestation_hmac):
        raise HTTPException(403, detail={"code": "TWIN_VALIDATION_ATTESTATION_INVALID"})


def verified_subject(value: str) -> str:
    value = value.strip()
    if not SUBJECT_RE.fullmatch(value):
        raise HTTPException(422, detail={"code": "INVALID_SUBJECT_ID"})
    return value


app = FastAPI(
    title="Cirvanna Twin and Asset Registry",
    version="1.0.0",
    description="Internal owner-bound Twin and asset metadata; object bytes remain private to the storage data plane.",
)


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", dependencies=[Depends(require_internal_token)])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(select(TwinRecord.twin_id).limit(1))
        db.execute(select(AssetRecord.asset_id).limit(1))
        if len(os.getenv("TWIN_REGISTRY_VALIDATION_HMAC_SECRET", "").encode("utf-8")) < 32:
            raise HTTPException(503, detail={"code": "TWIN_VALIDATION_ATTESTATION_NOT_CONFIGURED"})
        return {"status": "ready", "service": SERVICE, "database": "reachable", "ready": True}
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_SCHEMA_NOT_READY"}) from exc


@app.post("/internal/v1/assets/register", dependencies=[Depends(require_internal_token)])
def register_asset(payload: AssetRegister, db: Session = Depends(get_db)):
    if payload.owner_subject_id is not None:
        verified_subject(payload.owner_subject_id)
    asset_id = str(uuid.uuid4())
    row = AssetRecord(
        asset_id=asset_id,
        owner_subject_id=payload.owner_subject_id,
        tenant_id=payload.tenant_id.strip(),
        asset_kind=payload.asset_kind,
        access_scope=payload.access_scope,
        twin_id=payload.twin_id,
        product_id=payload.product_id,
        storage_object_key=payload.storage_object_key,
        content_type=payload.content_type,
        byte_size=payload.byte_size,
        sha256=payload.sha256,
        state="active",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "ASSET_STORAGE_OBJECT_ALREADY_REGISTERED"}) from exc
    return {
        "asset_id": row.asset_id,
        "asset_kind": row.asset_kind,
        "state": row.state,
        "owner_subject_id": row.owner_subject_id,
        "tenant_id": row.tenant_id,
        "storage_bytes_persisted_by_registry": False,
    }


@app.post("/internal/v1/twins", dependencies=[Depends(require_internal_token)])
def create_twin(payload: TwinCreate, db: Session = Depends(get_db)):
    subject = verified_subject(payload.subject_id)
    _verify_validation_attestation(payload)
    existing = db.get(TwinRecord, payload.twin_id)
    if existing is not None:
        same = (
            existing.subject_id == subject
            and existing.mesh_asset_id == payload.mesh_asset_id
            and existing.model_revision == payload.model_revision
            and existing.model_release_sha256 == payload.model_release_sha256
            and existing.validation_report_sha256 == payload.validation_report_sha256
        )
        if same and existing.state == "active":
            return {"twin_id": existing.twin_id, "subject_id": subject, "status": "replayed"}
        raise HTTPException(409, detail={"code": "TWIN_ID_IMMUTABLE"})
    mesh = db.get(AssetRecord, payload.mesh_asset_id)
    if not (
        mesh is not None
        and mesh.state == "active"
        and mesh.asset_kind == "twin_mesh"
        and mesh.access_scope == "private"
        and mesh.owner_subject_id == subject
        and mesh.tenant_id == subject
        and mesh.twin_id == payload.twin_id
    ):
        raise HTTPException(403, detail={"code": "TWIN_MESH_OWNERSHIP_REQUIRED"})
    row = TwinRecord(
        twin_id=payload.twin_id,
        subject_id=subject,
        mesh_asset_id=mesh.asset_id,
        model_id=payload.model_id.strip(),
        model_revision=payload.model_revision,
        model_release_sha256=payload.model_release_sha256,
        validation_report_sha256=payload.validation_report_sha256,
        state="active",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "TWIN_CREATE_CONFLICT"}) from exc
    return {"twin_id": row.twin_id, "subject_id": subject, "status": "active", "model_revision": row.model_revision}


@app.post("/internal/v1/twins/authorize", dependencies=[Depends(require_internal_token)])
def authorize_twin(payload: TwinOwner, db: Session = Depends(get_db)):
    subject = verified_subject(payload.subject_id)
    twin = db.get(TwinRecord, payload.twin_id)
    if twin is None or twin.subject_id != subject or twin.state != "active":
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})
    return {"authorized": True, "active": True, "subject_id": subject, "twin_id": twin.twin_id}


@app.post("/internal/v1/twins/revoke", dependencies=[Depends(require_internal_token)])
def revoke_twin(payload: TwinOwner, db: Session = Depends(get_db)):
    subject = verified_subject(payload.subject_id)
    twin = db.get(TwinRecord, payload.twin_id)
    if twin is None or twin.subject_id != subject:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND"})
    if twin.state != "revoked":
        twin.state = "revoked"
        twin.revoked_at = utcnow()
        db.commit()
        db.refresh(twin)
    return {"twin_id": twin.twin_id, "status": "revoked", "revoked_at": twin.revoked_at.isoformat()}


@app.post("/internal/v1/assets/authorize", dependencies=[Depends(require_internal_token)])
def authorize_assets(payload: AssetAuthorization, db: Session = Depends(get_db)):
    subject = verified_subject(payload.subject_id)
    twin = db.get(TwinRecord, payload.twin_id)
    if twin is None or twin.subject_id != subject or twin.state != "active":
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})
    mesh = db.get(AssetRecord, twin.mesh_asset_id)
    person = db.get(AssetRecord, payload.person_image_asset_id)
    garment = db.get(AssetRecord, payload.garment_image_asset_id)
    person_ok = (
        person is not None and person.state == "active" and person.asset_kind == "person_reference"
        and person.access_scope == "private" and person.owner_subject_id == subject
        and person.tenant_id == subject and person.twin_id == twin.twin_id
    )
    garment_ok = (
        garment is not None and garment.state == "active" and garment.product_id == payload.product_id
        and (
            (garment.access_scope == "catalog" and garment.asset_kind == "catalog_garment" and garment.owner_subject_id is None)
            or (garment.access_scope == "private" and garment.asset_kind == "user_garment" and garment.owner_subject_id == subject and garment.tenant_id == subject)
        )
    )
    mesh_ok = (
        mesh is not None and mesh.state == "active" and mesh.asset_kind == "twin_mesh"
        and mesh.owner_subject_id == subject and mesh.twin_id == twin.twin_id
    )
    if not (person_ok and garment_ok and mesh_ok):
        raise HTTPException(403, detail={"code": "ASSET_ACCESS_DENIED"})
    return {
        "authorized": True,
        "active": True,
        "subject_id": subject,
        "twin_id": twin.twin_id,
        "product_id": payload.product_id,
        "person_image_asset_id": person.asset_id,
        "garment_image_asset_id": garment.asset_id,
        "mesh_asset_id": mesh.asset_id,
    }


@app.post("/internal/v1/assets/revoke", dependencies=[Depends(require_internal_token)])
def revoke_asset(payload: AssetRevoke, db: Session = Depends(get_db)):
    subject = verified_subject(payload.subject_id)
    asset = db.get(AssetRecord, payload.asset_id)
    if asset is None or asset.owner_subject_id != subject or asset.access_scope != "private":
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
    if asset.state != "revoked":
        asset.state = "revoked"
        asset.revoked_at = utcnow()
        db.commit()
        db.refresh(asset)
        if asset.asset_kind == "twin_mesh":
            twin = db.scalar(select(TwinRecord).where(TwinRecord.mesh_asset_id == asset.asset_id))
            if twin is not None:
                twin.state = "revoked"
                twin.revoked_at = utcnow()
                db.commit()
    return {"asset_id": asset.asset_id, "status": "revoked", "revoked_at": asset.revoked_at.isoformat() if asset.revoked_at else None}

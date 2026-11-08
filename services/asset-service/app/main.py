from __future__ import annotations

import hashlib
import hmac
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Iterator, Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import DateTime, Index, Integer, String, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-asset-service"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ASSET_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
AssetPurpose = Literal[
    "twin_source_image", "twin_person_image", "twin_representation",
    "catalog_garment_image", "wardrobe_garment_image", "try_on_output",
]
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna Private Asset Service", version="1.0.0")


class Base(DeclarativeBase):
    pass


class AssetRow(Base):
    __tablename__ = "asset_objects"
    __table_args__ = (
        Index("ix_asset_owner_parent_status", "owner_user_id", "parent_id", "status"),
        Index("ix_asset_expiry_status", "retention_until", "status"),
    )
    asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(160), nullable=False)
    object_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@lru_cache(maxsize=4)
def _engine(url: str):
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("ASSET_DATABASE_URL must use PostgreSQL; SQLite is test-only")
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def _sessions(url: str):
    return sessionmaker(bind=_engine(url), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    url = os.getenv("ASSET_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "ASSET_DATABASE_NOT_CONFIGURED"})
    try:
        db = _sessions(url)()
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(503, detail={"code": "ASSET_DATABASE_UNAVAILABLE"}) from exc
    try:
        yield db
    finally:
        db.close()


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("ASSET_SERVICE_TOKEN", "").strip()
    if len(expected.encode()) < 32:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _storage_config() -> tuple[str, str, str, str]:
    bucket = os.getenv("ASSET_S3_BUCKET", "").strip()
    access = os.getenv("ASSET_S3_ACCESS_KEY_ID", "").strip()
    secret = os.getenv("ASSET_S3_SECRET_ACCESS_KEY", "").strip()
    region = os.getenv("ASSET_S3_REGION", "us-east-1").strip()
    endpoint = os.getenv("ASSET_S3_ENDPOINT_URL", "").strip()
    if (
        not bucket or not region or bool(access) != bool(secret)
        or (access and len(secret) < 16)
    ):
        raise HTTPException(503, detail={"code": "ASSET_OBJECT_STORAGE_NOT_CONFIGURED"})
    if endpoint:
        from urllib.parse import urlsplit
        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1", "minio"}
        if not host or parts.username or parts.password or parts.query or parts.fragment:
            raise HTTPException(503, detail={"code": "ASSET_STORAGE_ENDPOINT_INVALID"})
        if parts.scheme != "https" and not (parts.scheme == "http" and local):
            raise HTTPException(503, detail={"code": "ASSET_STORAGE_ENDPOINT_MUST_USE_HTTPS"})
    return bucket, access, secret, endpoint


def _object_store():
    bucket, access, secret, endpoint = _storage_config()
    options = {
        "endpoint_url": endpoint or None,
        "region_name": os.getenv("ASSET_S3_REGION", "us-east-1"),
    }
    # Empty credentials use the cloud SDK's workload/IAM credential chain.
    if access and secret:
        options.update({"aws_access_key_id": access, "aws_secret_access_key": secret})
    return boto3.client("s3", **options), bucket


def _verify_private_bucket(client, bucket: str) -> bool:
    """Require provider-reported controls that prevent anonymous/public bucket reads.

    Reachability alone is not a privacy check. Providers that cannot report these
    controls remain not-ready; CDN/origin and deployment-level checks are separate.
    """
    try:
        access = client.get_public_access_block(Bucket=bucket).get(
            "PublicAccessBlockConfiguration", {}
        )
        if not all(
            access.get(key) is True
            for key in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        ):
            return False

        policy = client.get_bucket_policy_status(Bucket=bucket).get("PolicyStatus", {})
        if policy.get("IsPublic") is not False:
            return False

        encryption = client.get_bucket_encryption(Bucket=bucket).get("ServerSideEncryptionConfiguration", {})
        rules = encryption.get("Rules", [])
        if not rules or not any(
            rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm")
            in {"AES256", "aws:kms", "aws:kms:dsse"}
            for rule in rules
        ):
            return False

        ownership = client.get_bucket_ownership_controls(Bucket=bucket).get(
            "OwnershipControls", {}
        )
        if not any(
            rule.get("ObjectOwnership") == "BucketOwnerEnforced"
            for rule in ownership.get("Rules", [])
        ):
            return False
    except (BotoCoreError, ClientError, KeyError, TypeError, AttributeError, ValueError):
        return False
    return True


def _normalize_image(data: bytes, content_type: str) -> bytes:
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_TYPE"})
    if not data:
        raise HTTPException(400, detail={"code": "EMPTY_IMAGE"})
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_FORMAT"})
            if source.width < 64 or source.height < 64 or source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(422, detail={"code": "IMAGE_DIMENSIONS_INVALID"})
            source.load()
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            out = io.BytesIO()
            normalized.save(out, format="PNG", optimize=True)
            clean = out.getvalue()
            if not clean or len(clean) > MAX_IMAGE_BYTES:
                raise HTTPException(413, detail={"code": "NORMALIZED_IMAGE_SIZE_LIMIT_EXCEEDED"})
            return clean
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "INVALID_IMAGE_DATA"}) from exc


def _owned_asset(db: Session, asset_id: str, owner: str, purpose: str, parent_id: str) -> AssetRow:
    row = db.get(AssetRow, asset_id)
    if (
        row is None or row.status != "active" or row.owner_user_id != owner
        or row.purpose != purpose or row.parent_id != parent_id
        or (row.retention_until is not None and row.retention_until <= datetime.now(timezone.utc))
    ):
        # 404 deliberately prevents cross-tenant and resource-existence probing.
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND_OR_NOT_AUTHORIZED"})
    return row


@app.on_event("startup")
def startup() -> None:
    if os.getenv("ASSET_AUTO_CREATE_SCHEMA", "false").lower() == "true":
        url = os.getenv("ASSET_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("ASSET_DATABASE_URL is required")
        Base.metadata.create_all(bind=_engine(url))


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def ready(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(select(AssetRow.asset_id).limit(1))
        client, bucket = _object_store()
        client.head_bucket(Bucket=bucket)
        if not _verify_private_bucket(client, bucket):
            raise HTTPException(
                503,
                detail={
                    "status": "not_ready",
                    "service": SERVICE,
                    "ready": False,
                    "reason": "private_bucket_controls_unverified",
                },
            )
    except HTTPException:
        raise
    except (BotoCoreError, ClientError, SQLAlchemyError, ValueError) as exc:
        raise HTTPException(503, detail={"status": "not_ready", "service": SERVICE, "ready": False, "reason": "storage_or_database_unavailable"}) from exc
    return {
        "status": "ready",
        "service": SERVICE,
        "database": "reachable",
        "object_storage": "reachable",
        "private_access": "verified",
        "ready": True,
    }


@app.post("/internal/v1/assets", dependencies=[Depends(require_internal_token)], status_code=201)
async def upload_asset(
    owner_user_id: Annotated[str, Form(min_length=3, max_length=128)],
    purpose: Annotated[AssetPurpose, Form()],
    parent_id: Annotated[str, Form(min_length=3, max_length=160)],
    file: Annotated[UploadFile, File()],
    retention_days: Annotated[int | None, Form(ge=1, le=3650)] = None,
    db: Session = Depends(get_db),
):
    owner = owner_user_id.strip()
    parent = parent_id.strip()
    try:
        raw = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    normalized = _normalize_image(raw, file.content_type or "")
    asset_id = str(uuid.uuid4())
    object_key = f"private/{asset_id[:2]}/{asset_id}.png"
    digest = hashlib.sha256(normalized).hexdigest()
    now = datetime.now(timezone.utc)
    retention_until = now + timedelta(days=retention_days) if retention_days else None
    client, bucket = _object_store()
    try:
        client.put_object(
            Bucket=bucket, Key=object_key, Body=normalized,
            ContentType="image/png", Metadata={"sha256": digest, "asset-id": asset_id},
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(503, detail={"code": "ASSET_OBJECT_WRITE_FAILED"}) from exc
    row = AssetRow(
        asset_id=asset_id, owner_user_id=owner, purpose=purpose, parent_id=parent,
        object_key=object_key, content_type="image/png", byte_size=len(normalized),
        sha256=digest, status="active", created_at=now, retention_until=retention_until,
    )
    try:
        db.add(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            client.delete_object(Bucket=bucket, Key=object_key)
        except Exception:
            pass
        raise HTTPException(503, detail={"code": "ASSET_METADATA_WRITE_FAILED"}) from exc
    return {
        "asset_id": asset_id, "owner_user_id": owner, "purpose": purpose,
        "parent_id": parent, "content_type": row.content_type,
        "byte_size": row.byte_size, "sha256": row.sha256,
        "status": row.status, "retention_until": retention_until.isoformat() if retention_until else None,
    }


@app.post("/internal/v1/assets/authorize", dependencies=[Depends(require_internal_token)])
def authorize_asset(
    payload: dict,
    db: Annotated[Session, Depends(get_db)],
):
    owner = payload.get("subject_id")
    purpose = payload.get("purpose")
    if not isinstance(owner, str) or not owner.strip() or not isinstance(purpose, str):
        raise HTTPException(422, detail={"code": "ASSET_AUTHORIZATION_INPUT_INVALID"})

    # Twin registry bulk contract. Asset purpose is checked independently from
    # the consent purpose, and all references must belong to one parent record.
    if "asset_ids" in payload:
        asset_ids = payload.get("asset_ids")
        parent_id = payload.get("parent_id")
        if (
            purpose != "virtual_twin_storage"
            or not isinstance(asset_ids, list) or not asset_ids
            or any(not isinstance(x, str) or not x.strip() for x in asset_ids)
            or len(set(asset_ids)) != len(asset_ids)
            or not isinstance(parent_id, str) or not parent_id.strip()
        ):
            raise HTTPException(422, detail={"code": "ASSET_AUTHORIZATION_INPUT_INVALID"})
        rows = []
        for asset_id in asset_ids:
            row = db.get(AssetRow, asset_id.strip())
            if row is None or row.owner_user_id != owner.strip() or row.status != "active":
                raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
            if row.purpose not in {"twin_source_image", "twin_person_image", "twin_representation"}:
                raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
            if row.parent_id != parent_id.strip():
                raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
            row = _owned_asset(db, row.asset_id, owner.strip(), row.purpose, row.parent_id)
            rows.append(row)
        parents = {row.parent_id for row in rows}
        if len(parents) != 1:
            raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
        return {
            "authorized": True, "subject_id": owner.strip(),
            "authorized_asset_ids": sorted(row.asset_id for row in rows),
            "parent_id": next(iter(parents)), "purpose": purpose,
        }

    asset_id = payload.get("asset_id")
    parent_id = payload.get("parent_id")
    if not all(isinstance(x, str) and x.strip() for x in (asset_id, parent_id)):
        raise HTTPException(422, detail={"code": "ASSET_AUTHORIZATION_INPUT_INVALID"})
    row = _owned_asset(db, asset_id.strip(), owner.strip(), purpose.strip(), parent_id.strip())
    return {
        "authorized": True, "active": True, "subject_id": owner.strip(),
        "asset_id": row.asset_id, "purpose": row.purpose, "parent_id": row.parent_id,
        "content_type": row.content_type, "byte_size": row.byte_size, "sha256": row.sha256,
    }


@app.get("/internal/v1/assets/{asset_id}/content", dependencies=[Depends(require_internal_token)])
def read_asset_content(
    asset_id: str,
    subject_id: str,
    purpose: str,
    parent_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    row = _owned_asset(db, asset_id, subject_id, purpose, parent_id)
    client, bucket = _object_store()
    try:
        response = client.get_object(Bucket=bucket, Key=row.object_key)
        data = response["Body"].read(MAX_IMAGE_BYTES + 1)
    except (BotoCoreError, ClientError, KeyError) as exc:
        raise HTTPException(503, detail={"code": "ASSET_OBJECT_READ_FAILED"}) from exc
    if not data or len(data) > MAX_IMAGE_BYTES or hashlib.sha256(data).hexdigest() != row.sha256:
        raise HTTPException(502, detail={"code": "ASSET_OBJECT_INTEGRITY_FAILED"})
    return Response(content=data, media_type=row.content_type, headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})


@app.delete("/v1/assets/{asset_id}", dependencies=[Depends(require_internal_token)], status_code=204)
def delete_asset(
    asset_id: str,
    owner_user_id: Annotated[str, Header(alias="X-Asset-Owner-ID", min_length=3, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    db: Annotated[Session, Depends(get_db)],
):
    row = db.get(AssetRow, asset_id)
    if row is None or row.owner_user_id != owner_user_id.strip():
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
    if row.status == "deleted":
        return Response(status_code=204)
    client, bucket = _object_store()
    try:
        client.delete_object(Bucket=bucket, Key=row.object_key)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(503, detail={"code": "ASSET_OBJECT_DELETE_FAILED"}) from exc
    row.status = "deleted"
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@app.post("/internal/v1/assets/delete", dependencies=[Depends(require_internal_token)])
def delete_assets(
    payload: dict,
    db: Annotated[Session, Depends(get_db)],
):
    """Idempotently delete all Twin and derived assets for one owner-scoped parent."""
    owner = payload.get("subject_id")
    asset_ids = payload.get("asset_ids")
    purpose = payload.get("purpose")
    cascade = payload.get("cascade_derived_assets")
    idempotency_key = payload.get("idempotency_key")
    parent_id = payload.get("parent_id")
    if (
        not isinstance(owner, str) or not owner.strip()
        or not isinstance(asset_ids, list) or not asset_ids
        or any(not isinstance(x, str) or not x.strip() for x in asset_ids)
        or len(set(asset_ids)) != len(asset_ids)
        or purpose != "virtual_twin_deletion" or cascade is not True
        or not isinstance(parent_id, str) or not parent_id.strip()
        or not isinstance(idempotency_key, str) or len(idempotency_key.strip()) < 8
    ):
        raise HTTPException(422, detail={"code": "ASSET_DELETION_INPUT_INVALID"})
    requested = sorted(x.strip() for x in asset_ids)
    rows = list(db.scalars(select(AssetRow).where(AssetRow.asset_id.in_(requested))).all())
    if len(rows) != len(requested) or any(row.owner_user_id != owner.strip() for row in rows):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
    parents = {row.parent_id for row in rows}
    if len(parents) != 1 or next(iter(parents)) != parent_id.strip():
        raise HTTPException(404, detail={"code": "ASSET_PARENT_MISMATCH"})
    parent_id = parent_id.strip()
    parent_rows = list(db.scalars(select(AssetRow).where(
        AssetRow.owner_user_id == owner.strip(), AssetRow.parent_id == parent_id,
    )).all())
    allowed_purposes = {
        "twin_source_image", "twin_person_image", "twin_representation", "try_on_output",
    }
    if any(row.purpose not in allowed_purposes for row in parent_rows):
        raise HTTPException(409, detail={"code": "ASSET_PARENT_CONTAINS_UNRELATED_PURPOSE"})
    client, bucket = _object_store()
    now = datetime.now(timezone.utc)
    deleted_ids: list[str] = []
    failed_ids: list[str] = []
    for row in parent_rows:
        if row.status == "deleted":
            deleted_ids.append(row.asset_id)
            continue
        if row.status != "active":
            failed_ids.append(row.asset_id)
            continue
        try:
            client.delete_object(Bucket=bucket, Key=row.object_key)
        except (BotoCoreError, ClientError):
            failed_ids.append(row.asset_id)
            continue
        row.status = "deleted"
        row.deleted_at = now
        deleted_ids.append(row.asset_id)
    db.commit()
    if failed_ids or not set(requested).issubset(set(deleted_ids)):
        raise HTTPException(503, detail={
            "code": "ASSET_PARENT_DELETE_INCOMPLETE",
            "deleted_asset_ids": sorted(deleted_ids),
            "failed_asset_ids": sorted(failed_ids),
        })
    return {
        "deleted": True, "subject_id": owner.strip(),
        "deleted_asset_ids": sorted(deleted_ids),
        "idempotency_key": idempotency_key.strip(),
    }


@app.delete("/internal/v1/assets/by-parent/{parent_id}", dependencies=[Depends(require_internal_token)])
def delete_parent_assets(
    parent_id: str,
    owner_user_id: Annotated[str, Query(min_length=3, max_length=128)],
    db: Annotated[Session, Depends(get_db)],
):
    """Remove every asset attached to one owner's Twin/wardrobe parent record."""
    rows = list(db.scalars(select(AssetRow).where(
        AssetRow.owner_user_id == owner_user_id.strip(),
        AssetRow.parent_id == parent_id,
        AssetRow.status == "active",
    )).all())
    if not rows:
        return {"status": "deleted", "deleted_count": 0}
    client, bucket = _object_store()
    now = datetime.now(timezone.utc)
    deleted = 0
    for row in rows:
        try:
            client.delete_object(Bucket=bucket, Key=row.object_key)
        except (BotoCoreError, ClientError):
            continue
        row.status = "deleted"
        row.deleted_at = now
        deleted += 1
    db.commit()
    if deleted != len(rows):
        raise HTTPException(503, detail={"code": "ASSET_PARENT_DELETE_INCOMPLETE", "deleted_count": deleted})
    return {"status": "deleted", "deleted_count": deleted}


@app.post("/internal/v1/assets/purge-expired", dependencies=[Depends(require_internal_token)])
def purge_expired_assets(
    cron_token: Annotated[str, Header(alias="X-Asset-Cron-Token", min_length=32)],
    db: Annotated[Session, Depends(get_db)],
):
    """Physically delete expired short-lived assets; caller is a dedicated cron identity."""
    expected = os.getenv("ASSET_CRON_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32 or not hmac.compare_digest(cron_token, expected):
        raise HTTPException(401, detail={"code": "ASSET_CRON_AUTH_REQUIRED"})
    now = datetime.now(timezone.utc)
    rows = list(db.scalars(select(AssetRow).where(
        AssetRow.status == "active", AssetRow.retention_until.is_not(None)
    ).order_by(AssetRow.retention_until).limit(1000)).all())
    expired = []
    for row in rows:
        expiry = row.retention_until
        if expiry is not None:
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                expired.append(row)
    if not expired:
        return {"status": "complete", "purged_count": 0, "failed_count": 0}
    client, bucket = _object_store()
    purged = 0
    failed = 0
    for row in expired:
        try:
            client.delete_object(Bucket=bucket, Key=row.object_key)
            row.status = "deleted"
            row.deleted_at = now
            purged += 1
        except (BotoCoreError, ClientError):
            failed += 1
    db.commit()
    return {"status": "complete" if failed == 0 else "partial", "purged_count": purged, "failed_count": failed}

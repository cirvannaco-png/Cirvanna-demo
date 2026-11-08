from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class TryOnJobRow(Base):
    __tablename__ = "virtual_try_on_jobs"
    subject_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    twin_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    person_image_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    garment_image_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    garment_asset_purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    garment_asset_parent_id: Mapped[str] = mapped_column(String(160), nullable=False)
    garment_category: Mapped[str] = mapped_column(String(32), nullable=False)
    look_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    look_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wardrobe_snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    renderer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    renderer_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


def engine_for_url(url: str):
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("VIRTUAL_TRY_ON_DATABASE_URL must use PostgreSQL; SQLite is test-only")
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def engine(url: str):
    return engine_for_url(url)


@lru_cache(maxsize=4)
def session_factory(url: str):
    return sessionmaker(bind=engine(url), autoflush=False, expire_on_commit=False)


def _serialize(row: TryOnJobRow) -> dict[str, Any]:
    return {
        "request_id": row.request_id, "subject_id": row.subject_id,
        "twin_id": row.twin_id, "product_id": row.product_id,
        "person_image_asset_id": row.person_image_asset_id,
        "garment_image_asset_id": row.garment_image_asset_id,
        "garment_asset_purpose": row.garment_asset_purpose,
        "garment_asset_parent_id": row.garment_asset_parent_id,
        "garment_category": row.garment_category,
        "look_id": row.look_id, "look_version": row.look_version,
        "wardrobe_snapshot_version": row.wardrobe_snapshot_version,
        "output_asset_id": row.output_asset_id, "renderer_id": row.renderer_id,
        "renderer_version": row.renderer_version, "consent_id": row.consent_id,
        "consent_version": row.consent_version, "status": row.status,
        "created_at": row.created_at.isoformat(),
        "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
        "result": row.result, "payload_hash": row.payload_hash,
    }


class TryOnStore:
    """Persistent request reservation prevents duplicate concurrent GPU renders."""

    def __init__(self, database_url: str):
        self.sessions = session_factory(database_url)

    def ready(self) -> bool:
        with self.sessions() as db:
            db.execute(select(TryOnJobRow.request_id).limit(1))
        return True

    def get(self, subject_id: str, request_id: str) -> dict[str, Any] | None:
        with self.sessions() as db:
            row = db.get(TryOnJobRow, (subject_id, request_id))
            return _serialize(row) if row is not None else None

    def reserve(self, data: dict[str, Any], lease_seconds: int = 600) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)
        key = (data["subject_id"], data["request_id"])
        with self.sessions() as db:
            existing = db.get(TryOnJobRow, key, with_for_update=True)
            if existing is not None:
                if existing.payload_hash != data["payload_hash"]:
                    raise ValueError("idempotency key reused with a different payload")
                if existing.status == "complete":
                    return {"acquired": False, "job": _serialize(existing)}
                expiry = existing.lease_expires_at
                if expiry is not None and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if existing.status == "processing" and expiry is not None and expiry > now:
                    return {"acquired": False, "job": _serialize(existing)}
                if existing.status == "deleted":
                    raise ValueError("deleted try-on jobs cannot be replayed")
                existing.status = "processing"
                existing.lease_expires_at = lease_until
                existing.updated_at = now
                db.commit()
                return {"acquired": True, "job": _serialize(existing)}
            row = TryOnJobRow(
                **data, status="processing", created_at=now, updated_at=now,
                lease_expires_at=lease_until, output_asset_id=None,
                renderer_id=None, renderer_version=None, result=None,
            )
            db.add(row)
            try:
                db.commit()
                return {"acquired": True, "job": _serialize(row)}
            except IntegrityError:
                db.rollback()
                winner = db.get(TryOnJobRow, key)
                if winner is None:
                    raise
                if winner.payload_hash != data["payload_hash"]:
                    raise ValueError("idempotency key reused with a different payload")
                return {"acquired": False, "job": _serialize(winner)}

    def complete(self, subject_id: str, request_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.sessions() as db:
            row = db.get(TryOnJobRow, (subject_id, request_id), with_for_update=True)
            if row is None or row.status != "processing":
                raise ValueError("try-on reservation is not active")
            row.output_asset_id = data["output_asset_id"]
            row.renderer_id = data["renderer_id"]
            row.renderer_version = data["renderer_version"]
            row.updated_at = datetime.now(timezone.utc)
            row.lease_expires_at = None
            row.result = data["result"]
            row.status = "complete"
            db.commit()
            return _serialize(row)

    def fail(self, subject_id: str, request_id: str) -> None:
        with self.sessions() as db:
            row = db.get(TryOnJobRow, (subject_id, request_id), with_for_update=True)
            if row is not None and row.status == "processing":
                row.status = "failed"
                row.lease_expires_at = None
                row.updated_at = datetime.now(timezone.utc)
                db.commit()


def get_store() -> TryOnStore:
    import os
    url = os.getenv("VIRTUAL_TRY_ON_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("VIRTUAL_TRY_ON_DATABASE_URL is not configured")
    return TryOnStore(url)

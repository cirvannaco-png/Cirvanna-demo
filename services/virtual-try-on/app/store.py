from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, create_engine, select
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
    look_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    look_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wardrobe_snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    renderer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(160), nullable=False)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


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


class TryOnStore:
    def __init__(self, database_url: str):
        self.sessions = session_factory(database_url)

    def ready(self) -> bool:
        with self.sessions() as db:
            db.execute(select(TryOnJobRow.request_id).limit(1))
        return True

    def get(self, subject_id: str, request_id: str) -> dict[str, Any] | None:
        with self.sessions() as db:
            row = db.get(TryOnJobRow, (subject_id, request_id))
            if row is None:
                return None
            return {
                "request_id": row.request_id, "subject_id": row.subject_id,
                "twin_id": row.twin_id, "product_id": row.product_id,
                "look_id": row.look_id, "look_version": row.look_version,
                "wardrobe_snapshot_version": row.wardrobe_snapshot_version,
                "output_asset_id": row.output_asset_id, "renderer_id": row.renderer_id,
                "renderer_version": row.renderer_version, "consent_id": row.consent_id,
                "consent_version": row.consent_version, "status": row.status,
                "created_at": row.created_at.isoformat(), "result": row.result,
                "payload_hash": row.payload_hash,
            }

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.sessions() as db, db.begin():
            db.add(TryOnJobRow(**data))
            db.flush()
        return self.get(data["subject_id"], data["request_id"])


def get_store() -> TryOnStore:
    import os
    url = os.getenv("VIRTUAL_TRY_ON_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("VIRTUAL_TRY_ON_DATABASE_URL is not configured")
    return TryOnStore(url)

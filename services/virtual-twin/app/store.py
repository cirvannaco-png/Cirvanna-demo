from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class TwinRow(Base):
    __tablename__ = "virtual_twin_records"
    __table_args__ = (
        Index("ix_virtual_twin_subject_status", "subject_id", "status"),
    )
    twin_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    representation_type: Mapped[str] = mapped_column(String(48), nullable=False)
    representation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    representation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def engine_for_url(url: str):
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("VIRTUAL_TWIN_DATABASE_URL must use PostgreSQL; SQLite is test-only")
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


class TwinStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.sessions = session_factory(database_url)

    def ready(self) -> bool:
        with self.sessions() as db:
            db.execute(select(TwinRow.twin_id).limit(1))
        return True

    @staticmethod
    def serialize(row: TwinRow) -> dict[str, Any]:
        return {
            "twin_id": row.twin_id,
            "subject_id": row.subject_id,
            "representation_type": row.representation_type,
            "representation_version": row.representation_version,
            "representation": row.representation,
            "source_asset_id": row.source_asset_id,
            "consent_id": row.consent_id,
            "consent_version": row.consent_version,
            "model_version": row.model_version,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def create(
        self, *, twin_id: str, subject_id: str, representation: dict[str, Any],
        source_asset_id: str, consent_id: str, consent_version: str, model_version: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        row = TwinRow(
            twin_id=twin_id, subject_id=subject_id,
            representation_type="pose_skeleton_3d",
            representation_version=1, representation=representation,
            source_asset_id=source_asset_id, consent_id=consent_id,
            consent_version=consent_version, model_version=model_version,
            status="active", created_at=now, updated_at=now,
        )
        try:
            with self.sessions() as db, db.begin():
                db.add(row)
                db.flush()
                result = self.serialize(row)
            return result
        except IntegrityError as exc:
            raise ValueError("twin_id already exists") from exc

    def get(self, *, subject_id: str, twin_id: str, include_deleted: bool = False) -> dict[str, Any]:
        with self.sessions() as db:
            row = db.scalar(select(TwinRow).where(
                TwinRow.subject_id == subject_id,
                TwinRow.twin_id == twin_id,
            ))
            if row is None or (row.status != "active" and not include_deleted):
                raise LookupError("twin not found")
            return self.serialize(row)

    def list(self, *, subject_id: str) -> list[dict[str, Any]]:
        """List only the requesting owner's Twin metadata, newest first."""
        with self.sessions() as db:
            rows = db.scalars(select(TwinRow).where(
                TwinRow.subject_id == subject_id,
                TwinRow.status.in_(["active", "deleting"]),
            ).order_by(TwinRow.created_at.desc())).all()
            return [self.serialize(row) for row in rows]

    def begin_delete(self, *, subject_id: str, twin_id: str) -> dict[str, Any]:
        """Hide the record before asset cleanup; failures remain retryable."""
        with self.sessions() as db, db.begin():
            row = db.scalar(select(TwinRow).where(
                TwinRow.subject_id == subject_id, TwinRow.twin_id == twin_id
            ).with_for_update())
            if row is None:
                raise LookupError("twin not found")
            if row.status == "active":
                row.status = "deleting"
                row.updated_at = datetime.now(timezone.utc)
            return {"twin_id": row.twin_id, "source_asset_id": row.source_asset_id, "status": row.status}

    def complete_delete(self, *, subject_id: str, twin_id: str) -> dict[str, Any]:
        with self.sessions() as db, db.begin():
            row = db.scalar(select(TwinRow).where(
                TwinRow.subject_id == subject_id, TwinRow.twin_id == twin_id
            ).with_for_update())
            if row is None:
                raise LookupError("twin not found")
            if row.status == "active":
                raise ValueError("Twin deletion has not started")
            if row.status == "deleting":
                row.status = "deleted"
                row.deleted_at = datetime.now(timezone.utc)
                row.updated_at = row.deleted_at
            return {"twin_id": row.twin_id, "source_asset_id": row.source_asset_id, "status": row.status}

    def delete(self, *, subject_id: str, twin_id: str) -> dict[str, Any]:
        pending = self.begin_delete(subject_id=subject_id, twin_id=twin_id)
        if pending["status"] == "deleting":
            return self.complete_delete(subject_id=subject_id, twin_id=twin_id)
        return pending


def get_store() -> TwinStore:
    url = os.getenv("VIRTUAL_TWIN_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("VIRTUAL_TWIN_DATABASE_URL is not configured")
    return TwinStore(url)

"""Durable, owner-scoped appearance look-session records."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import (
    Boolean, DateTime, ForeignKeyConstraint, Index, Integer, JSON, String,
    UniqueConstraint, create_engine, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class AppearanceLookRow(Base):
    __tablename__ = "appearance_look_sessions"
    __table_args__ = (
        Index("ix_appearance_look_subject_status", "subject_id", "status"),
        UniqueConstraint("subject_id", "look_id", name="uq_appearance_subject_look"),
    )

    look_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    base: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    operations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppearanceLookVersionRow(Base):
    __tablename__ = "appearance_look_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["look_id"], ["appearance_look_sessions.look_id"],
            name="fk_appearance_look_version_session",
        ),
        UniqueConstraint("subject_id", "command_id", name="uq_appearance_subject_command"),
        Index("ix_appearance_look_version", "look_id", "version"),
    )

    look_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    base_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    operations_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    output_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    renderer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    renderer_version: Mapped[str | None] = mapped_column(String(180), nullable=True)
    fidelity_assessment: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def engine_for_url(url: str):
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("APPEARANCE_DATABASE_URL must use PostgreSQL; SQLite is test-only")
    options: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **options)


@lru_cache(maxsize=4)
def engine(url: str):
    return engine_for_url(url)


@lru_cache(maxsize=4)
def session_factory(url: str):
    return sessionmaker(bind=engine(url), autoflush=False, autocommit=False, expire_on_commit=False)


def open_session(url: str) -> Session:
    return session_factory(url)()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def find_command(db: Session, subject_id: str, command_id: str):
    return db.scalar(select(AppearanceLookVersionRow).where(
        AppearanceLookVersionRow.subject_id == subject_id,
        AppearanceLookVersionRow.command_id == command_id,
    ))


def get_look(db: Session, subject_id: str, look_id: str, *, lock: bool = False):
    statement = select(AppearanceLookRow).where(
        AppearanceLookRow.subject_id == subject_id,
        AppearanceLookRow.look_id == look_id,
        AppearanceLookRow.status == "active",
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def get_version(db: Session, subject_id: str, look_id: str, version: int):
    return db.scalar(select(AppearanceLookVersionRow).where(
        AppearanceLookVersionRow.subject_id == subject_id,
        AppearanceLookVersionRow.look_id == look_id,
        AppearanceLookVersionRow.version == version,
    ))

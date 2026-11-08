"""Durable, owner-scoped skincare routine and expiring-share persistence."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime, ForeignKeyConstraint, Index, Integer, JSON, String,
    UniqueConstraint, create_engine, func, select, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class RoutineRow(Base):
    __tablename__ = "skincare_routines"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "routine_id", name="uq_skincare_routine_owner_id"),
        Index("ix_skincare_routines_owner_status_updated", "owner_user_id", "status", "updated_at"),
    )

    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    routine_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    morning_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evening_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class RoutineShareRow(Base):
    __tablename__ = "skincare_routine_shares"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_skincare_routine_share_token_hash"),
        ForeignKeyConstraint(
            ["owner_user_id", "routine_id"],
            ["skincare_routines.owner_user_id", "skincare_routines.routine_id"],
            ondelete="CASCADE",
            name="fk_skincare_routine_share_routine",
        ),
        Index("ix_skincare_routine_shares_owner_routine", "owner_user_id", "routine_id", "revoked_at"),
        Index("ix_skincare_routine_shares_expiry", "expires_at"),
    )

    share_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    routine_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())


class RoutineNotFound(Exception):
    pass


class RoutineConflict(Exception):
    pass


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def engine_for_url(url: str) -> Engine:
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("SKINCARE_ROUTINE_DATABASE_URL must use postgresql+psycopg://; SQLite is test-only")
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


class RoutineStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _active(row: RoutineRow | None) -> RoutineRow:
        if row is None or row.status != "active":
            raise RoutineNotFound("routine not found")
        return row

    def create(
        self, *, owner_user_id: str, routine_id: str, name: str, description: str | None,
        morning_steps: list[dict[str, Any]], evening_steps: list[dict[str, Any]],
    ) -> RoutineRow:
        row = RoutineRow(
            owner_user_id=owner_user_id, routine_id=routine_id, name=name,
            description=description, morning_steps=morning_steps, evening_steps=evening_steps,
            status="active", version=1,
        )
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                session.add(row)
                session.flush()
        except IntegrityError as exc:
            raise RoutineConflict("routine already exists for this owner") from exc
        return row

    def list(self, owner_user_id: str) -> tuple[RoutineRow, ...]:
        with Session(self.engine, expire_on_commit=False) as session:
            rows = session.scalars(
                select(RoutineRow)
                .where(RoutineRow.owner_user_id == owner_user_id, RoutineRow.status == "active")
                .order_by(RoutineRow.updated_at.desc(), RoutineRow.routine_id)
            ).all()
            return tuple(rows)

    def get(self, owner_user_id: str, routine_id: str) -> RoutineRow:
        with Session(self.engine, expire_on_commit=False) as session:
            row = session.scalar(select(RoutineRow).where(
                RoutineRow.owner_user_id == owner_user_id,
                RoutineRow.routine_id == routine_id,
            ))
            return self._active(row)

    def update(
        self, *, owner_user_id: str, routine_id: str, expected_version: int,
        name: str, description: str | None, morning_steps: list[dict[str, Any]],
        evening_steps: list[dict[str, Any]],
    ) -> RoutineRow:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = session.scalar(select(RoutineRow).where(
                RoutineRow.owner_user_id == owner_user_id,
                RoutineRow.routine_id == routine_id,
            ).with_for_update())
            self._active(row)
            assert row is not None
            if row.version != expected_version:
                raise RoutineConflict("stale routine version; reload before saving")
            row.name = name
            row.description = description
            row.morning_steps = morning_steps
            row.evening_steps = evening_steps
            row.version += 1
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return row

    def delete(self, *, owner_user_id: str, routine_id: str, expected_version: int) -> None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = session.scalar(select(RoutineRow).where(
                RoutineRow.owner_user_id == owner_user_id,
                RoutineRow.routine_id == routine_id,
            ).with_for_update())
            self._active(row)
            assert row is not None
            if row.version != expected_version:
                raise RoutineConflict("stale routine version; reload before deleting")
            session.execute(update(RoutineShareRow).where(
                RoutineShareRow.owner_user_id == owner_user_id,
                RoutineShareRow.routine_id == routine_id,
                RoutineShareRow.revoked_at.is_(None),
            ).values(revoked_at=func.current_timestamp()))
            session.delete(row)

    def create_share(
        self, *, owner_user_id: str, routine_id: str, token: str,
        expires_at: datetime,
    ) -> datetime:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = session.scalar(select(RoutineRow).where(
                RoutineRow.owner_user_id == owner_user_id,
                RoutineRow.routine_id == routine_id,
            ).with_for_update())
            self._active(row)
            session.execute(update(RoutineShareRow).where(
                RoutineShareRow.owner_user_id == owner_user_id,
                RoutineShareRow.routine_id == routine_id,
                RoutineShareRow.revoked_at.is_(None),
            ).values(revoked_at=func.current_timestamp()))
            session.add(RoutineShareRow(
                owner_user_id=owner_user_id,
                routine_id=routine_id,
                token_hash=token_digest(token),
                expires_at=expires_at,
            ))
            session.flush()
        return expires_at

    def revoke_share(self, *, owner_user_id: str, routine_id: str) -> bool:
        now = datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            row = session.scalar(select(RoutineRow).where(
                RoutineRow.owner_user_id == owner_user_id,
                RoutineRow.routine_id == routine_id,
            ))
            self._active(row)
            result = session.execute(update(RoutineShareRow).where(
                RoutineShareRow.owner_user_id == owner_user_id,
                RoutineShareRow.routine_id == routine_id,
                RoutineShareRow.revoked_at.is_(None),
            ).values(revoked_at=now))
            return bool(result.rowcount)

    def get_shared(self, token: str, *, now: datetime | None = None) -> tuple[RoutineRow, datetime] | None:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session:
            result = session.execute(
                select(RoutineRow, RoutineShareRow.expires_at)
                .join(
                    RoutineShareRow,
                    (RoutineShareRow.owner_user_id == RoutineRow.owner_user_id)
                    & (RoutineShareRow.routine_id == RoutineRow.routine_id),
                )
                .where(
                    RoutineShareRow.token_hash == token_digest(token),
                    RoutineShareRow.revoked_at.is_(None),
                    RoutineShareRow.expires_at > now,
                    RoutineRow.status == "active",
                )
            ).first()
            if result is None:
                return None
            return result[0], result[1]

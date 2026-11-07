"""SQLAlchemy-backed NPL ledger. PostgreSQL is the production target."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import hmac
import os
import uuid
from functools import lru_cache
from typing import Any
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from npl.core import NegativePreference, PreferenceSource, TargetType, evaluate as evaluate_npl, record_rejection, retract_preference

class Base(DeclarativeBase):
    pass

class PreferenceRow(Base):
    __tablename__ = "npl_preferences"
    __table_args__ = (
        CheckConstraint("target_type IN ('item', 'attribute')", name="ck_npl_target_type"),
        CheckConstraint("source IN ('user_declared', 'learned_rejection')", name="ck_npl_source"),
        CheckConstraint("rejection_threshold >= 1", name="ck_npl_rejection_threshold"),
        Index("ix_npl_preferences_user_active", "user_id", "active"),
    )
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    preference_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_value: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    correction_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class RejectionEventRow(Base):
    __tablename__ = "npl_rejection_events"
    __table_args__ = (
        UniqueConstraint("user_id", "rejection_event_id", name="uq_npl_rejection_user_event"),
        ForeignKeyConstraint(["user_id", "preference_id"], ["npl_preferences.user_id", "npl_preferences.preference_id"], ondelete="CASCADE", name="fk_npl_rejection_preference"),
        Index("ix_npl_rejection_preference", "user_id", "preference_id"),
    )
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    preference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rejection_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

class CorrectionEventRow(Base):
    __tablename__ = "npl_correction_events"
    __table_args__ = (
        UniqueConstraint("user_id", "correction_event_id", name="uq_npl_correction_user_event"),
        ForeignKeyConstraint(["user_id", "preference_id"], ["npl_preferences.user_id", "npl_preferences.preference_id"], ondelete="CASCADE", name="fk_npl_correction_preference"),
        Index("ix_npl_correction_preference", "user_id", "preference_id"),
    )
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    preference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correction_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

class NPLDeletionReceiptRow(Base):
    __tablename__ = "npl_deletion_receipts"
    receipt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deleted_preference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_rejection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_correction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

class PreferenceNotFound(Exception):
    pass

class PreferenceConflict(Exception):
    pass

class NPLStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_preference(self, *, user_id: str, preference_id: str, target_type: TargetType, target_value: str, source: PreferenceSource, rejection_threshold: int = 3) -> NegativePreference:
        value = NegativePreference(preference_id=preference_id, user_id=user_id, target_type=target_type, target_value=target_value, source=source, rejection_event_ids=(), rejection_threshold=rejection_threshold, active=True)
        try:
            with Session(self.engine) as session, session.begin():
                session.add(PreferenceRow(user_id=user_id, preference_id=preference_id, target_type=target_type.value, target_value=target_value, source=source.value, rejection_threshold=rejection_threshold, active=True, correction_event_id=None))
                session.flush()
        except IntegrityError as exc:
            raise PreferenceConflict("preference ID already exists for this user") from exc
        return value

    def _as_domain(self, session: Session, row: PreferenceRow) -> NegativePreference:
        events = session.scalars(select(RejectionEventRow.rejection_event_id).where(RejectionEventRow.user_id == row.user_id, RejectionEventRow.preference_id == row.preference_id).order_by(RejectionEventRow.event_id)).all()
        return NegativePreference(preference_id=row.preference_id, user_id=row.user_id, target_type=TargetType(row.target_type), target_value=row.target_value, source=PreferenceSource(row.source), rejection_event_ids=tuple(events), rejection_threshold=row.rejection_threshold, active=row.active, correction_event_id=row.correction_event_id)

    def list_preferences(self, user_id: str) -> tuple[NegativePreference, ...]:
        with Session(self.engine) as session:
            rows = session.scalars(select(PreferenceRow).where(PreferenceRow.user_id == user_id).order_by(PreferenceRow.preference_id)).all()
            return tuple(self._as_domain(session, row) for row in rows)

    def get_preference(self, user_id: str, preference_id: str) -> NegativePreference:
        with Session(self.engine) as session:
            row = session.scalar(select(PreferenceRow).where(PreferenceRow.user_id == user_id, PreferenceRow.preference_id == preference_id))
            if row is None:
                raise PreferenceNotFound("preference not found for this user")
            return self._as_domain(session, row)

    def record_rejection(self, *, user_id: str, preference_id: str, rejection_event_id: str) -> NegativePreference:
        if not rejection_event_id.strip():
            raise ValueError("rejection_event_id must not be empty")
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(select(PreferenceRow).where(PreferenceRow.user_id == user_id, PreferenceRow.preference_id == preference_id).with_for_update())
                if row is None:
                    raise PreferenceNotFound("preference not found for this user")
                current = self._as_domain(session, row)
                updated = record_rejection(current, rejection_event_id)
                if updated is current:
                    return current
                session.add(RejectionEventRow(user_id=user_id, preference_id=preference_id, rejection_event_id=rejection_event_id))
                session.flush()
                row.updated_at = datetime.now(timezone.utc)
                return self._as_domain(session, row)
        except IntegrityError as exc:
            with Session(self.engine) as session:
                existing = session.scalar(select(RejectionEventRow).where(RejectionEventRow.user_id == user_id, RejectionEventRow.rejection_event_id == rejection_event_id))
                if existing is not None and existing.preference_id == preference_id:
                    row = session.scalar(select(PreferenceRow).where(PreferenceRow.user_id == user_id, PreferenceRow.preference_id == preference_id))
                    if row is not None:
                        return self._as_domain(session, row)
            raise PreferenceConflict("rejection event ID was already used by a different preference") from exc

    def retract_preference(self, *, user_id: str, preference_id: str, correction_event_id: str) -> NegativePreference:
        if not correction_event_id.strip():
            raise ValueError("correction_event_id must not be empty")
        try:
            with Session(self.engine) as session, session.begin():
                row = session.scalar(select(PreferenceRow).where(PreferenceRow.user_id == user_id, PreferenceRow.preference_id == preference_id).with_for_update())
                if row is None:
                    raise PreferenceNotFound("preference not found for this user")
                current = self._as_domain(session, row)
                updated = retract_preference(current, correction_event_id)
                if updated is current:
                    return current
                session.add(CorrectionEventRow(user_id=user_id, preference_id=preference_id, correction_event_id=correction_event_id))
                row.active = updated.active
                row.correction_event_id = updated.correction_event_id
                row.updated_at = datetime.now(timezone.utc)
                session.flush()
                return self._as_domain(session, row)
        except IntegrityError as exc:
            with Session(self.engine) as session:
                existing = session.scalar(select(CorrectionEventRow).where(CorrectionEventRow.user_id == user_id, CorrectionEventRow.correction_event_id == correction_event_id))
                if existing is not None and existing.preference_id == preference_id:
                    row = session.scalar(select(PreferenceRow).where(PreferenceRow.user_id == user_id, PreferenceRow.preference_id == preference_id))
                    if row is not None and not row.active and row.correction_event_id == correction_event_id:
                        return self._as_domain(session, row)
            raise PreferenceConflict("correction event ID was already used by a different preference") from exc

    def export_user_data(self, user_id: str) -> dict[str, object]:
        """Return complete, user-scoped NPL preferences and their event audit rows."""
        normalized = user_id.strip()
        if not normalized:
            raise ValueError("user_id must not be empty")
        with Session(self.engine) as session:
            preference_rows = session.scalars(
                select(PreferenceRow).where(PreferenceRow.user_id == normalized).order_by(PreferenceRow.preference_id)
            ).all()
            rejection_rows = session.execute(
                select(
                    RejectionEventRow.preference_id,
                    RejectionEventRow.rejection_event_id,
                    RejectionEventRow.occurred_at,
                ).where(RejectionEventRow.user_id == normalized).order_by(RejectionEventRow.occurred_at, RejectionEventRow.event_id)
            ).all()
            correction_rows = session.execute(
                select(
                    CorrectionEventRow.preference_id,
                    CorrectionEventRow.correction_event_id,
                    CorrectionEventRow.occurred_at,
                ).where(CorrectionEventRow.user_id == normalized).order_by(CorrectionEventRow.occurred_at, CorrectionEventRow.event_id)
            ).all()
            return {
                "preferences": tuple(self._as_domain(session, row) for row in preference_rows),
                "rejection_events": [
                    {"preference_id": row.preference_id, "event_id": row.rejection_event_id, "occurred_at": row.occurred_at.isoformat()}
                    for row in rejection_rows
                ],
                "correction_events": [
                    {"preference_id": row.preference_id, "event_id": row.correction_event_id, "occurred_at": row.occurred_at.isoformat()}
                    for row in correction_rows
                ],
            }

    def delete_user_data(self, user_id: str) -> dict[str, object]:
        """Delete every NPL preference and its event rows, retaining only a one-way receipt."""
        normalized = user_id.strip()
        if not normalized:
            raise ValueError("user_id must not be empty")
        receipt_id = str(uuid.uuid4())
        receipt_secret = os.getenv("NPL_EVIDENCE_HMAC_SECRET", "").strip()
        if len(receipt_secret.encode("utf-8")) < 32:
            raise RuntimeError("NPL deletion receipt signing is not configured")
        digest = hmac.new(receipt_secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        with Session(self.engine) as session, session.begin():
            preference_count = session.scalar(
                select(func.count()).select_from(PreferenceRow).where(PreferenceRow.user_id == normalized)
            ) or 0
            rejection_count = session.scalar(
                select(func.count()).select_from(RejectionEventRow).where(RejectionEventRow.user_id == normalized)
            ) or 0
            correction_count = session.scalar(
                select(func.count()).select_from(CorrectionEventRow).where(CorrectionEventRow.user_id == normalized)
            ) or 0
            session.execute(delete(RejectionEventRow).where(RejectionEventRow.user_id == normalized))
            session.execute(delete(CorrectionEventRow).where(CorrectionEventRow.user_id == normalized))
            session.execute(delete(PreferenceRow).where(PreferenceRow.user_id == normalized))
            session.add(NPLDeletionReceiptRow(
                receipt_id=receipt_id,
                subject_digest=digest,
                deleted_preference_count=int(preference_count),
                deleted_rejection_count=int(rejection_count),
                deleted_correction_count=int(correction_count),
            ))
            session.flush()
        return {
            "status": "deleted",
            "deleted_preferences": int(preference_count),
            "deleted_rejection_events": int(rejection_count),
            "deleted_correction_events": int(correction_count),
            "deletion_receipt_id": receipt_id,
        }

    def evaluate(self, *, user_id: str, candidate_id: str, candidate_attributes: tuple[str, ...]):
        preferences = self.list_preferences(user_id)
        return evaluate_npl(user_id, candidate_id, candidate_attributes, preferences), preferences

@lru_cache(maxsize=8)
def engine_for_url(database_url: str) -> Engine:
    if not database_url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("NPL_DATABASE_URL must use postgresql+psycopg://; local SQLite URLs are test-only")
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)

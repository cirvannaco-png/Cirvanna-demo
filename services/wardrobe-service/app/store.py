"""SQLAlchemy wardrobe persistence with user-scoped versions and deletion outbox."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint, create_engine, func, select, or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from wardrobe import WardrobeItem, WardrobeItemStatus, transition_item

class Base(DeclarativeBase):
    pass

class WardrobeRow(Base):
    __tablename__ = "wardrobe_items"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "last_command_id", name="uq_wardrobe_owner_command"),
        Index("ix_wardrobe_owner_status", "owner_user_id", "status"),
        UniqueConstraint("owner_user_id", "commerce_order_item_id", name="uq_wardrobe_owner_commerce_line"),
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    attributes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    catalog_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commerce_order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    commerce_order_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    purchase_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    purchase_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchase_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    purchase_unit_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchase_paid_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_asset_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    image_storage_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_command_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class WardrobePurchaseRefundSnapshotRow(Base):
    """Order-level financial refund snapshot; never asserts physical return or item deletion."""
    __tablename__ = "wardrobe_purchase_refund_snapshots"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_wardrobe_purchase_refund_event"),
        UniqueConstraint("provider_event_id", name="uq_wardrobe_purchase_refund_provider_event"),
        Index("ix_wardrobe_purchase_refund_order", "order_id"),
        CheckConstraint("order_total_minor > 0", name="ck_wardrobe_refund_order_total_positive"),
        CheckConstraint("amount_refunded_minor > 0 AND amount_refunded_minor <= order_total_minor", name="ck_wardrobe_refund_amount_bounds"),
        CheckConstraint("refund_state IN ('partial_refund', 'refunded')", name="ck_wardrobe_refund_state"),
        CheckConstraint("physical_return_confirmed = FALSE", name="ck_wardrobe_refund_not_a_return"),
        CheckConstraint("ownership_effect = 'financial_status_only'", name="ck_wardrobe_refund_financial_only"),
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(180), nullable=False)
    payment_intent_id: Mapped[str] = mapped_column(String(180), nullable=False)
    charge_id: Mapped[str] = mapped_column(String(180), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    order_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_refunded_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    refund_state: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    refunded_at: Mapped[str] = mapped_column(String(64), nullable=False)
    physical_return_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ownership_effect: Mapped[str] = mapped_column(String(32), nullable=False, default="financial_status_only")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class WardrobeOutfitRow(Base):
    """Saved outfit is a user-owned composition of references to active wardrobe items."""
    __tablename__ = "wardrobe_outfits"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "last_command_id", name="uq_wardrobe_outfit_owner_command"),
        Index("ix_wardrobe_outfit_owner_status", "owner_user_id", "status"),
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    outfit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    pieces: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_command_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_command_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class AssetDeletionOutboxRow(Base):
    __tablename__ = "wardrobe_asset_deletion_outbox"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "item_id", "command_id", name="uq_wardrobe_asset_delete_command"),
        ForeignKeyConstraint(
            ["owner_user_id", "item_id"], ["wardrobe_items.owner_user_id", "wardrobe_items.item_id"],
            ondelete="RESTRICT", name="fk_wardrobe_deletion_item",
        ),
        Index("ix_wardrobe_asset_delete_state", "state", "created_at"),
    )
    outbox_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(160), nullable=False)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class WorkerHeartbeatRow(Base):
    __tablename__ = "wardrobe_worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)



class WardrobeOutfitWearEventRow(Base):
    """Consent-gated, immutable snapshot of an outfit the owner says they wore."""
    __tablename__ = "wardrobe_outfit_wear_events"
    __table_args__ = (
        Index("ix_wardrobe_outfit_wear_owner_observed", "owner_user_id", "observed_at"),
        Index("ix_wardrobe_outfit_wear_outfit", "owner_user_id", "outfit_id"),
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    outfit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outfit_version: Mapped[int] = mapped_column(Integer, nullable=False)
    items_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    context: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    consent_receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_result: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())


class WardrobeFeedbackEventRow(Base):
    """Local audit mirror of a user-authorized learning event; source of truth remains USI/TAL and NPL."""
    __tablename__ = "wardrobe_learning_events"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "event_id", name="uq_wardrobe_learning_owner_event"),
        CheckConstraint("signal IN ('like','dislike','avoid','modify','wear')", name="ck_wardrobe_learning_signal"),
        CheckConstraint("delivery_state IN ('delivered','failed')", name="ck_wardrobe_learning_delivery_state"),
        Index("ix_wardrobe_learning_owner_observed", "owner_user_id", "observed_at"),
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_value: Mapped[str | None] = mapped_column(String(180), nullable=True)
    consent_receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class WardrobeNotFound(Exception):
    pass
class WardrobeConflict(Exception):
    pass

class DeletionJob:
    def __init__(self, outbox_id: int, owner_user_id: str, item_id: str, asset_id: str, command_id: str, attempts: int, lease_owner: str):
        self.outbox_id = outbox_id
        self.owner_user_id = owner_user_id
        self.item_id = item_id
        self.asset_id = asset_id
        self.command_id = command_id
        self.attempts = attempts
        self.lease_owner = lease_owner

def _row_to_domain(row: WardrobeRow) -> WardrobeItem:
    return WardrobeItem(
        item_id=row.item_id, owner_user_id=row.owner_user_id,
        display_name=row.display_name, category=row.category,
        attributes=tuple(row.attributes or ()), catalog_product_id=row.catalog_product_id,
        image_asset_id=row.image_asset_id, image_storage_consent=row.image_storage_consent,
        status=WardrobeItemStatus(row.status), version=row.version, last_command_id=row.last_command_id,
        commerce_order_id=row.commerce_order_id, commerce_order_item_id=row.commerce_order_item_id,
        purchase_event_id=row.purchase_event_id, purchase_quantity=row.purchase_quantity,
        purchase_currency=row.purchase_currency, purchase_unit_price_minor=row.purchase_unit_price_minor,
        purchase_paid_at=row.purchase_paid_at,
    )

class WardrobeStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, item: WardrobeItem) -> WardrobeItem:
        row = WardrobeRow(
            owner_user_id=item.owner_user_id, item_id=item.item_id,
            display_name=item.display_name, category=item.category,
            attributes=list(item.attributes), catalog_product_id=item.catalog_product_id,
            image_asset_id=item.image_asset_id, image_storage_consent=item.image_storage_consent,
            status=item.status.value, version=item.version, last_command_id=item.last_command_id,
            commerce_order_id=item.commerce_order_id, commerce_order_item_id=item.commerce_order_item_id,
            purchase_event_id=item.purchase_event_id, purchase_quantity=item.purchase_quantity,
            purchase_currency=item.purchase_currency, purchase_unit_price_minor=item.purchase_unit_price_minor,
            purchase_paid_at=item.purchase_paid_at,
        )
        try:
            with Session(self.engine) as session, session.begin():
                session.add(row)
                session.flush()
        except IntegrityError as exc:
            raise WardrobeConflict("item ID or owner command ID already exists") from exc
        return item

    def get(self, owner_user_id: str, item_id: str) -> WardrobeItem:
        with Session(self.engine) as session:
            row=session.scalar(select(WardrobeRow).where(WardrobeRow.owner_user_id==owner_user_id, WardrobeRow.item_id==item_id))
            if row is None: raise WardrobeNotFound("wardrobe item not found")
            return _row_to_domain(row)

    def list(self, owner_user_id: str, include_archived: bool = True) -> tuple[WardrobeItem, ...]:
        with Session(self.engine) as session:
            query=select(WardrobeRow).where(WardrobeRow.owner_user_id==owner_user_id)
            if not include_archived:
                query=query.where(WardrobeRow.status=="active")
            rows=session.scalars(query.order_by(WardrobeRow.created_at, WardrobeRow.item_id)).all()
            return tuple(_row_to_domain(row) for row in rows)

    def transition(
        self, *, owner_user_id: str, item_id: str, expected_version: int,
        target_status: WardrobeItemStatus, command_id: str,
    ) -> WardrobeItem:
        if expected_version < 1: raise ValueError("expected_version must be positive")
        try:
            with Session(self.engine) as session, session.begin():
                row=session.scalar(select(WardrobeRow).where(
                    WardrobeRow.owner_user_id==owner_user_id, WardrobeRow.item_id==item_id
                ).with_for_update())
                if row is None: raise WardrobeNotFound("wardrobe item not found")
                if row.version != expected_version:
                    if row.last_command_id == command_id and row.status == target_status.value:
                        return _row_to_domain(row)
                    raise WardrobeConflict("stale item version; reload and retry")
                current=_row_to_domain(row)
                updated=transition_item(current, actor_user_id=owner_user_id, target_status=target_status, command_id=command_id)
                row.status=updated.status.value
                row.version=updated.version
                row.last_command_id=updated.last_command_id
                row.updated_at=func.current_timestamp()
                if updated.status is WardrobeItemStatus.DELETED and updated.image_asset_id:
                    session.add(AssetDeletionOutboxRow(
                        owner_user_id=owner_user_id, item_id=item_id, asset_id=updated.image_asset_id,
                        command_id=command_id, state="pending", attempts=0,
                    ))
                session.flush()
                return updated
        except IntegrityError as exc:
            raise WardrobeConflict("command ID already used for another mutation") from exc

def engine_for_url(url: str) -> Engine:
    if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
        raise ValueError("WARDROBE_DATABASE_URL must use postgresql+psycopg://; SQLite is test-only")
    kwargs: dict[str, Any]={"pool_pre_ping":True}
    if url.startswith("sqlite:///"): kwargs["connect_args"]={"check_same_thread":False}
    return create_engine(url, **kwargs)


class WardrobeDeletionQueue:
    """Transactional outbox lease and retry primitives shared by worker and readiness."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def heartbeat(self, worker_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            row = session.get(WorkerHeartbeatRow, worker_id)
            if row is None:
                session.add(WorkerHeartbeatRow(worker_id=worker_id, last_seen_at=now))
            else:
                row.last_seen_at = now

    def has_fresh_heartbeat(self, *, max_age_seconds: int = 90, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max_age_seconds)
        with Session(self.engine) as session:
            rows = session.scalars(select(WorkerHeartbeatRow.last_seen_at)).all()
        for seen in rows:
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if seen >= cutoff:
                return True
        return False

    def claim(self, *, worker_id: str, lease_seconds: int = 60, now: datetime | None = None) -> DeletionJob | None:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            row = session.scalar(
                select(AssetDeletionOutboxRow)
                .where(
                    or_(
                        (AssetDeletionOutboxRow.state == "pending") & (AssetDeletionOutboxRow.available_at <= now),
                        (AssetDeletionOutboxRow.state == "processing") & (AssetDeletionOutboxRow.lease_until < now),
                    )
                )
                .order_by(AssetDeletionOutboxRow.created_at, AssetDeletionOutboxRow.outbox_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.state = "processing"
            row.attempts += 1
            row.lease_owner = worker_id
            row.lease_until = now + timedelta(seconds=lease_seconds)
            row.updated_at = now
            session.flush()
            return DeletionJob(
                row.outbox_id, row.owner_user_id, row.item_id, row.asset_id,
                row.command_id, row.attempts, worker_id,
            )

    def complete(self, job: DeletionJob, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            row = session.scalar(select(AssetDeletionOutboxRow).where(
                AssetDeletionOutboxRow.outbox_id == job.outbox_id,
                AssetDeletionOutboxRow.state == "processing",
                AssetDeletionOutboxRow.lease_owner == job.lease_owner,
            ).with_for_update())
            if row is None:
                return False
            row.state = "completed"
            row.lease_until = None
            row.lease_owner = None
            row.last_error_code = None
            row.updated_at = now
            return True

    def retry(self, job: DeletionJob, *, error_code: str, max_attempts: int = 8, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            row = session.scalar(select(AssetDeletionOutboxRow).where(
                AssetDeletionOutboxRow.outbox_id == job.outbox_id,
                AssetDeletionOutboxRow.state == "processing",
                AssetDeletionOutboxRow.lease_owner == job.lease_owner,
            ).with_for_update())
            if row is None:
                return "lease_lost"
            row.last_error_code = error_code[:80]
            row.lease_until = None
            row.lease_owner = None
            row.updated_at = now
            if row.attempts >= max_attempts:
                row.state = "failed"
                return "failed"
            delay = min(15 * (2 ** max(row.attempts - 1, 0)), 900)
            row.state = "pending"
            row.available_at = now + timedelta(seconds=delay)
            return "retry_scheduled"

"""SQLAlchemy wardrobe persistence with user-scoped versions and deletion outbox."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, UniqueConstraint, create_engine, func, select
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
    )
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    attributes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    catalog_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_asset_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    image_storage_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_command_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class AssetDeletionOutboxRow(Base):
    __tablename__ = "wardrobe_asset_deletion_outbox"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "item_id", "command_id", name="uq_wardrobe_asset_delete_command"),
        Index("ix_wardrobe_asset_delete_state", "state", "created_at"),
    )
    outbox_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(160), nullable=False)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

class WardrobeNotFound(Exception):
    pass
class WardrobeConflict(Exception):
    pass

def _row_to_domain(row: WardrobeRow) -> WardrobeItem:
    return WardrobeItem(
        item_id=row.item_id, owner_user_id=row.owner_user_id,
        display_name=row.display_name, category=row.category,
        attributes=tuple(row.attributes or ()), catalog_product_id=row.catalog_product_id,
        image_asset_id=row.image_asset_id, image_storage_consent=row.image_storage_consent,
        status=WardrobeItemStatus(row.status), version=row.version, last_command_id=row.last_command_id,
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

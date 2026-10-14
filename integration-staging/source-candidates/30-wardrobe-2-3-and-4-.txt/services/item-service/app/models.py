"""SQLAlchemy ORM models + Pydantic request/response schemas."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common.domain import (
    GeometryProfile,
    IngestionMethod,
    PrimaryCategory,
    SurfaceProperties,
    WardrobeObject,
)


class Base(DeclarativeBase):
    pass


class ItemRow(Base):
    """Persistent representation of a WardrobeObject."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ingestion_method: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    bootstrap_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    geometry_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    surface_properties: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    category_constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    wearability_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence_envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    regret_signals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    total_wears: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_wears: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adaptive_slice_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pending_decay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalog_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_worn: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_items_owner_category", "owner_id", "primary_category"),
        Index("ix_items_owner_state", "owner_id", "lifecycle_state"),
    )

    @classmethod
    def from_domain(cls, obj: WardrobeObject) -> "ItemRow":
        return cls(
            id=obj.id,
            owner_id=obj.owner_id,
            ingestion_method=obj.ingestion_method.value,
            primary_category=obj.category_constraints["primary_category"],
            bootstrap_confidence=obj.bootstrap_confidence,
            geometry_profile=obj.geometry_profile.to_dict() if obj.geometry_profile else None,
            surface_properties=obj.surface_properties.to_dict() if obj.surface_properties else None,
            category_constraints=obj.category_constraints,
            wearability_context=obj.wearability_context,
            confidence_envelope=obj.confidence_envelope.to_dict(),
            regret_signals=obj.regret_signals.to_dict(),
            lifecycle_state=obj.lifecycle_state.value,
            total_wears=obj.total_wears,
            successful_wears=obj.successful_wears,
            adaptive_slice_weight=obj.adaptive_slice_weight,
            pending_decay_days=obj.pending_decay_days,
            catalog_metadata=obj._catalog_metadata,
            created_at=obj.created_at,
            updated_at=obj.last_updated,
            last_worn=obj.last_worn,
        )

    def to_domain(self) -> WardrobeObject:
        obj = WardrobeObject.from_dict(
            {
                "id": self.id,
                "owner_id": self.owner_id,
                "created_at": self.created_at.isoformat(),
                "last_updated": self.updated_at.isoformat(),
                "ingestion_method": self.ingestion_method,
                "lifecycle_state": self.lifecycle_state,
                "bootstrap_confidence": self.bootstrap_confidence,
                "geometry_profile": self.geometry_profile,
                "surface_properties": self.surface_properties,
                "category_constraints": self.category_constraints,
                "wearability_context": self.wearability_context,
                "confidence_envelope": self.confidence_envelope,
                "regret_signals": self.regret_signals,
                "usage_history": [],
                "total_wears": self.total_wears,
                "successful_wears": self.successful_wears,
                "adaptive_slice_weight": self.adaptive_slice_weight,
                "pending_decay_days": self.pending_decay_days,
                "catalog_metadata": self.catalog_metadata,
                "last_worn": self.last_worn.isoformat() if self.last_worn else None,
            }
        )
        return obj


class WearEventRow(Base):
    __tablename__ = "wear_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# ────────────────────────────────────────────────────────────────
# Pydantic schemas
# ────────────────────────────────────────────────────────────────

class GeometryData(BaseModel):
    silhouette_class: str
    length_profile: str
    volume_distribution: list[float]
    stretch_behavior: str

    @field_validator("volume_distribution")
    @classmethod
    def _check_volume(cls, v: list[float]) -> list[float]:
        if len(v) != 3 or any(x < 0 or x > 1 for x in v) or abs(sum(v) - 1.0) > 0.01:
            raise ValueError("volume_distribution must be 3 non-negative values summing to 1.0")
        return v


class SurfaceData(BaseModel):
    dominant_color: dict[str, float]
    color_variance: float = Field(ge=0.0, le=1.0)
    texture_class: str
    pattern_density: float = Field(ge=0.0, le=1.0)
    lighting_risk: float = Field(default=0.0, ge=0.0, le=1.0)


class ItemCreate(BaseModel):
    owner_id: str = Field(min_length=1, max_length=64)
    ingestion_method: str
    primary_category: str
    bootstrap_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    geometry_data: GeometryData | None = None
    surface_data: SurfaceData | None = None
    catalog_metadata: dict[str, Any] | None = None

    @field_validator("ingestion_method")
    @classmethod
    def _check_ingestion(cls, v: str) -> str:
        if v not in [m.value for m in IngestionMethod]:
            raise ValueError(f"Invalid ingestion_method: {v}")
        return v

    @field_validator("primary_category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in [c.value for c in PrimaryCategory]:
            raise ValueError(f"Invalid primary_category: {v}")
        return v


class WearRequest(BaseModel):
    accepted: bool
    duration_minutes: float = Field(gt=0, le=1440)
    event_type: str = "wear"
    context_snapshot: dict[str, Any] | None = None


class ItemSummary(BaseModel):
    id: str
    owner_id: str
    primary_category: str
    lifecycle_state: str
    confidence: float
    total_wears: int
    last_worn: dt.datetime | None = None


class ItemListResponse(BaseModel):
    items: list[ItemSummary]
    total: int
    skip: int
    limit: int

"""Owner-scoped, versioned wardrobe exposure state.

Only trusted internal ingress may call these routes. The caller must resolve
owner_user_id from the verified Commerce subject; browser-supplied identity or
rotation state is never authoritative.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, Integer, JSON, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.store import Base, WardrobeRow, engine_for_url

router = APIRouter(tags=["wardrobe rotation"])
bearer = HTTPBearer(auto_error=False)


class WardrobeRotationStateRow(Base):
    __tablename__ = "wardrobe_rotation_states"
    owner_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cycle_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    surfaced_item_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RotationStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=8, max_length=128)
    expected_version: int = Field(ge=0)
    cycle_number: int = Field(ge=1)
    cycle_started_at: str = Field(min_length=19, max_length=64)
    surfaced_item_ids: list[str] = Field(max_length=150)

    @field_validator("owner_user_id")
    @classmethod
    def normalize_owner(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("owner_user_id must not be blank")
        return value

    @field_validator("surfaced_item_ids")
    @classmethod
    def validate_item_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("surfaced item IDs must be non-empty and at most 128 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("surfaced item IDs must be unique")
        return normalized


def _authorize(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    expected = os.getenv("WARDROBE_SERVICE_TOKEN", "")
    if len(expected.encode()) < 32:
        raise HTTPException(503, detail={"code": "WARDROBE_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "WARDROBE_INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _engine():
    url = os.getenv("WARDROBE_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "WARDROBE_DATABASE_NOT_CONFIGURED"})
    try:
        return engine_for_url(url)
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_DATABASE_CONFIGURATION_INVALID"}) from exc


def _json(row: WardrobeRotationStateRow, active_ids: set[str]) -> dict[str, object]:
    # Removed/archived items no longer block cycle completion.
    return {
        "owner_user_id": row.owner_user_id,
        "cycle_number": row.cycle_number,
        "cycle_started_at": row.cycle_started_at.isoformat(),
        "surfaced_item_ids": [item_id for item_id in row.surfaced_item_ids if item_id in active_ids],
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/v1/rotation-state", dependencies=[Depends(_authorize)])
def get_rotation_state(owner_user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    owner = owner_user_id.strip()
    try:
        with Session(_engine()) as session:
            row = session.get(WardrobeRotationStateRow, owner)
            if row is None:
                return {"state": None, "version": 0}
            active_ids = set(session.scalars(select(WardrobeRow.item_id).where(
                WardrobeRow.owner_user_id == owner, WardrobeRow.status == "active"
            )).all())
            return {"state": _json(row, active_ids), "version": row.version}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_ROTATION_STORE_UNAVAILABLE"}) from exc


@router.put("/v1/rotation-state", dependencies=[Depends(_authorize)])
def put_rotation_state(payload: RotationStateWrite) -> dict[str, object]:
    owner = payload.owner_user_id
    fingerprint = hashlib.sha256(json.dumps({
        "cycle_number": payload.cycle_number,
        "cycle_started_at": payload.cycle_started_at,
        "surfaced_item_ids": payload.surfaced_item_ids,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    try:
        cycle_started = datetime.fromisoformat(payload.cycle_started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "ROTATION_TIMESTAMP_INVALID"}) from exc
    if cycle_started.tzinfo is None:
        raise HTTPException(422, detail={"code": "ROTATION_TIMESTAMP_REQUIRES_TIMEZONE"})
    cycle_started = cycle_started.astimezone(timezone.utc)
    engine = _engine()
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session, session.begin():
            row = session.scalar(select(WardrobeRotationStateRow).where(
                WardrobeRotationStateRow.owner_user_id == owner
            ).with_for_update())
            current_version = 0 if row is None else row.version
            if row is not None and row.last_request_id == payload.request_id:
                if row.last_request_hash != fingerprint:
                    raise HTTPException(409, detail={"code": "WARDROBE_ROTATION_IDEMPOTENCY_CONFLICT"})
                active_ids = set(session.scalars(select(WardrobeRow.item_id).where(
                    WardrobeRow.owner_user_id == owner, WardrobeRow.status == "active"
                )).all())
                return {"state": _json(row, active_ids), "version": row.version, "status": "replayed"}
            if current_version != payload.expected_version:
                raise HTTPException(409, detail={
                    "code": "WARDROBE_ROTATION_VERSION_CONFLICT",
                    "current_version": current_version,
                })
            active_ids = set(session.scalars(select(WardrobeRow.item_id).where(
                WardrobeRow.owner_user_id == owner, WardrobeRow.status == "active"
            )).all())
            unknown_ids = sorted(set(payload.surfaced_item_ids) - active_ids)
            if unknown_ids:
                raise HTTPException(422, detail={"code": "ROTATION_ITEMS_NOT_ACTIVE_OR_NOT_OWNED"})
            if row is None:
                row = WardrobeRotationStateRow(
                    owner_user_id=owner, cycle_number=payload.cycle_number,
                    cycle_started_at=cycle_started, surfaced_item_ids=payload.surfaced_item_ids,
                    version=1, last_request_id=payload.request_id,
                    last_request_hash=fingerprint, created_at=now, updated_at=now,
                )
                session.add(row)
            else:
                row.cycle_number = payload.cycle_number
                row.cycle_started_at = cycle_started
                row.surfaced_item_ids = payload.surfaced_item_ids
                row.last_request_id = payload.request_id
                row.last_request_hash = fingerprint
                row.version += 1
                row.updated_at = now
            session.flush()
            return {"state": _json(row, active_ids), "version": row.version, "status": "created" if current_version == 0 else "updated"}
    except HTTPException:
        raise
    except IntegrityError as exc:
        # Two first writes can race before a row exists to lock; force a reload/retry.
        raise HTTPException(409, detail={"code": "WARDROBE_ROTATION_VERSION_CONFLICT", "current_version": 1}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_ROTATION_STORE_UNAVAILABLE"}) from exc


@router.delete("/v1/rotation-state", dependencies=[Depends(_authorize)])
def delete_rotation_state(owner_user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    """Erase the owner's rotation record as part of account-data deletion."""
    from sqlalchemy import delete
    owner = owner_user_id.strip()
    try:
        with Session(_engine()) as session, session.begin():
            session.execute(delete(WardrobeRotationStateRow).where(
                WardrobeRotationStateRow.owner_user_id == owner
            ))
        return {"status": "deleted", "owner_user_id": owner}
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_ROTATION_STORE_UNAVAILABLE"}) from exc

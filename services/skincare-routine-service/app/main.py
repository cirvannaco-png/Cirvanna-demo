"""Owner-scoped AM/PM skincare routine API with revocable public sharing.

This service stores and organizes user-approved steps. It does not infer skin
conditions, generate treatment advice, or authorize product recommendations.
"""
from __future__ import annotations

import hmac
import os
from functools import lru_cache
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.store import (
    RoutineConflict, RoutineNotFound, RoutineStore, engine_for_url,
)

SERVICE = "cirvanna-skincare-routine-service"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Skincare Routine API",
    version="0.1.0",
    description="User-controlled morning and evening routine storage and revocable sharing.",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoutineStep(StrictModel):
    step_id: str = Field(min_length=3, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    product_id: str | None = Field(default=None, max_length=36)
    recommendation_id: str | None = Field(default=None, max_length=128)
    instruction: str | None = Field(default=None, max_length=280)

    @field_validator("step_id", "label", "product_id", "recommendation_id", "instruction", mode="before")
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("label")
    @classmethod
    def require_label(cls, value: str) -> str:
        if not value:
            raise ValueError("label must not be blank")
        return value

    @field_validator("product_id")
    @classmethod
    def validate_product_reference(cls, value: str | None) -> str | None:
        if value:
            try:
                return str(uuid.UUID(value))
            except ValueError as exc:
                raise ValueError("product_id must be a canonical catalog UUID") from exc
        return value


class RoutineFields(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    morning_steps: list[RoutineStep] = Field(default_factory=list, max_length=20)
    evening_steps: list[RoutineStep] = Field(default_factory=list, max_length=20)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_steps(self) -> "RoutineFields":
        if not self.name:
            raise ValueError("name must not be blank")
        if not self.morning_steps and not self.evening_steps:
            raise ValueError("at least one morning or evening step is required")
        for period, steps in (("morning", self.morning_steps), ("evening", self.evening_steps)):
            ids = [step.step_id for step in steps]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{period} step_id values must be unique")
        return self


class RoutineCreate(RoutineFields):
    owner_user_id: str = Field(min_length=1, max_length=128)

    @field_validator("owner_user_id", mode="before")
    @classmethod
    def trim_owner(cls, value):
        return value.strip() if isinstance(value, str) else value


class RoutineUpdate(RoutineFields):
    owner_user_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)

    @field_validator("owner_user_id", mode="before")
    @classmethod
    def trim_owner(cls, value):
        return value.strip() if isinstance(value, str) else value


class ShareCreate(StrictModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    expires_in_days: int = Field(default=30, ge=1, le=90)

    @field_validator("owner_user_id", mode="before")
    @classmethod
    def trim_owner(cls, value):
        return value.strip() if isinstance(value, str) else value


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("SKINCARE_ROUTINE_SERVICE_TOKEN", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            401, detail="Valid internal bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@lru_cache(maxsize=4)
def configured_engine(url: str) -> Engine:
    return engine_for_url(url)


def store() -> RoutineStore:
    url = os.getenv("SKINCARE_ROUTINE_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_DATABASE_NOT_CONFIGURED"})
    if url.startswith("sqlite:///") and os.getenv("SKINCARE_ROUTINE_ALLOW_SQLITE_TESTS") != "1":
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_SQLITE_TEST_MODE_REQUIRED"})
    try:
        return RoutineStore(configured_engine(url))
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_DATABASE_CONFIGURATION_INVALID"}) from exc


def _step_json(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": step["step_id"],
        "label": step["label"],
        "product_id": step.get("product_id"),
        "recommendation_id": step.get("recommendation_id"),
        "instruction": step.get("instruction"),
    }


def routine_json(row: Any, *, include_owner: bool = True) -> dict[str, Any]:
    value: dict[str, Any] = {
        "routine_id": row.routine_id,
        "name": row.name,
        "description": row.description,
        "morning_steps": [_step_json(step) for step in (row.morning_steps or [])],
        "evening_steps": [_step_json(step) for step in (row.evening_steps or [])],
        "version": row.version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_owner:
        value["owner_user_id"] = row.owner_user_id
    return value


def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, RoutineNotFound):
        raise HTTPException(404, detail={"code": "SKINCARE_ROUTINE_NOT_FOUND"}) from exc
    if isinstance(exc, RoutineConflict):
        raise HTTPException(409, detail={"code": "SKINCARE_ROUTINE_VERSION_CONFLICT", "message": str(exc)}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(422, detail={"code": "INVALID_SKINCARE_ROUTINE", "message": str(exc)}) from exc
    raise exc


@app.middleware("http")
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", tags=["operations"])
def ready() -> dict[str, object]:
    token_ready = len(os.getenv("SKINCARE_ROUTINE_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    url = os.getenv("SKINCARE_ROUTINE_DATABASE_URL", "").strip()
    database_ready = False
    schema_ready = False
    try:
        if url.startswith("sqlite:///") and os.getenv("SKINCARE_ROUTINE_ALLOW_SQLITE_TESTS") != "1":
            raise ValueError("SQLite is test-only")
        engine = configured_engine(url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        tables = set(inspect(engine).get_table_names())
        schema_ready = {"skincare_routines", "skincare_routine_shares"}.issubset(tables)
        database_ready = schema_ready
    except Exception:
        database_ready = False
    ready_state = token_ready and database_ready
    detail = {
        "status": "ready" if ready_state else "not_ready",
        "service": SERVICE,
        "authentication_configured": token_ready,
        "database_connected": database_ready,
        "schema_ready": schema_ready,
        "ready": ready_state,
    }
    if not ready_state:
        raise HTTPException(503, detail=detail)
    return detail


@app.post("/v1/routines", status_code=201, dependencies=[Depends(require_internal_token)], tags=["routines"])
def create_routine(payload: RoutineCreate) -> dict[str, object]:
    try:
        row = store().create(
            owner_user_id=payload.owner_user_id.strip(),
            routine_id=str(uuid.uuid4()),
            name=payload.name,
            description=payload.description,
            morning_steps=[step.model_dump() for step in payload.morning_steps],
            evening_steps=[step.model_dump() for step in payload.evening_steps],
        )
        return {"routine": routine_json(row)}
    except (RoutineConflict, RoutineNotFound, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.get("/v1/routines", dependencies=[Depends(require_internal_token)], tags=["routines"])
def list_routines(owner_user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    try:
        rows = store().list(owner_user_id.strip())
        return {"owner_user_id": owner_user_id.strip(), "routines": [routine_json(row) for row in rows]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.get("/v1/routines/{routine_id}", dependencies=[Depends(require_internal_token)], tags=["routines"])
def get_routine(routine_id: str, owner_user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    try:
        return {"routine": routine_json(store().get(owner_user_id.strip(), routine_id))}
    except (RoutineNotFound, RoutineConflict, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.put("/v1/routines/{routine_id}", dependencies=[Depends(require_internal_token)], tags=["routines"])
def update_routine(routine_id: str, payload: RoutineUpdate) -> dict[str, object]:
    try:
        row = store().update(
            owner_user_id=payload.owner_user_id.strip(),
            routine_id=routine_id,
            expected_version=payload.expected_version,
            name=payload.name,
            description=payload.description,
            morning_steps=[step.model_dump() for step in payload.morning_steps],
            evening_steps=[step.model_dump() for step in payload.evening_steps],
        )
        return {"routine": routine_json(row)}
    except (RoutineNotFound, RoutineConflict, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.delete("/v1/routines/{routine_id}", dependencies=[Depends(require_internal_token)], tags=["routines"])
def delete_routine(
    routine_id: str,
    owner_user_id: Annotated[str, Query(min_length=1, max_length=128)],
    expected_version: Annotated[int, Query(ge=1)],
) -> dict[str, object]:
    try:
        store().delete(
            owner_user_id=owner_user_id.strip(),
            routine_id=routine_id,
            expected_version=expected_version,
        )
        return {"deleted": True, "routine_id": routine_id}
    except (RoutineNotFound, RoutineConflict, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/routines/{routine_id}/share", dependencies=[Depends(require_internal_token)], tags=["sharing"])
def create_share(routine_id: str, payload: ShareCreate) -> dict[str, object]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    try:
        store().create_share(
            owner_user_id=payload.owner_user_id.strip(),
            routine_id=routine_id,
            token=token,
            expires_at=expires_at,
        )
        return {
            "share_path": f"/public/routines/{token}",
            "expires_at": expires_at.isoformat(),
            "warning": "Anyone with this link can view this routine until it expires or you revoke it.",
        }
    except (RoutineNotFound, RoutineConflict, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.delete("/v1/routines/{routine_id}/share", dependencies=[Depends(require_internal_token)], tags=["sharing"])
def revoke_share(
    routine_id: str,
    owner_user_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> dict[str, object]:
    try:
        return {
            "routine_id": routine_id,
            "revoked": store().revoke_share(owner_user_id=owner_user_id.strip(), routine_id=routine_id),
        }
    except (RoutineNotFound, RoutineConflict, ValueError) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc


@app.get("/public/routines/{token}", tags=["sharing"])
def get_shared_routine(token: str) -> dict[str, object]:
    if len(token) < 32 or len(token) > 128:
        raise HTTPException(404, detail={"code": "SHARED_ROUTINE_NOT_FOUND"})
    try:
        result = store().get_shared(token)
        if result is None:
            raise HTTPException(404, detail={"code": "SHARED_ROUTINE_NOT_FOUND"})
        row, expires_at = result
        return {
            "routine": routine_json(row, include_owner=False),
            "expires_at": expires_at.isoformat(),
            "shared_view": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SKINCARE_ROUTINE_STORE_UNAVAILABLE"}) from exc

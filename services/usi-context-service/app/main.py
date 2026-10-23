"""Persistent, user-scoped USI profile and EEPL context service.

Only trusted internal callers may write data. Updates require explicit user
confirmation; the service does not infer preferences, culture or context.
"""
from __future__ import annotations

import hmac
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, create_engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-usi-context-service"
EXPECTED_TABLES = {"usi_profiles", "usi_contexts", "usi_change_events"}
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna USI and User Context Service", version="0.1.0")


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class USIProfile(Base):
    __tablename__ = "usi_profiles"
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    preferences: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    eepl_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class UserContext(Base):
    __tablename__ = "usi_contexts"
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    age_years: Mapped[int | None] = mapped_column(nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    climate: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class USIChangeEvent(Base):
    __tablename__ = "usi_change_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


@lru_cache(maxsize=1)
def _engine():
    url = os.getenv("USI_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "USI_DATABASE_NOT_CONFIGURED"})
    if url.startswith("sqlite:///") and os.getenv("USI_ALLOW_SQLITE_TESTS") != "1":
        raise HTTPException(503, detail={"code": "USI_SQLITE_TEST_MODE_REQUIRED"})
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    parts = urlsplit(url)
    if parts.scheme not in {"postgresql+psycopg", "sqlite"}:
        raise HTTPException(503, detail={"code": "USI_DATABASE_SCHEME_NOT_ALLOWED"})
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    try:
        return create_engine(url, **kwargs)
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(503, detail={"code": "USI_DATABASE_CONFIGURATION_INVALID"}) from exc


def _session_factory():
    return sessionmaker(bind=_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()


def require_internal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = os.getenv("USI_SERVICE_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "USI_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "USI_INTERNAL_AUTH_FAILED"}, headers={"WWW-Authenticate": "Bearer"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StylePreference(StrictModel):
    preference_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0, le=1)
    active: bool = True


class EEPLPolicy(StrictModel):
    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(default="1.0.0", min_length=1, max_length=64)
    minimum_age: int | None = Field(default=None, ge=0, le=125)
    maximum_age: int | None = Field(default=None, ge=0, le=125)
    allowed_locations: list[str] = Field(default_factory=list, max_length=100)
    allowed_occasions: list[str] = Field(default_factory=list, max_length=100)
    allowed_climates: list[str] = Field(default_factory=list, max_length=100)
    required_context: list[Literal["age", "location", "occasion", "climate"]] = Field(default_factory=list, max_length=4)


class ProfileWrite(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    preferences: list[StylePreference] = Field(min_length=1, max_length=250)
    eepl_policy: EEPLPolicy
    user_confirmation: bool


class ContextWrite(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    age_years: int | None = Field(default=None, ge=0, le=125)
    location: str | None = Field(default=None, max_length=120)
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=120)
    user_confirmation: bool


def _profile_json(profile: USIProfile) -> dict[str, Any]:
    return {"profile_id": profile.profile_id, "user_id": profile.user_id, "version": profile.version,
            "preferences": profile.preferences, "updated_at": profile.updated_at.isoformat() if profile.updated_at else None}


@app.on_event("startup")
def startup() -> None:
    if os.getenv("USI_AUTO_CREATE_SCHEMA", "false").strip().lower() == "true":
        Base.metadata.create_all(bind=_engine())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def readiness() -> dict[str, Any]:
    token_ready = len(os.getenv("USI_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    database_connected = False
    schema_ready = False
    try:
        engine = _engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_connected = True
        schema_ready = EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))
    except (HTTPException, SQLAlchemyError):
        pass
    ready = token_ready and database_connected and schema_ready
    result = {"service": SERVICE, "ready": ready, "internal_auth_configured": token_ready,
              "database_connected": database_connected, "schema_ready": schema_ready,
              "durable_usi_profiles": schema_ready, "durable_user_context": schema_ready,
              "change_audit": schema_ready}
    if not ready:
        raise HTTPException(503, detail=result)
    return result


@app.put("/v1/profiles/{user_id}", dependencies=[Depends(require_internal)])
def write_profile(user_id: str, payload: ProfileWrite, db: Session = Depends(get_db)) -> dict[str, Any]:
    if user_id != payload.user_id:
        raise HTTPException(409, detail={"code": "USI_USER_BINDING_MISMATCH"})
    if payload.user_confirmation is not True:
        raise HTTPException(400, detail={"code": "EXPLICIT_USER_CONFIRMATION_REQUIRED"})
    if any(item.user_id != user_id for item in payload.preferences):
        raise HTTPException(409, detail={"code": "USI_PREFERENCE_USER_MISMATCH"})
    current = db.get(USIProfile, user_id)
    event_type = "profile_updated" if current else "profile_created"
    if current:
        current.profile_id = payload.profile_id
        current.version = payload.version
        current.preferences = [item.model_dump(mode="json") for item in payload.preferences]
        current.eepl_policy = payload.eepl_policy.model_dump(mode="json")
        current.updated_at = now()
    else:
        current = USIProfile(user_id=user_id, profile_id=payload.profile_id, version=payload.version,
            preferences=[item.model_dump(mode="json") for item in payload.preferences],
            eepl_policy=payload.eepl_policy.model_dump(mode="json"), updated_at=now())
        db.add(current)
    db.add(USIChangeEvent(event_id=str(uuid.uuid4()), user_id=user_id, event_type=event_type,
        source_version=payload.version, changed_at=now()))
    db.commit()
    db.refresh(current)
    return {"user_id": user_id, "usi_profile": _profile_json(current), "eepl_policy": current.eepl_policy}


@app.get("/v1/profiles/{user_id}", dependencies=[Depends(require_internal)])
def read_profile(user_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = db.get(USIProfile, user_id)
    if profile is None:
        raise HTTPException(404, detail={"code": "USI_PROFILE_NOT_FOUND"})
    return {"user_id": user_id, "usi_profile": _profile_json(profile), "eepl_policy": profile.eepl_policy}


@app.put("/v1/context/{user_id}", dependencies=[Depends(require_internal)])
def write_context(user_id: str, payload: ContextWrite, db: Session = Depends(get_db)) -> dict[str, Any]:
    if user_id != payload.user_id:
        raise HTTPException(409, detail={"code": "USER_CONTEXT_BINDING_MISMATCH"})
    if payload.user_confirmation is not True:
        raise HTTPException(400, detail={"code": "EXPLICIT_USER_CONFIRMATION_REQUIRED"})
    context = db.get(UserContext, user_id)
    if context is None:
        context = UserContext(user_id=user_id, age_years=payload.age_years, location=payload.location,
            occasion=payload.occasion, climate=payload.climate, updated_at=now())
        db.add(context)
    else:
        context.age_years, context.location, context.occasion, context.climate = payload.age_years, payload.location, payload.occasion, payload.climate
        context.updated_at = now()
    db.add(USIChangeEvent(event_id=str(uuid.uuid4()), user_id=user_id, event_type="context_updated",
        source_version=now().isoformat(), changed_at=now()))
    db.commit()
    return {"user_id": user_id, "context": {"user_id": user_id, "age_years": context.age_years,
        "location": context.location, "occasion": context.occasion, "climate": context.climate,
        "updated_at": context.updated_at.isoformat() if context.updated_at else None}}


@app.get("/v1/context/{user_id}", dependencies=[Depends(require_internal)])
def read_context(user_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    context = db.get(UserContext, user_id)
    if context is None:
        raise HTTPException(404, detail={"code": "USER_CONTEXT_NOT_FOUND"})
    return {"user_id": user_id, "context": {"user_id": user_id, "age_years": context.age_years,
        "location": context.location, "occasion": context.occasion, "climate": context.climate,
        "updated_at": context.updated_at.isoformat() if context.updated_at else None}}

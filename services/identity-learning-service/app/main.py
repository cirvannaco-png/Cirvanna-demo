"""Internal USI profile and TAL persistence API.

This service trusts only the API Gateway's machine credential. The gateway must
resolve end-user subjects through Commerce /me before forwarding a subject_id.
It owns prefixed tables in the existing shared managed Postgres database; it
does not provision a second database or expose a public end-user identity API.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from functools import lru_cache
from typing import Annotated, Iterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint, create_engine, select, delete, update, or_,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-identity-learning-service"
bearer = HTTPBearer(auto_error=False)
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
SCOPES = {
    "personalization", "style_learning", "profile_storage",
    "image_processing", "body_measurements", "virtual_twin_storage",
    "virtual_try_on", "click_it", "look_it", "skin_analysis",
    "wardrobe_photo_storage", "pnelly_conversation",
    "facial_geometry_analysis", "body_tone_analysis",
    "appearance_correction", "global_model_training", "appearance_session_storage", "appearance_source_storage",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cil_contributor_token(subject_id: str) -> str:
    """Derive a stable keyed pseudonym without exposing the canonical subject to CIL."""
    secret = os.getenv("CIL_CONTRIBUTOR_TOKEN_HMAC_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise HTTPException(503, detail={"code": "CIL_CONTRIBUTOR_TOKEN_KEY_NOT_CONFIGURED"})
    digest = hmac.new(
        secret,
        ("cirvanna:cil:contributor:v1:" + subject_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def engine_for_url(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def _engine(url: str):
    return engine_for_url(url)


@lru_cache(maxsize=4)
def _session_factory(url: str):
    return sessionmaker(bind=_engine(url), autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class USIProfileRow(Base):
    __tablename__ = "identity_usi_profiles"
    subject_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ColorProfileRow(Base):
    """User-declared colour preferences; objective colour analysis is stored separately."""
    __tablename__ = "identity_usi_color_profiles"
    subject_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    liked_colors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    disliked_colors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    best_version_colors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ConsentReceipt(Base):
    __tablename__ = "identity_tal_consent_receipts"
    __table_args__ = (
        Index("ix_identity_tal_consent_subject_scope", "subject_id", "scope", "granted"),
        Index("ix_identity_tal_consent_bundle", "subject_id", "consent_id", "resource_id", "granted"),
        Index("ix_identity_tal_consent_expiry", "expires_at"),
    )
    receipt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_contributor_token: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)



class DSICaptureChallengeRow(Base):
    """Short-lived DSI challenge state; raw nonce material is never persisted."""

    __tablename__ = "identity_dsi_capture_challenges"
    __table_args__ = (
        Index("ix_identity_dsi_capture_challenge_subject", "subject_id", "created_at"),
        Index("ix_identity_dsi_capture_challenge_expiry", "expires_at"),
    )
    challenge_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    required_scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    consent_receipt_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    nonce_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_receipt_id: Mapped[str | None] = mapped_column(String(80))


class DSICaptureVerificationReceiptRow(Base):
    """Immutable, short-lived record created only by the trusted Vision verifier."""

    __tablename__ = "identity_dsi_capture_verification_receipts"
    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_identity_dsi_capture_receipt_challenge"),
        Index("ix_identity_dsi_capture_receipt_subject", "subject_id", "issued_at"),
        Index("ix_identity_dsi_capture_receipt_expiry", "expires_at"),
    )
    receipt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(
        ForeignKey("identity_dsi_capture_challenges.challenge_id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_receipt_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    device_pipeline_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    key_attestation_challenge_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    play_integrity_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    package_name: Mapped[str] = mapped_column(String(200), nullable=False)
    package_certificate_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    app_version: Mapped[str] = mapped_column(String(80), nullable=False)
    sdk_version: Mapped[str] = mapped_column(String(80), nullable=False)
    verifier_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    key_security_level: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_boot_state: Mapped[str] = mapped_column(String(32), nullable=False)
    app_recognition_verdict: Mapped[str] = mapped_column(String(40), nullable=False)
    account_licensing_verdict: Mapped[str] = mapped_column(String(40), nullable=False)
    device_integrity_verdicts: Mapped[list] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TALEvent(Base):
    __tablename__ = "identity_tal_events"
    __table_args__ = (
        UniqueConstraint("subject_id", "idempotency_key", name="uq_identity_tal_subject_idempotency"),
        Index("ix_identity_tal_subject_observed", "subject_id", "observed_at"),
        Index("ix_identity_tal_expiry", "expires_at"),
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_receipt_id: Mapped[str] = mapped_column(ForeignKey("identity_tal_consent_receipts.receipt_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="observation")
    supersedes_event_id: Mapped[str | None] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TALDeletionReceipt(Base):
    __tablename__ = "identity_tal_deletion_receipts"
    receipt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_profile: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ConsentRevocationOutbox(Base):
    """Durable, retryable handoff from consent withdrawal to Twin asset cleanup."""
    __tablename__ = "identity_consent_revocation_outbox"
    __table_args__ = (
        Index("ix_identity_consent_revocation_status_created", "status", "created_at"),
    )
    command_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CILProviderConsentRevocationOutbox(Base):
    """Durable consent-to-CIL provider cleanup handoff; stores only a keyed pseudonym."""
    __tablename__ = "identity_cil_provider_consent_revocation_outbox"
    __table_args__ = (
        Index("ix_identity_cil_provider_revocation_status_created", "status", "created_at"),
        Index("ix_identity_cil_provider_revocation_receipt", "revocation_receipt_id"),
    )
    command_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    revocation_receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160))
    receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contributor_token: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    matched_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waiting_for_terminal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PnellyConversation(Base):
    """Short-lived, structured discovery context; raw chat transcript is never stored."""
    __tablename__ = "identity_pnelly_conversations"
    __table_args__ = (
        Index("ix_identity_pnelly_conversation_subject", "subject_id"),
        Index("ix_identity_pnelly_conversation_expiry", "expires_at"),
    )
    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    consent_receipt_id: Mapped[str] = mapped_column(
        ForeignKey("identity_tal_consent_receipts.receipt_id"), nullable=False
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_turn_id: Mapped[str | None] = mapped_column(String(128))
    last_turn_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkinAnalysisProviderReceiptIn(StrictModel):
    receipt_id: str = Field(min_length=8, max_length=128)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_subject_age_years: int = Field(ge=18, le=120)

    @field_validator("verified_subject_age_years", mode="before")
    @classmethod
    def strict_adult_age(cls, value):
        if type(value) is not int:
            raise ValueError("verified_subject_age_years must be an integer")
        return value


class SkinAnalysisProviderConsentVerifyIn(StrictModel):
    receipt_id: str = Field(min_length=8, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    resource_id: str = Field(min_length=3, max_length=160)
    contributor_token: str = Field(pattern=r"^hmac-sha256:[0-9a-f]{64}$")
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


PNELLY_CONFIRMED_PROFILE_ATTRIBUTES = {
    "style:minimalist", "style:elegant", "style:romantic", "style:bold",
    "style:streetwear", "style:classic", "style:editorial",
    "color:teal", "color:navy", "color:earthy", "color:monochrome", "color:pastel",
    "silhouette:relaxed", "silhouette:tailored", "silhouette:oversized", "silhouette:structured",
    "material:linen", "material:cotton", "material:denim", "material:silk",
    "pattern:solid", "pattern:floral", "pattern:striped", "pattern:geometric",
    "culture:ankara",
    "culture:kitenge",
    "culture:kente",
    "culture:adire",
    "culture:aso-oke",
    "culture:batik",
    "culture:saree",
    "culture:lehenga",
    "culture:salwar-kameez",
    "culture:kimono-inspired",
    "culture:hanbok-inspired",
    "culture:abaya",
    "culture:kaftan",
    "culture:embroidered-thobe",
    "culture:caribbean-textiles",
    "culture:indigenous-craft-user-selected",
    "occasion:everyday",
    "occasion:work",
    "occasion:wedding",
    "occasion:celebration",
    "occasion:religious-occasion",
    "occasion:formal",
    "occasion:travel",
    "coverage:covered-shoulders",
    "coverage:long-sleeves",
    "coverage:knee-length-or-longer",
    "coverage:ankle-length",
    "coverage:high-neckline",
    "coverage:loose-fit",
    "coverage:opaque-fabric",
    "coverage:head-covering-if-selected",
    "style:bohemian",
    "style:natural",
    "color:jewel-tones",
    "color:burgundy",
    "color:emerald",
    "color:sapphire",
}


class PreferenceIn(StrictModel):
    preference_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0, le=1)
    active: bool = True
    source: Literal["user_declared", "pnelly_user_confirmed"] = "user_declared"
    source_request_id: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_pnelly_provenance(self):
        if self.source == "pnelly_user_confirmed":
            if self.attribute not in PNELLY_CONFIRMED_PROFILE_ATTRIBUTES:
                raise ValueError("PNELLY preference attribute is not in the controlled taxonomy")
            if not self.source_request_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", self.source_request_id):
                raise ValueError("PNELLY preferences require a valid source request ID")
        elif self.source_request_id is not None:
            raise ValueError("source_request_id is reserved for PNELLY-confirmed preferences")
        return self


class ProfilePut(StrictModel):
    expected_version: int | None = Field(default=None, ge=0)
    consent_receipt_id: str | None = Field(default=None, min_length=8, max_length=128)
    preferences: list[PreferenceIn] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.preference_id.strip() for x in self.preferences]
        if len(ids) != len(set(ids)):
            raise ValueError("preference_id values must be unique")
        return self


class ColorProfilePut(StrictModel):
    expected_version: int = Field(ge=0)
    liked_colors: list[str] = Field(default_factory=list, max_length=40)
    disliked_colors: list[str] = Field(default_factory=list, max_length=40)
    best_version_colors: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("liked_colors", "disliked_colors", "best_version_colors")
    @classmethod
    def normalize_color_list(cls, values):
        normalized = [" ".join(value.strip().casefold().split()) for value in values]
        if any(not value or len(value) > 40 for value in normalized):
            raise ValueError("color names must be non-empty and at most 40 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("color names must be unique within each preference list")
        return normalized


class PnellyDiscoveryContext(StrictModel):
    """Only normalized search state is retained; never include transcript or arbitrary profile data."""
    query: str | None = Field(default=None, min_length=2, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    location: str | None = Field(default=None, min_length=1, max_length=120)
    occasion: str | None = Field(default=None, min_length=1, max_length=120)
    climate: str | None = Field(default=None, min_length=1, max_length=120)
    constraints: list[str] = Field(default_factory=list, max_length=8)
    exclude_owned_products: bool = True

    @field_validator("query", "category", "currency", "location", "occasion", "climate", mode="before")
    @classmethod
    def trim_context_strings(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("context fields must be strings")
        value = " ".join(value.split()).strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value):
        return value.upper() if value else None

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, values):
        normalized = [" ".join(value.split()).strip() for value in values if isinstance(value, str)]
        if len(normalized) != len(values) or any(not value or len(value) > 120 for value in normalized):
            raise ValueError("constraints must be non-empty strings of at most 120 characters")
        if len(normalized) != len(set(item.casefold() for item in normalized)):
            raise ValueError("constraints must be unique")
        return normalized


    @model_validator(mode="after")
    def bounded_search_context(self):
        total = len(self.query or "") + sum(len(item) for item in self.constraints)
        if total > 160:
            raise ValueError("query plus discovery cues must fit the 160-character search limit")
        return self


class PnellyConversationCreate(StrictModel):
    conversation_id: str = Field(min_length=36, max_length=36)
    consent_receipt_id: str = Field(min_length=8, max_length=128)

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise ValueError("conversation_id must be a UUID") from exc


class PnellyConversationUpdate(StrictModel):
    expected_version: int = Field(ge=0)
    turn_id: str = Field(min_length=8, max_length=128)
    context: PnellyDiscoveryContext


class ConsentPut(StrictModel):
    receipt_id: str = Field(min_length=8, max_length=128)
    scope: Literal[
        "personalization", "style_learning", "profile_storage",
        "image_processing", "body_measurements", "virtual_twin_storage",
        "virtual_try_on", "click_it", "look_it", "skin_analysis",
        "wardrobe_photo_storage", "pnelly_conversation",
        "facial_geometry_analysis", "body_tone_analysis",
        "appearance_correction", "global_model_training", "appearance_session_storage",
        "appearance_source_storage",
    ]
    consent_version: str = Field(min_length=1, max_length=80)
    granted: bool
    consent_id: str | None = Field(default=None, min_length=8, max_length=128)
    resource_id: str | None = Field(default=None, min_length=3, max_length=160)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("consent expiry must include a timezone")
        normalized = value.astimezone(timezone.utc)
        if normalized <= datetime.now(timezone.utc):
            raise ValueError("new consent expiry must be in the future")
        return normalized

    @field_validator("receipt_id", "consent_id", "resource_id", mode="before")
    @classmethod
    def normalize_identifiers(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("consent identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("consent identifiers must not be empty")
        return normalized


class ConsentVerify(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    required_scopes: list[str] = Field(min_length=1, max_length=10)
    consent_version: str | None = Field(default=None, min_length=1, max_length=80)
    resource_id: str | None = Field(default=None, min_length=3, max_length=160)
    require_expiring: bool = False

    @field_validator("subject_id", "consent_id", "resource_id", mode="before")
    @classmethod
    def normalize_verification_identifiers(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("verification identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("verification identifiers must not be empty")
        return normalized

    @field_validator("required_scopes")
    @classmethod
    def validate_required_scopes(cls, values):
        normalized = [value.strip() for value in values if isinstance(value, str)]
        if len(normalized) != len(values) or not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("required scopes must be non-empty, unique strings")
        unknown = set(normalized) - SCOPES
        if unknown:
            raise ValueError("unknown consent scope")
        return normalized



DSI_CAPTURE_PURPOSE_SCOPES: dict[str, tuple[str, ...]] = {
    "cosmetic_skin_analysis": ("image_processing", "skin_analysis"),
    "facial_geometry_analysis": ("image_processing", "facial_geometry_analysis"),
    "body_tone_analysis": ("image_processing", "body_tone_analysis"),
    "appearance_correction": ("image_processing", "appearance_correction"),
}
DSI_CAPTURE_CHALLENGE_TTL_SECONDS = 180
DSI_CAPTURE_RECEIPT_TTL_SECONDS = 120


class DSICaptureChallengeCreate(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    consent_version: str = Field(min_length=1, max_length=80)
    resource_id: str = Field(min_length=3, max_length=160)
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ]


class DSICaptureChallengeConsume(StrictModel):
    nonce_b64url: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    device_pipeline_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    key_attestation_challenge_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    play_integrity_request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    package_name: str = Field(min_length=3, max_length=200)
    package_certificate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    app_version: str = Field(min_length=1, max_length=80)
    sdk_version: str = Field(min_length=1, max_length=80)
    verifier_policy_version: str = Field(min_length=1, max_length=80)
    key_security_level: Literal["strongbox", "trusted_environment", "software"]
    verified_boot_state: Literal["verified", "self_signed", "unverified", "failed"]
    app_recognition_verdict: Literal["PLAY_RECOGNIZED", "UNRECOGNIZED_VERSION", "UNEVALUATED"]
    account_licensing_verdict: Literal["LICENSED", "UNLICENSED", "UNEVALUATED"]
    device_integrity_verdicts: list[
        Literal["MEETS_BASIC_INTEGRITY", "MEETS_DEVICE_INTEGRITY", "MEETS_STRONG_INTEGRITY"]
    ] = Field(min_length=1, max_length=3)

    @field_validator("nonce_b64url")
    @classmethod
    def validate_nonce_encoding(cls, value: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(value + "=")
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("nonce must be canonical base64url") from exc
        if len(raw) != 32 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
            raise ValueError("nonce must encode exactly 32 canonical bytes")
        return value

    @model_validator(mode="after")
    def validate_verified_claims(self):
        expected = hashlib.sha256(base64.urlsafe_b64decode(self.nonce_b64url + "=")).hexdigest()
        if self.key_attestation_challenge_sha256 != expected:
            raise ValueError("key-attestation challenge digest must match the issued nonce")
        if self.play_integrity_request_hash != self.manifest_sha256:
            raise ValueError("Play Integrity requestHash must match the canonical manifest digest")
        if self.key_security_level == "software":
            raise ValueError("software-backed keys cannot produce a hardware capture receipt")
        if self.verified_boot_state != "verified":
            raise ValueError("verified boot is required by the current capture verifier policy")
        if self.app_recognition_verdict != "PLAY_RECOGNIZED":
            raise ValueError("Play Integrity must recognize the expected application")
        if self.account_licensing_verdict != "LICENSED":
            raise ValueError("Play Integrity must report an active app license")
        if not ({"MEETS_DEVICE_INTEGRITY", "MEETS_STRONG_INTEGRITY"} & set(self.device_integrity_verdicts)):
            raise ValueError("Play Integrity must meet the configured device-integrity threshold")
        return self


class DSICaptureReceiptVerify(StrictModel):
    receipt_id: str = Field(min_length=12, max_length=80)
    subject_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=3, max_length=160)
    purpose: Literal[
        "cosmetic_skin_analysis",
        "facial_geometry_analysis",
        "body_tone_analysis",
        "appearance_correction",
    ]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    device_pipeline_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EventPut(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=160)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    feature_key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    observed_at: str
    expires_at: str | None = None
    event_kind: Literal["observation", "correction"] = "observation"
    supersedes_event_id: str | None = Field(default=None, max_length=128)

    @field_validator("observed_at")
    @classmethod
    def valid_observed(cls, value):
        parse_time(value)
        return value

    @field_validator("expires_at")
    @classmethod
    def valid_expiry(cls, value):
        if value is not None:
            parse_time(value)
        return value

    @model_validator(mode="after")
    def validate_correction(self):
        if self.event_kind == "correction" and not self.supersedes_event_id:
            raise ValueError("corrections must identify supersedes_event_id")
        if self.event_kind == "observation" and self.supersedes_event_id:
            raise ValueError("observation cannot supersede another event")
        if self.expires_at and parse_time(self.expires_at) <= parse_time(self.observed_at):
            raise ValueError("expires_at must be later than observed_at")
        return self


def get_db() -> Iterator[Session]:
    url = os.getenv("IDENTITY_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "IDENTITY_DATABASE_NOT_CONFIGURED"})
    db = _session_factory(url)()
    try:
        yield db
    finally:
        db.close()


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})





def require_cil_consent_issuer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """Dedicated credential held only by the trusted adult-eligibility assertion service."""
    expected = os.getenv("IDENTITY_CIL_CONSENT_ISSUER_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_CIL_CONSENT_ISSUER_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "CIL_CONSENT_ISSUER_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_cil_consent_verifier(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """Dedicated credential held only by the CIL server, never by browsers."""
    expected = os.getenv("IDENTITY_CIL_CONSENT_VERIFIER_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_CIL_CONSENT_VERIFIER_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "CIL_CONSENT_VERIFIER_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_dsi_capture_service(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """Separate machine credential held only by DermalSight/Vision service identities."""
    expected = os.getenv("IDENTITY_DSI_CAPTURE_SERVICE_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_DSI_CAPTURE_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "DSI_CAPTURE_INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _active_dsi_capture_consent_bundle(
    db: Session,
    *,
    subject_id: str,
    consent_id: str,
    consent_version: str,
    resource_id: str,
    purpose: str,
) -> tuple[tuple[str, ...], list[str], datetime]:
    required_scopes = DSI_CAPTURE_PURPOSE_SCOPES[purpose]
    statement = select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject_id,
        ConsentReceipt.consent_id == consent_id,
        ConsentReceipt.resource_id == resource_id,
        ConsentReceipt.consent_version == consent_version,
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        ConsentReceipt.expires_at.is_not(None),
        ConsentReceipt.expires_at > utcnow(),
    ).with_for_update()
    rows = list(db.scalars(statement).all())
    granted = {row.scope for row in rows}
    missing = sorted(set(required_scopes) - granted)
    if missing:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_INCOMPLETE", "missing_scopes": missing})
    selected = [row for row in rows if row.scope in required_scopes]
    if len({row.consent_version for row in selected}) != 1:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_VERSION_MISMATCH"})
    receipt_ids = sorted(row.receipt_id for row in selected)
    expiry_values = [normalize_utc(row.expires_at) for row in selected]
    if not receipt_ids or any(value is None for value in expiry_values):
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_EXPIRY_REQUIRED"})
    return required_scopes, receipt_ids, min(expiry_values)


def _capture_receipt_public_payload(row: DSICaptureVerificationReceiptRow) -> dict[str, object]:
    return {
        "receipt_id": row.receipt_id,
        "challenge_id": row.challenge_id,
        "subject_id": row.subject_id,
        "consent_id": row.consent_id,
        "consent_version": row.consent_version,
        "resource_id": row.resource_id,
        "purpose": row.purpose,
        "consent_receipt_ids": row.consent_receipt_ids,
        "manifest_sha256": row.manifest_sha256,
        "image_sha256": row.image_sha256,
        "device_pipeline_fingerprint_sha256": row.device_pipeline_fingerprint_sha256,
        "package_name": row.package_name,
        "package_certificate_sha256": row.package_certificate_sha256,
        "app_version": row.app_version,
        "sdk_version": row.sdk_version,
        "verifier_policy_version": row.verifier_policy_version,
        "key_security_level": row.key_security_level,
        "verified_boot_state": row.verified_boot_state,
        "app_recognition_verdict": row.app_recognition_verdict,
        "account_licensing_verdict": row.account_licensing_verdict,
        "device_integrity_verdicts": row.device_integrity_verdicts,
        "issued_at": normalize_utc(row.issued_at).isoformat(),
        "expires_at": normalize_utc(row.expires_at).isoformat(),
        "verification_status": "verified_by_trusted_vision_service",
    }


def _dsi_private_response(payload: dict[str, object], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )



def subject_or_404(subject_id: str) -> str:
    subject = subject_id.strip()
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, detail={"code": "INVALID_VERIFIED_SUBJECT"})
    return subject


def active_consent_predicate():
    """Legacy null expiry remains readable; new expiries are enforced centrally."""
    return or_(ConsentReceipt.expires_at.is_(None), ConsentReceipt.expires_at > utcnow())


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def consent_is_active(receipt: ConsentReceipt) -> bool:
    if not receipt.granted or receipt.revoked_at is not None:
        return False
    expiry = normalize_utc(receipt.expires_at)
    return expiry is None or expiry > utcnow()


def _event_hash(payload: EventPut) -> str:
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


app = FastAPI(
    title="Cirvanna USI and TAL service",
    version="1.0.0",
    description="Internal-only persistent explicit preferences and consented temporal learning.",
)


@app.on_event("startup")
def startup() -> None:
    if os.getenv("IDENTITY_AUTO_CREATE_SCHEMA", "false").lower() == "true":
        url = os.getenv("IDENTITY_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("IDENTITY_DATABASE_URL is required")
        Base.metadata.create_all(bind=_engine(url))


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", dependencies=[Depends(require_internal_token)])
def readiness(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(select(USIProfileRow.subject_id).limit(1))
        db.execute(select(ColorProfileRow.subject_id).limit(1))
        db.execute(select(ConsentReceipt.consent_id, ConsentReceipt.expires_at).limit(1))
        db.execute(select(TALEvent.event_id).limit(1))
        db.execute(select(PnellyConversation.conversation_id).limit(1))
        db.execute(select(ConsentRevocationOutbox.command_id).limit(1))
        db.execute(select(CILProviderConsentRevocationOutbox.command_id).limit(1))
        db.execute(select(DSICaptureChallengeRow.challenge_id).limit(1))
        db.execute(select(DSICaptureVerificationReceiptRow.receipt_id).limit(1))
        return {
            "status": "ready",
            "service": SERVICE,
            "database": "reachable",
            "durable_usi": True,
            "durable_tal": True,
            "pnelly_conversation_context": True,
            "twin_consent_cleanup_outbox": True,
            "cil_provider_consent_cleanup_outbox": True,
            "dsi_capture_challenge_state": True,
            "dsi_capture_verification_receipts": True,
            "ready": True,
        }
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "IDENTITY_SCHEMA_NOT_READY"})


@app.get("/v1/profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def get_profile(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    active = db.scalar(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject, ConsentReceipt.scope == "profile_storage", ConsentReceipt.granted.is_(True), ConsentReceipt.revoked_at.is_(None), active_consent_predicate()).limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(USIProfileRow, subject)
    if row is None:
        return {"subject_id": subject, "profile_version": 0, "preferences": []}
    return {"subject_id": subject, "profile_version": row.profile_version, "preferences": row.preferences, "updated_at": row.updated_at.isoformat()}


@app.put("/v1/profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def put_profile(subject_id: str, payload: ProfilePut, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    consent_query = select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject,
        ConsentReceipt.scope == "profile_storage",
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        active_consent_predicate(),
    )
    if payload.consent_receipt_id is not None:
        consent_query = consent_query.where(ConsentReceipt.receipt_id == payload.consent_receipt_id)
    # Serialize profile writes against concurrent receipt revocation. On
    # PostgreSQL, the row lock makes a revocation either precede this check or
    # wait until this authorized write commits; a stale receipt cannot race it.
    active = db.scalar(consent_query.with_for_update().limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(USIProfileRow, subject)
    current = row.profile_version if row else 0
    if payload.expected_version is not None and payload.expected_version != current:
        raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": current})
    preferences = [item.model_dump() for item in payload.preferences]
    now = utcnow()
    if row is None:
        row = USIProfileRow(subject_id=subject, profile_version=1, preferences=preferences, updated_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            latest = db.scalar(select(USIProfileRow.profile_version).where(USIProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": latest})
    else:
        statement = update(USIProfileRow).where(USIProfileRow.subject_id == subject)
        if payload.expected_version is not None:
            statement = statement.where(USIProfileRow.profile_version == payload.expected_version)
        result = db.execute(statement.values(
            profile_version=USIProfileRow.profile_version + 1,
            preferences=preferences,
            updated_at=now,
        ))
        if result.rowcount != 1:
            db.rollback()
            latest = db.scalar(select(USIProfileRow.profile_version).where(USIProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT", "current_version": latest})
        db.commit()
        db.expire_all()
        row = db.get(USIProfileRow, subject)
    return {"subject_id": subject, "profile_version": row.profile_version, "preferences": row.preferences, "updated_at": row.updated_at.isoformat()}


@app.get("/v1/color-profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def get_color_profile(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    active = db.scalar(select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject,
        ConsentReceipt.scope == "profile_storage",
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        active_consent_predicate(),
    ).limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(ColorProfileRow, subject)
    return {
        "subject_id": subject,
        "profile_version": row.profile_version if row else 0,
        "liked_colors": row.liked_colors if row else [],
        "disliked_colors": row.disliked_colors if row else [],
        "best_version_colors": row.best_version_colors if row else [],
        "analysis": {
            "status": "unavailable",
            "reason_code": "NO_VALIDATED_COLOR_ANALYSIS_MODEL",
            "message": "No validated colour-analysis model is connected. These lists are user-declared preferences, not objective skin-tone analysis.",
        },
    }


@app.put("/v1/color-profiles/{subject_id}", dependencies=[Depends(require_internal_token)])
def put_color_profile(subject_id: str, payload: ColorProfilePut, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    active = db.scalar(select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject,
        ConsentReceipt.scope == "profile_storage",
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        active_consent_predicate(),
    ).limit(1))
    if active is None:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    row = db.get(ColorProfileRow, subject)
    current = row.profile_version if row else 0
    if payload.expected_version != current:
        raise HTTPException(409, detail={"code": "COLOR_PROFILE_VERSION_CONFLICT", "current_version": current})
    values = {
        "liked_colors": payload.liked_colors,
        "disliked_colors": payload.disliked_colors,
        "best_version_colors": payload.best_version_colors,
    }
    now = utcnow()
    if row is None:
        row = ColorProfileRow(subject_id=subject, profile_version=1, updated_at=now, **values)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            latest = db.scalar(select(ColorProfileRow.profile_version).where(ColorProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "COLOR_PROFILE_VERSION_CONFLICT", "current_version": latest})
    else:
        result = db.execute(
            update(ColorProfileRow)
            .where(ColorProfileRow.subject_id == subject, ColorProfileRow.profile_version == payload.expected_version)
            .values(profile_version=ColorProfileRow.profile_version + 1, updated_at=now, **values)
        )
        if result.rowcount != 1:
            db.rollback()
            latest = db.scalar(select(ColorProfileRow.profile_version).where(ColorProfileRow.subject_id == subject)) or 0
            raise HTTPException(409, detail={"code": "COLOR_PROFILE_VERSION_CONFLICT", "current_version": latest})
        db.commit()
        db.expire_all()
        row = db.get(ColorProfileRow, subject)
    return {
        "subject_id": subject,
        "profile_version": row.profile_version,
        "liked_colors": row.liked_colors,
        "disliked_colors": row.disliked_colors,
        "best_version_colors": row.best_version_colors,
        "analysis": {
            "status": "unavailable",
            "reason_code": "NO_VALIDATED_COLOR_ANALYSIS_MODEL",
            "message": "Saved preferences are user-declared. Objective complexion/undertone analysis remains unavailable until a validated model is deployed.",
        },
    }


@app.post("/v1/tal/consents", dependencies=[Depends(require_internal_token)])
async def put_consent(subject_id: str = Query(min_length=1, max_length=128), payload: ConsentPut = None, db: Session = Depends(get_db)):
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "CONSENT_RECEIPT_REQUIRED"})
    consent_id = payload.consent_id or payload.receipt_id
    existing = db.get(ConsentReceipt, payload.receipt_id)
    if existing is not None:
        if (
            existing.subject_id != subject
            or existing.scope != payload.scope
            or existing.consent_version != payload.consent_version
            or existing.granted != payload.granted
            or existing.consent_id != consent_id
            or existing.resource_id != payload.resource_id
            or normalize_utc(existing.expires_at) != normalize_utc(payload.expires_at)
        ):
            raise HTTPException(409, detail={"code": "CONSENT_RECEIPT_IMMUTABLE"})
        existing_twin_commands = list(db.scalars(select(
            ConsentRevocationOutbox.command_id
        ).where(
            ConsentRevocationOutbox.subject_id == existing.subject_id,
            ConsentRevocationOutbox.consent_id == existing.consent_id,
            ConsentRevocationOutbox.resource_id == existing.resource_id,
        )).all())
        twin_result = await _dispatch_twin_consent_revocations_batched(
            db, existing_twin_commands,
        ) if existing_twin_commands else _empty_cleanup_dispatch_result()
        existing_cil_commands = list(db.scalars(select(
            CILProviderConsentRevocationOutbox.command_id
        ).where(
            CILProviderConsentRevocationOutbox.revocation_receipt_id == existing.receipt_id,
        )).all())
        cil_result = await _dispatch_cil_provider_consent_revocations_batched(
            db, existing_cil_commands,
        ) if existing_cil_commands else _empty_cleanup_dispatch_result()
        return {
            "receipt_id": existing.receipt_id, "consent_id": existing.consent_id,
            "resource_id": existing.resource_id, "expires_at": existing.expires_at.isoformat() if existing.expires_at else None, "status": "replayed", "granted": existing.granted,
            "twin_cleanup_status": (
                "pending" if twin_result["pending"] or twin_result["failed"]
                else "delivered" if twin_result["delivered"]
                else "not_applicable"
            ),
            "cil_provider_cleanup_status": (
                "pending" if cil_result["pending"] or cil_result["failed"]
                else "delivered" if cil_result["delivered"]
                else "not_applicable"
            ),
        }

    now = utcnow()
    provider_contributor_token = None
    if payload.granted and payload.scope == "skin_analysis":
        if payload.resource_id is None or payload.expires_at is None:
            raise HTTPException(422, detail={"code": "SKIN_ANALYSIS_CONSENT_MUST_BE_RESOURCE_BOUND_AND_EXPIRE"})
        existing_bundle = db.scalar(select(ConsentReceipt.receipt_id).where(
            ConsentReceipt.scope == "skin_analysis",
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.consent_id == consent_id,
        ).limit(1))
        if existing_bundle is not None:
            raise HTTPException(409, detail={"code": "SKIN_ANALYSIS_CONSENT_ID_MUST_BE_UNIQUE"})
        provider_contributor_token = _cil_contributor_token(subject)

    affected_receipts: list[ConsentReceipt] = []
    if not payload.granted:
        # Snapshot every active receipt being withdrawn so provider cleanup commands
        # are committed in the same transaction as the canonical revocation.
        statement = select(ConsentReceipt).where(
            ConsentReceipt.subject_id == subject,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        )
        if payload.resource_id is not None:
            statement = statement.where(
                ConsentReceipt.consent_id == consent_id,
                ConsentReceipt.resource_id == payload.resource_id,
            )
        else:
            statement = statement.where(ConsentReceipt.scope == payload.scope)
        affected_receipts = list(db.scalars(statement).all())
        if affected_receipts:
            ids = [item.receipt_id for item in affected_receipts]
            db.execute(update(ConsentReceipt).where(
                ConsentReceipt.receipt_id.in_(ids),
            ).values(revoked_at=now))
        _delete_inactive_pnelly_conversations(db, subject)

    twin_cleanup_ids: set[str] = set()
    cil_cleanup_ids: set[str] = set()
    if not payload.granted:
        for affected in affected_receipts:
            twin_cleanup = _queue_twin_consent_cleanup(
                db,
                subject_id=subject,
                consent_id=affected.consent_id,
                resource_id=affected.resource_id,
                receipt_id=affected.receipt_id,
                scope=affected.scope,
            )
            if twin_cleanup is not None:
                twin_cleanup_ids.add(twin_cleanup.command_id)
            for cleanup in _queue_cil_provider_consent_cleanup(
                db, affected, revocation_receipt_id=payload.receipt_id
            ):
                cil_cleanup_ids.add(cleanup.command_id)

    row = ConsentReceipt(
        receipt_id=payload.receipt_id, subject_id=subject, consent_id=consent_id,
        resource_id=payload.resource_id, scope=payload.scope,
        consent_version=payload.consent_version, granted=payload.granted,
        granted_at=now if payload.granted else None,
        revoked_at=None if payload.granted else now,
        expires_at=payload.expires_at if payload.granted else None,
        provider_contributor_token=provider_contributor_token,
    )
    db.add(row)
    db.commit()

    twin_result = await _dispatch_twin_consent_revocations_batched(
        db, sorted(twin_cleanup_ids),
    ) if twin_cleanup_ids else _empty_cleanup_dispatch_result()
    cil_result = await _dispatch_cil_provider_consent_revocations_batched(
        db, sorted(cil_cleanup_ids),
    ) if cil_cleanup_ids else _empty_cleanup_dispatch_result()
    return {
        "receipt_id": row.receipt_id, "consent_id": row.consent_id,
        "resource_id": row.resource_id, "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "status": "recorded", "granted": row.granted,
        "twin_cleanup_status": "pending" if twin_result["pending"] or twin_result["failed"] else ("delivered" if twin_result.get("delivered", twin_result["completed"]) else "not_applicable"),
        "cil_provider_cleanup_status": "pending" if cil_result["pending"] or cil_result["failed"] else ("delivered" if cil_result["delivered"] else "not_applicable"),
    }


@app.post("/internal/v1/consents/skin-analysis-provider-receipts", dependencies=[Depends(require_cil_consent_issuer)])
def issue_skin_analysis_provider_consent_receipt(
    subject_id: str = Query(min_length=1, max_length=128),
    payload: SkinAnalysisProviderReceiptIn = None,
    db: Session = Depends(get_db),
):
    """Issue a short-lived, image-digest-bound CIL receipt from canonical active consent."""
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "SKIN_ANALYSIS_PROVIDER_RECEIPT_REQUIRED"})
    consent = db.get(ConsentReceipt, payload.receipt_id)
    if (
        consent is None or consent.subject_id != subject
        or consent.scope != "skin_analysis"
        or not consent_is_active(consent)
        or consent.provider_contributor_token is None
        or consent.resource_id is None
    ):
        raise HTTPException(403, detail={"code": "ACTIVE_RESOURCE_BOUND_SKIN_ANALYSIS_CONSENT_REQUIRED"})
    consent_expiry = normalize_utc(consent.expires_at)
    if consent_expiry is None:
        raise HTTPException(403, detail={"code": "EXPIRING_SKIN_ANALYSIS_CONSENT_REQUIRED"})
    key = os.getenv("CIL_SKIN_ANALYSIS_CONSENT_KEY", "").encode("utf-8")
    if len(key) < 32:
        raise HTTPException(503, detail={"code": "CIL_SKIN_ANALYSIS_CONSENT_KEY_NOT_CONFIGURED"})
    try:
        ttl_seconds = int(os.getenv("CIL_SKIN_ANALYSIS_RECEIPT_TTL_SECONDS", "600"))
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "CIL_SKIN_ANALYSIS_RECEIPT_TTL_INVALID"}) from exc
    if not 60 <= ttl_seconds <= 900:
        raise HTTPException(503, detail={"code": "CIL_SKIN_ANALYSIS_RECEIPT_TTL_INVALID"})
    receipt_expiry = min(consent_expiry, utcnow() + timedelta(seconds=ttl_seconds))
    if receipt_expiry <= utcnow():
        raise HTTPException(403, detail={"code": "SKIN_ANALYSIS_CONSENT_EXPIRED"})
    signed_payload = {
        "type": "consent",
        "purpose": "perfectcorp_skin_analysis",
        "provider": "perfectcorp",
        "subject_token": consent.provider_contributor_token,
        "consent_id": consent.consent_id,
        "consent_receipt_id": consent.receipt_id,
        "resource_id": consent.resource_id,
        "consent_expires_at": int(consent_expiry.timestamp()),
        "image_sha256": payload.image_sha256,
        "single_subject": True,
        "subject_age_years": payload.verified_subject_age_years,
        "expires_at": int(receipt_expiry.timestamp()),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(signed_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return {
        "status": "issued",
        "consent_id": consent.consent_id,
        "resource_id": consent.resource_id,
        "consent_expires_at": consent_expiry.isoformat(),
        "expires_at": receipt_expiry.isoformat(),
        "receipt": encoded + "." + signature,
    }


@app.post(
    "/internal/v1/consents/skin-analysis-provider-receipts/verify",
    dependencies=[Depends(require_cil_consent_verifier)],
)
def verify_skin_analysis_provider_consent(
    payload: SkinAnalysisProviderConsentVerifyIn,
    db: Session = Depends(get_db),
):
    """Live revocation/expiry check for CIL immediately before use and before result release."""
    consent = db.get(ConsentReceipt, payload.receipt_id)
    if (
        consent is None
        or consent.scope != "skin_analysis"
        or consent.consent_id != payload.consent_id
        or consent.resource_id != payload.resource_id
        or consent.provider_contributor_token is None
        or not hmac.compare_digest(consent.provider_contributor_token, payload.contributor_token)
        or not consent_is_active(consent)
    ):
        raise HTTPException(403, detail={"code": "SKIN_ANALYSIS_CONSENT_INACTIVE_OR_MISMATCHED"})
    expiry = normalize_utc(consent.expires_at)
    if expiry is None or expiry <= utcnow():
        raise HTTPException(403, detail={"code": "SKIN_ANALYSIS_CONSENT_EXPIRED"})
    return {
        "status": "active",
        "consent_receipt_id": consent.receipt_id,
        "consent_id": consent.consent_id,
        "resource_id": consent.resource_id,
        "contributor_token": consent.provider_contributor_token,
        "image_sha256": payload.image_sha256,
        "consent_expires_at": int(expiry.timestamp()),
    }


@app.post("/v1/tal/consents/{receipt_id}/revoke", dependencies=[Depends(require_internal_token)])
async def revoke_consent(
    receipt_id: str,
    subject_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    subject = subject_or_404(subject_id)
    receipt = db.get(ConsentReceipt, receipt_id)
    if receipt is None or receipt.subject_id != subject:
        raise HTTPException(404, detail={"code": "CONSENT_RECEIPT_NOT_FOUND"})

    selected_receipt_is_active = consent_is_active(receipt)
    affected_receipts: list[ConsentReceipt] = []
    if selected_receipt_is_active:
        statement = select(ConsentReceipt).where(
            ConsentReceipt.subject_id == subject,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        )
        if receipt.resource_id is not None:
            # Resource-bound withdrawal revokes all active scopes in this exact bundle/resource.
            statement = statement.where(
                ConsentReceipt.consent_id == receipt.consent_id,
                ConsentReceipt.resource_id == receipt.resource_id,
            )
        else:
            # Legacy/global withdrawal remains scope-wide and never crosses to another scope.
            statement = statement.where(ConsentReceipt.scope == receipt.scope)
        affected_receipts = list(db.scalars(statement).all())

    revoked_at = utcnow()
    affected_ids = [item.receipt_id for item in affected_receipts]
    if affected_ids:
        db.execute(update(ConsentReceipt).where(
            ConsentReceipt.receipt_id.in_(affected_ids),
            ConsentReceipt.revoked_at.is_(None),
        ).values(revoked_at=revoked_at))
        _delete_inactive_pnelly_conversations(db, subject)

    twin_cleanup_ids: set[str] = set()
    cil_cleanup_ids: set[str] = set()
    if selected_receipt_is_active:
        # Preserve the receipt the user actually withdrew in the outbox. The helper
        # checks the full exact bundle for Twin scopes, so a sibling-scope revocation
        # still triggers cleanup without substituting an unrelated receipt ID.
        twin_cleanup = _queue_twin_consent_cleanup(
            db,
            subject_id=subject,
            consent_id=receipt.consent_id,
            resource_id=receipt.resource_id,
            receipt_id=receipt.receipt_id,
            scope=receipt.scope,
        )
        if twin_cleanup is not None:
            twin_cleanup_ids.add(twin_cleanup.command_id)
        for affected in affected_receipts:
            for cleanup in _queue_cil_provider_consent_cleanup(
                db, affected, revocation_receipt_id=receipt.receipt_id
            ):
                cil_cleanup_ids.add(cleanup.command_id)
    else:
        # A stale retry may re-dispatch the original cleanup command, but it must
        # never withdraw a later active grant for the same subject/scope.
        existing_twin = select(ConsentRevocationOutbox.command_id).where(
            ConsentRevocationOutbox.subject_id == subject,
            ConsentRevocationOutbox.consent_id == receipt.consent_id,
            ConsentRevocationOutbox.resource_id == receipt.resource_id,
        )
        twin_cleanup_ids.update(db.scalars(existing_twin).all())
        existing_cil = select(CILProviderConsentRevocationOutbox.command_id).where(
            CILProviderConsentRevocationOutbox.revocation_receipt_id == receipt.receipt_id,
        )
        cil_cleanup_ids.update(db.scalars(existing_cil).all())

    db.commit()
    twin_result = await _dispatch_twin_consent_revocations_batched(
        db, sorted(twin_cleanup_ids),
    ) if twin_cleanup_ids else _empty_cleanup_dispatch_result()
    cil_result = await _dispatch_cil_provider_consent_revocations_batched(
        db, sorted(cil_cleanup_ids),
    ) if cil_cleanup_ids else _empty_cleanup_dispatch_result()
    db.refresh(receipt)
    return {
        "receipt_id": receipt_id,
        "consent_id": receipt.consent_id,
        "resource_id": receipt.resource_id,
        "status": (
            "revoked" if selected_receipt_is_active
            else (
                "already_revoked" if receipt.revoked_at is not None
                else "already_denied" if not receipt.granted
                else "already_expired"
            )
        ),
        "revoked_at": receipt.revoked_at.isoformat() if receipt.revoked_at else None,
        "twin_cleanup_status": "pending" if twin_result["pending"] or twin_result["failed"] else ("delivered" if twin_result.get("delivered", twin_result["completed"]) else "not_applicable"),
        "cil_provider_cleanup_status": "pending" if cil_result["pending"] or cil_result["failed"] else ("delivered" if cil_result["delivered"] else "not_applicable"),
    }


@app.post("/internal/v1/consent-revocations/dispatch", dependencies=[Depends(require_internal_token)])
async def dispatch_twin_consent_revocations(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return await _dispatch_twin_consent_revocations(db, limit=limit)


@app.post("/internal/v1/cil/provider-consent-revocations/dispatch", dependencies=[Depends(require_internal_token)])
async def dispatch_cil_provider_consent_revocations(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return await _dispatch_cil_provider_consent_revocations(db, limit=limit)




@app.post("/internal/v1/dsi/capture-challenges", dependencies=[Depends(require_dsi_capture_service)])
def create_dsi_capture_challenge(
    payload: DSICaptureChallengeCreate,
    db: Annotated[Session, Depends(get_db)],
):
    """Issue a one-use 256-bit challenge bound to an active, expiring DSI consent bundle.

    The random nonce is returned once to the trusted Vision service. Only its SHA-256
    digest, consent receipt IDs, opaque challenge ID and short expiry are persisted.
    """
    subject = subject_or_404(payload.subject_id)
    now = utcnow()
    required_scopes, receipt_ids, consent_expiry = _active_dsi_capture_consent_bundle(
        db,
        subject_id=subject,
        consent_id=payload.consent_id,
        consent_version=payload.consent_version,
        resource_id=payload.resource_id,
        purpose=payload.purpose,
    )
    expires_at = min(now + timedelta(seconds=DSI_CAPTURE_CHALLENGE_TTL_SECONDS), consent_expiry)
    if expires_at <= now:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_EXPIRED"})

    nonce = secrets.token_bytes(32)
    nonce_b64url = base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii")
    nonce_sha256 = hashlib.sha256(nonce).hexdigest()
    challenge_id = "dsi_challenge_" + uuid.uuid4().hex
    row = DSICaptureChallengeRow(
        challenge_id=challenge_id,
        subject_id=subject,
        consent_id=payload.consent_id,
        consent_version=payload.consent_version,
        resource_id=payload.resource_id,
        purpose=payload.purpose,
        required_scopes=list(required_scopes),
        consent_receipt_ids=receipt_ids,
        nonce_sha256=nonce_sha256,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return _dsi_private_response({
        "status": "issued",
        "challenge_id": challenge_id,
        "nonce_b64url": nonce_b64url,
        "nonce_bytes": 32,
        "nonce_sha256": nonce_sha256,
        "subject_id": subject,
        "consent_id": payload.consent_id,
        "consent_version": payload.consent_version,
        "resource_id": payload.resource_id,
        "purpose": payload.purpose,
        "required_scopes": list(required_scopes),
        "consent_receipt_ids": receipt_ids,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    })


@app.post(
    "/internal/v1/dsi/capture-challenges/{challenge_id}/consume",
    dependencies=[Depends(require_dsi_capture_service)],
)
def consume_dsi_capture_challenge(
    challenge_id: str,
    payload: DSICaptureChallengeConsume,
    db: Annotated[Session, Depends(get_db)],
):
    """Atomically consume one challenge after Vision has verified both Google proofs.

    This persistence endpoint does not parse Android certificates or decode Play
    Integrity tokens. Its dedicated service credential must only be held by the
    Vision verifier, which must complete those checks before invoking this route.
    """
    now = utcnow()
    challenge = db.scalar(
        select(DSICaptureChallengeRow)
        .where(DSICaptureChallengeRow.challenge_id == challenge_id)
        .with_for_update()
    )
    if challenge is None:
        raise HTTPException(404, detail={"code": "DSI_CAPTURE_CHALLENGE_NOT_FOUND"})
    if challenge.consumed_at is not None:
        raise HTTPException(409, detail={"code": "DSI_CAPTURE_CHALLENGE_ALREADY_CONSUMED"})
    if normalize_utc(challenge.expires_at) <= now:
        raise HTTPException(410, detail={"code": "DSI_CAPTURE_CHALLENGE_EXPIRED"})

    nonce = base64.urlsafe_b64decode(payload.nonce_b64url + "=")
    nonce_sha256 = hashlib.sha256(nonce).hexdigest()
    if not hmac.compare_digest(nonce_sha256, challenge.nonce_sha256):
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CHALLENGE_NONCE_MISMATCH"})
    if payload.key_attestation_challenge_sha256 != nonce_sha256:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_ATTESTATION_CHALLENGE_MISMATCH"})

    required_scopes, receipt_ids, consent_expiry = _active_dsi_capture_consent_bundle(
        db,
        subject_id=challenge.subject_id,
        consent_id=challenge.consent_id,
        consent_version=challenge.consent_version,
        resource_id=challenge.resource_id,
        purpose=challenge.purpose,
    )
    if (
        receipt_ids != challenge.consent_receipt_ids
        or list(required_scopes) != challenge.required_scopes
        or consent_expiry <= now
    ):
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_BINDING_CHANGED"})

    receipt_id = "dsi_receipt_" + uuid.uuid4().hex
    receipt_expiry = min(
        now + timedelta(seconds=DSI_CAPTURE_RECEIPT_TTL_SECONDS),
        normalize_utc(challenge.expires_at),
        consent_expiry,
    )
    if receipt_expiry <= now:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_CONSENT_EXPIRED"})

    # The row lock serializes PostgreSQL consumers; the conditional UPDATE is the
    # final compare-and-set guard for concurrent retries and SQLite-backed tests.
    claimed = db.execute(
        update(DSICaptureChallengeRow)
        .where(
            DSICaptureChallengeRow.challenge_id == challenge_id,
            DSICaptureChallengeRow.nonce_sha256 == nonce_sha256,
            DSICaptureChallengeRow.consumed_at.is_(None),
            DSICaptureChallengeRow.expires_at > now,
        )
        .values(consumed_at=now, verification_receipt_id=receipt_id)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail={"code": "DSI_CAPTURE_CHALLENGE_ALREADY_CONSUMED_OR_EXPIRED"})

    receipt = DSICaptureVerificationReceiptRow(
        receipt_id=receipt_id,
        challenge_id=challenge.challenge_id,
        subject_id=challenge.subject_id,
        consent_id=challenge.consent_id,
        consent_version=challenge.consent_version,
        resource_id=challenge.resource_id,
        purpose=challenge.purpose,
        consent_receipt_ids=receipt_ids,
        manifest_sha256=payload.manifest_sha256,
        image_sha256=payload.image_sha256,
        device_pipeline_fingerprint_sha256=payload.device_pipeline_fingerprint_sha256,
        key_attestation_challenge_sha256=payload.key_attestation_challenge_sha256,
        play_integrity_request_hash=payload.play_integrity_request_hash,
        package_name=payload.package_name,
        package_certificate_sha256=payload.package_certificate_sha256,
        app_version=payload.app_version,
        sdk_version=payload.sdk_version,
        verifier_policy_version=payload.verifier_policy_version,
        key_security_level=payload.key_security_level,
        verified_boot_state=payload.verified_boot_state,
        app_recognition_verdict=payload.app_recognition_verdict,
        account_licensing_verdict=payload.account_licensing_verdict,
        device_integrity_verdicts=list(payload.device_integrity_verdicts),
        issued_at=now,
        expires_at=receipt_expiry,
    )
    db.add(receipt)
    db.commit()
    return _dsi_private_response({
        "status": "verified_receipt_created",
        "receipt": _capture_receipt_public_payload(receipt),
    })


@app.post("/internal/v1/dsi/capture-receipts/verify", dependencies=[Depends(require_dsi_capture_service)])
def verify_dsi_capture_receipt(
    payload: DSICaptureReceiptVerify,
    db: Annotated[Session, Depends(get_db)],
):
    """Verify exact receipt scope, content digests, expiry and current consent."""
    receipt = db.get(DSICaptureVerificationReceiptRow, payload.receipt_id)
    if receipt is None:
        raise HTTPException(404, detail={"code": "DSI_CAPTURE_RECEIPT_NOT_FOUND"})
    now = utcnow()
    if normalize_utc(receipt.expires_at) <= now:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_EXPIRED"})
    exact = (
        receipt.subject_id == subject_or_404(payload.subject_id)
        and receipt.resource_id == payload.resource_id
        and receipt.purpose == payload.purpose
        and hmac.compare_digest(receipt.manifest_sha256, payload.manifest_sha256)
        and hmac.compare_digest(receipt.image_sha256, payload.image_sha256)
        and hmac.compare_digest(receipt.device_pipeline_fingerprint_sha256, payload.device_pipeline_fingerprint_sha256)
    )
    if not exact:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_SCOPE_OR_DIGEST_MISMATCH"})
    required_scopes, receipt_ids, consent_expiry = _active_dsi_capture_consent_bundle(
        db,
        subject_id=receipt.subject_id,
        consent_id=receipt.consent_id,
        consent_version=receipt.consent_version,
        resource_id=receipt.resource_id,
        purpose=receipt.purpose,
    )
    if receipt_ids != receipt.consent_receipt_ids or consent_expiry <= now:
        raise HTTPException(403, detail={"code": "DSI_CAPTURE_RECEIPT_CONSENT_REVOKED_OR_CHANGED"})
    return _dsi_private_response({
        "verified": True,
        "required_scopes": list(required_scopes),
        "receipt": _capture_receipt_public_payload(receipt),
        "checked_at": now.isoformat(),
    })


@app.post("/internal/v1/consents/verify", dependencies=[Depends(require_internal_token)])
def verify_resource_bound_consent(payload: ConsentVerify, db: Annotated[Session, Depends(get_db)]):
    """Verify a complete consent bundle for one trusted subject and exact resource."""
    subject = subject_or_404(payload.subject_id)
    statement = select(ConsentReceipt).where(
        ConsentReceipt.subject_id == subject,
        ConsentReceipt.consent_id == payload.consent_id,
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        active_consent_predicate(),
    )
    if payload.resource_id is None:
        statement = statement.where(ConsentReceipt.resource_id.is_(None))
    else:
        statement = statement.where(ConsentReceipt.resource_id == payload.resource_id)
    if payload.consent_version is not None:
        statement = statement.where(ConsentReceipt.consent_version == payload.consent_version)
    rows = list(db.scalars(statement).all())
    granted = {row.scope for row in rows}
    missing = sorted(set(payload.required_scopes) - granted)
    if missing:
        raise HTTPException(
            403,
            detail={"code": "CONSENT_BUNDLE_INCOMPLETE", "missing_scopes": missing},
        )
    required_rows = [row for row in rows if row.scope in payload.required_scopes]
    if payload.require_expiring and any(row.expires_at is None for row in required_rows):
        raise HTTPException(403, detail={"code": "CONSENT_EXPIRY_REQUIRED"})
    versions = {row.consent_version for row in required_rows}
    if len(versions) != 1:
        raise HTTPException(403, detail={"code": "CONSENT_VERSION_MISMATCH"})
    return {
        "verified": True,
        "active": True,
        "subject_id": subject,
        "consent_id": payload.consent_id,
        "resource_id": payload.resource_id,
        "consent_version": next(iter(versions)),
        "expires_at": min((row.expires_at for row in required_rows), default=None).isoformat() if required_rows and all(row.expires_at is not None for row in required_rows) else None,
        "granted_scopes": sorted(granted),
        "receipt_ids": sorted(row.receipt_id for row in required_rows),
    }


def _delete_inactive_pnelly_conversations(db: Session, subject_id: str | None = None) -> int:
    statement = select(PnellyConversation)
    if subject_id is not None:
        statement = statement.where(PnellyConversation.subject_id == subject_id)
    rows = list(db.scalars(statement).all())
    deleted = 0
    for row in rows:
        receipt = db.get(ConsentReceipt, row.consent_receipt_id)
        if (
            normalize_utc(row.expires_at) <= utcnow()
            or receipt is None
            or receipt.scope != "pnelly_conversation"
            or not consent_is_active(receipt)
        ):
            db.delete(row)
            deleted += 1
    return deleted


def _queue_cil_provider_consent_cleanup(
    db: Session,
    consent: ConsentReceipt,
    *,
    revocation_receipt_id: str | None = None,
) -> list[CILProviderConsentRevocationOutbox]:
    """Queue provider cleanup for the exact skin-analysis consent bundle being withdrawn."""
    if consent.resource_id is not None:
        skin_receipts = list(db.scalars(select(ConsentReceipt).where(
            ConsentReceipt.subject_id == consent.subject_id,
            ConsentReceipt.consent_id == consent.consent_id,
            ConsentReceipt.resource_id == consent.resource_id,
            ConsentReceipt.scope == "skin_analysis",
            ConsentReceipt.granted.is_(True),
        )).all())
    elif consent.scope == "skin_analysis":
        skin_receipts = [consent]
    else:
        return []

    queued: list[CILProviderConsentRevocationOutbox] = []
    for skin_receipt in skin_receipts:
        event_receipt_id = revocation_receipt_id or consent.receipt_id
        # Canonical JSON framing prevents delimiter collisions between valid IDs.
        digest_source = json.dumps({
            "version": 2,
            "revocation_receipt_id": event_receipt_id,
            "consent_receipt_id": skin_receipt.receipt_id,
            "consent_id": skin_receipt.consent_id,
            "resource_id": skin_receipt.resource_id,
            "contributor_token": skin_receipt.provider_contributor_token,
        }, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        command_id = "cil-provider-consent-revocation:" + digest
        pending = next(
            (item for item in db.new
             if isinstance(item, CILProviderConsentRevocationOutbox) and item.command_id == command_id),
            None,
        )
        if pending is not None:
            queued.append(pending)
            continue
        existing = db.get(CILProviderConsentRevocationOutbox, command_id)
        if existing is not None:
            queued.append(existing)
            continue
        row = CILProviderConsentRevocationOutbox(
            command_id=command_id,
            revocation_receipt_id=event_receipt_id,
            consent_id=skin_receipt.consent_id,
            resource_id=skin_receipt.resource_id,
            receipt_id=skin_receipt.receipt_id,
            contributor_token=skin_receipt.provider_contributor_token,
            status="pending",
            attempts=0,
        )
        db.add(row)
        queued.append(row)
    return queued


def _cil_provider_config() -> tuple[str, str] | None:
    base = os.getenv("CIL_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("CIL_SERVICE_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32:
        return None
    try:
        parsed = urlsplit(base)
        host = (parsed.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        if (
            not host or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
        ):
            return None
    except ValueError:
        return None
    return base, token


async def _notify_cil_provider_of_consent_revocation(
    item: CILProviderConsentRevocationOutbox,
) -> dict:
    config = _cil_provider_config()
    if config is None:
        raise RuntimeError("CIL_PROVIDER_REVOCATION_NOT_CONFIGURED")
    base, token = config
    payload = {
        "consent_id": item.consent_id,
        "revocation_reference": item.command_id,
    }
    if item.contributor_token is not None:
        payload["contributor_token"] = item.contributor_token
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                base + "/providers/perfectcorp/revoke-consent",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("CIL_PROVIDER_REVOCATION_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("CIL_PROVIDER_REVOCATION_UNAVAILABLE") from exc
    if response.status_code != 200:
        raise RuntimeError("CIL_PROVIDER_REVOCATION_REJECTED")
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("CIL_PROVIDER_REVOCATION_INVALID_RESPONSE") from exc
    counts = ("matched_tasks", "deleted_tasks", "waiting_for_terminal")
    if (
        not isinstance(result, dict)
        or result.get("revoked") is not True
        or result.get("consent_id") != item.consent_id
        or result.get("revocation_reference") != item.command_id
        or any(type(result.get(name)) is not int or result[name] < 0 for name in counts)
    ):
        raise RuntimeError("CIL_PROVIDER_REVOCATION_INVALID_RESPONSE")
    return result


async def _dispatch_cil_provider_consent_revocations(
    db: Session,
    limit: int = 20,
    command_ids: list[str] | None = None,
) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(422, detail={"code": "INVALID_CIL_PROVIDER_REVOCATION_BATCH_SIZE"})
    if command_ids is not None and (
        not command_ids or len(command_ids) > 100 or len(command_ids) != len(set(command_ids))
    ):
        raise HTTPException(422, detail={"code": "INVALID_CIL_PROVIDER_REVOCATION_COMMAND_SET"})
    statement = select(CILProviderConsentRevocationOutbox).where(
        CILProviderConsentRevocationOutbox.status == "pending"
    )
    if command_ids is not None:
        statement = statement.where(CILProviderConsentRevocationOutbox.command_id.in_(command_ids))
    pending_rows = db.scalars(
        statement.order_by(CILProviderConsentRevocationOutbox.created_at).limit(limit)
    ).all()
    completed = failed = 0
    for item in pending_rows:
        try:
            result = await _notify_cil_provider_of_consent_revocation(item)
            item.matched_tasks = result["matched_tasks"]
            item.deleted_tasks = result["deleted_tasks"]
            item.waiting_for_terminal = result["waiting_for_terminal"]
            item.status = "delivered"
            item.last_error_code = None
            item.completed_at = utcnow()
            completed += 1
        except RuntimeError as exc:
            item.attempts += 1
            item.last_error_code = str(exc)[:80]
            failed += 1
        except Exception:
            item.attempts += 1
            item.last_error_code = "CIL_PROVIDER_REVOCATION_FAILED"
            failed += 1
    db.commit()
    remaining_statement = select(CILProviderConsentRevocationOutbox.command_id).where(
        CILProviderConsentRevocationOutbox.status == "pending"
    )
    if command_ids is not None:
        remaining_statement = remaining_statement.where(
            CILProviderConsentRevocationOutbox.command_id.in_(command_ids)
        )
    remaining = db.scalar(remaining_statement.limit(1))
    already_delivered = 0
    if command_ids is not None:
        delivered_rows = db.scalars(select(CILProviderConsentRevocationOutbox).where(
            CILProviderConsentRevocationOutbox.command_id.in_(command_ids),
            CILProviderConsentRevocationOutbox.status == "delivered",
        )).all()
        already_delivered = max(0, len(delivered_rows) - completed)
    return {
        "processed": len(pending_rows),
        "completed": completed,
        "already_delivered": already_delivered,
        "delivered": completed + already_delivered,
        "failed": failed,
        "pending": remaining is not None,
    }


TWIN_CONSENT_SCOPES = {"body_measurements", "virtual_twin_storage"}
TWIN_CONSENT_EXPIRY_SCOPES = TWIN_CONSENT_SCOPES | {"image_processing"}


def _queue_twin_consent_cleanup(
    db: Session, *, subject_id: str, consent_id: str, resource_id: str | None,
    receipt_id: str, scope: str,
) -> ConsentRevocationOutbox | None:
    """Persist a cleanup command in the same transaction as resource consent withdrawal."""
    if resource_id is None:
        return None
    # Withdrawal of any receipt in a bundle revokes the entire exact-resource
    # bundle. Queue Twin cleanup when that bundle contains any Twin scope,
    # regardless of which receipt the user selected for revocation.
    twin_scope_receipt = db.scalar(select(ConsentReceipt.receipt_id).where(
        ConsentReceipt.subject_id == subject_id,
        ConsentReceipt.consent_id == consent_id,
        ConsentReceipt.resource_id == resource_id,
        ConsentReceipt.scope.in_(TWIN_CONSENT_SCOPES),
    ).limit(1))
    if twin_scope_receipt is None:
        return None
    digest = hashlib.sha256(
        f"{subject_id}:{consent_id}:{resource_id}".encode("utf-8")
    ).hexdigest()
    command_id = "twin-consent-revocation:" + digest
    # autoflush is disabled for this service. A previous scope in the same
    # consent bundle may already have queued this command but not committed it.
    pending = next(
        (item for item in db.new
         if isinstance(item, ConsentRevocationOutbox) and item.command_id == command_id),
        None,
    )
    if pending is not None:
        return pending
    existing = db.get(ConsentRevocationOutbox, command_id)
    if existing is not None:
        return existing
    row = ConsentRevocationOutbox(
        command_id=command_id,
        subject_id=subject_id,
        consent_id=consent_id,
        resource_id=resource_id,
        receipt_id=receipt_id,
        status="pending",
        attempts=0,
    )
    db.add(row)
    return row


def _twin_registry_config() -> tuple[str, str] | None:
    base = os.getenv("TWIN_REGISTRY_API_URL", "").strip().rstrip("/")
    token = os.getenv("TWIN_REGISTRY_API_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32:
        return None
    try:
        parsed = urlsplit(base)
        host = (parsed.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        if (
            not host or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
        ):
            return None
    except ValueError:
        return None
    return base, token


async def _notify_twin_registry_of_revocation(
    item: ConsentRevocationOutbox,
) -> dict:
    config = _twin_registry_config()
    if config is None:
        raise RuntimeError("TWIN_REGISTRY_NOT_CONFIGURED")
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(6.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                base + "/internal/v1/twins/revoke-consent",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={
                    "subject_id": item.subject_id,
                    "consent_id": item.consent_id,
                    "resource_id": item.resource_id,
                    "command_id": item.command_id,
                },
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("TWIN_REGISTRY_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("TWIN_REGISTRY_UNAVAILABLE") from exc
    if response.status_code not in {200, 202}:
        raise RuntimeError("TWIN_REGISTRY_REJECTED_REVOCATION")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("TWIN_REGISTRY_INVALID_RESPONSE") from exc
    queued = payload.get("twins_queued") if isinstance(payload, dict) else None
    status = payload.get("status") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or status not in {"pending", "complete"}
        or isinstance(queued, bool)
        or not isinstance(queued, int)
        or queued < 0
    ):
        raise RuntimeError("TWIN_REGISTRY_INVALID_RESPONSE")
    return payload


async def _dispatch_twin_consent_revocations(
    db: Session,
    limit: int = 20,
    command_ids: list[str] | None = None,
) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(422, detail={"code": "INVALID_TWIN_REVOCATION_BATCH_SIZE"})
    if command_ids is not None and (
        not command_ids or len(command_ids) > 100 or len(command_ids) != len(set(command_ids))
    ):
        raise HTTPException(422, detail={"code": "INVALID_TWIN_REVOCATION_COMMAND_SET"})
    statement = select(ConsentRevocationOutbox).where(
        ConsentRevocationOutbox.status == "pending"
    )
    if command_ids is not None:
        statement = statement.where(ConsentRevocationOutbox.command_id.in_(command_ids))
    pending = db.scalars(
        statement.order_by(ConsentRevocationOutbox.created_at).limit(limit)
    ).all()
    completed = failed = 0
    for item in pending:
        try:
            await _notify_twin_registry_of_revocation(item)
            item.status = "delivered"
            item.last_error_code = None
            item.completed_at = utcnow()
            completed += 1
        except RuntimeError as exc:
            item.attempts += 1
            item.last_error_code = str(exc)[:80]
            failed += 1
        except Exception:
            item.attempts += 1
            item.last_error_code = "TWIN_REGISTRY_NOTIFICATION_FAILED"
            failed += 1
    db.commit()
    remaining_statement = select(ConsentRevocationOutbox.command_id).where(
        ConsentRevocationOutbox.status == "pending"
    )
    if command_ids is not None:
        remaining_statement = remaining_statement.where(
            ConsentRevocationOutbox.command_id.in_(command_ids)
        )
    remaining = db.scalar(remaining_statement.limit(1))
    already_delivered = 0
    if command_ids is not None:
        delivered_rows = db.scalars(select(ConsentRevocationOutbox).where(
            ConsentRevocationOutbox.command_id.in_(command_ids),
            ConsentRevocationOutbox.status == "delivered",
        )).all()
        already_delivered = max(0, len(delivered_rows) - completed)
    return {
        "processed": len(pending),
        "completed": completed,
        "already_delivered": already_delivered,
        "delivered": completed + already_delivered,
        "failed": failed,
        "pending": remaining is not None,
    }


def _empty_cleanup_dispatch_result() -> dict[str, int | bool]:
    return {
        "processed": 0, "completed": 0, "already_delivered": 0,
        "delivered": 0, "failed": 0, "pending": False,
    }


async def _dispatch_cil_provider_consent_revocations_batched(
    db: Session, command_ids: list[str],
) -> dict:
    """Dispatch arbitrarily large deletion/revocation sets in provider-safe batches."""
    ids = sorted(set(command_ids))
    total = _empty_cleanup_dispatch_result()
    for offset in range(0, len(ids), 100):
        batch = ids[offset:offset + 100]
        result = await _dispatch_cil_provider_consent_revocations(db, limit=len(batch), command_ids=batch)
        for key in ("processed", "completed", "already_delivered", "delivered", "failed"):
            total[key] += result[key]
        total["pending"] = bool(total["pending"] or result["pending"])
    return total


async def _dispatch_twin_consent_revocations_batched(
    db: Session, command_ids: list[str],
) -> dict:
    """Dispatch Twin cleanup in the same bounded batches as CIL provider cleanup."""
    ids = sorted(set(command_ids))
    total = _empty_cleanup_dispatch_result()
    for offset in range(0, len(ids), 100):
        batch = ids[offset:offset + 100]
        result = await _dispatch_twin_consent_revocations(db, limit=len(batch), command_ids=batch)
        for key in ("processed", "completed", "already_delivered", "delivered", "failed"):
            total[key] += result[key]
        total["pending"] = bool(total["pending"] or result["pending"])
    return total


def _pnelly_conversation_json(row: PnellyConversation) -> dict:
    return {
        "conversation_id": row.conversation_id,
        "state_version": row.state_version,
        "context": row.context,
        "expires_at": normalize_utc(row.expires_at).isoformat(),
        "created_at": normalize_utc(row.created_at).isoformat(),
        "updated_at": normalize_utc(row.updated_at).isoformat(),
    }


def _active_pnelly_conversation(db: Session, subject_id: str, conversation_id: str) -> PnellyConversation:
    row = db.get(PnellyConversation, conversation_id)
    if row is None or row.subject_id != subject_id:
        raise HTTPException(404, detail={"code": "PNELLY_CONVERSATION_NOT_FOUND"})
    receipt = db.get(ConsentReceipt, row.consent_receipt_id)
    if (
        normalize_utc(row.expires_at) <= utcnow()
        or receipt is None
        or receipt.subject_id != subject_id
        or receipt.scope != "pnelly_conversation"
        or receipt.resource_id != conversation_id
        or not consent_is_active(receipt)
    ):
        db.delete(row)
        db.commit()
        raise HTTPException(403, detail={"code": "ACTIVE_PNELLY_CONVERSATION_CONSENT_REQUIRED"})
    return row


@app.post("/v1/pnelly/conversations", dependencies=[Depends(require_internal_token)])
def create_pnelly_conversation(
    subject_id: str = Query(min_length=1, max_length=128),
    payload: PnellyConversationCreate = None,
    db: Session = Depends(get_db),
):
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "PNELLY_CONVERSATION_REQUIRED"})
    receipt = db.get(ConsentReceipt, payload.consent_receipt_id)
    if (
        receipt is None or receipt.subject_id != subject
        or receipt.scope != "pnelly_conversation"
        or receipt.resource_id != payload.conversation_id
        or not consent_is_active(receipt)
    ):
        raise HTTPException(403, detail={"code": "ACTIVE_PNELLY_CONVERSATION_CONSENT_REQUIRED"})
    expiry = normalize_utc(receipt.expires_at)
    now = utcnow()
    if expiry is None or expiry > now + timedelta(hours=24):
        raise HTTPException(422, detail={"code": "PNELLY_CONVERSATION_EXPIRY_MUST_BE_WITHIN_24_HOURS"})
    existing = db.get(PnellyConversation, payload.conversation_id)
    if existing is not None:
        if existing.subject_id == subject and existing.consent_receipt_id == receipt.receipt_id:
            return {"status": "replayed", **_pnelly_conversation_json(existing)}
        raise HTTPException(409, detail={"code": "PNELLY_CONVERSATION_ID_CONFLICT"})
    row = PnellyConversation(
        conversation_id=payload.conversation_id,
        subject_id=subject,
        consent_receipt_id=receipt.receipt_id,
        state_version=0,
        context={},
        expires_at=expiry,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "PNELLY_CONVERSATION_CREATE_CONFLICT"}) from exc
    return {"status": "created", **_pnelly_conversation_json(row)}


@app.get("/v1/pnelly/conversations/{conversation_id}", dependencies=[Depends(require_internal_token)])
def get_pnelly_conversation(
    conversation_id: str,
    subject_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    row = _active_pnelly_conversation(db, subject_or_404(subject_id), conversation_id)
    return {"status": "active", **_pnelly_conversation_json(row)}


@app.put("/v1/pnelly/conversations/{conversation_id}", dependencies=[Depends(require_internal_token)])
def update_pnelly_conversation(
    conversation_id: str,
    payload: PnellyConversationUpdate,
    subject_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    subject = subject_or_404(subject_id)
    row = _active_pnelly_conversation(db, subject, conversation_id)
    normalized_context = payload.context.model_dump(mode="json")
    canonical = json.dumps(
        {"turn_id": payload.turn_id, "context": normalized_context},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if row.last_turn_id == payload.turn_id:
        if row.last_turn_hash == digest:
            return {"status": "replayed", **_pnelly_conversation_json(row)}
        raise HTTPException(409, detail={"code": "PNELLY_CONVERSATION_TURN_CONFLICT"})
    if row.state_version != payload.expected_version:
        raise HTTPException(409, detail={
            "code": "PNELLY_CONVERSATION_VERSION_CONFLICT",
            "current_version": row.state_version,
        })
    row.context = normalized_context
    row.state_version += 1
    row.last_turn_id = payload.turn_id
    row.last_turn_hash = digest
    row.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "PNELLY_CONVERSATION_CONCURRENT_UPDATE"}) from exc
    return {"status": "updated", **_pnelly_conversation_json(row)}


@app.delete("/v1/pnelly/conversations/{conversation_id}", dependencies=[Depends(require_internal_token)])
def delete_pnelly_conversation(
    conversation_id: str,
    subject_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    subject = subject_or_404(subject_id)
    row = db.get(PnellyConversation, conversation_id)
    if row is None or row.subject_id != subject:
        raise HTTPException(404, detail={"code": "PNELLY_CONVERSATION_NOT_FOUND"})
    receipt = db.get(ConsentReceipt, row.consent_receipt_id)
    if receipt is not None and receipt.granted and receipt.revoked_at is None:
        db.execute(update(ConsentReceipt).where(
            ConsentReceipt.subject_id == subject,
            ConsentReceipt.consent_id == receipt.consent_id,
            ConsentReceipt.resource_id == conversation_id,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        ).values(revoked_at=utcnow()))
    db.delete(row)
    db.commit()
    if receipt is not None:
        db.refresh(receipt)
    consent_inactive = receipt is None or not consent_is_active(receipt)
    return {
        "status": "deleted",
        "conversation_id": conversation_id,
        "consent_inactive": consent_inactive,
    }


@app.post("/v1/tal/events", dependencies=[Depends(require_internal_token)])
def append_event(subject_id: str = Query(min_length=1, max_length=128), payload: EventPut = None, db: Session = Depends(get_db)):
    subject = subject_or_404(subject_id)
    if payload is None:
        raise HTTPException(422, detail={"code": "TAL_EVENT_REQUIRED"})
    consent = db.get(ConsentReceipt, payload.consent_receipt_id)
    if consent is None or consent.subject_id != subject or not consent_is_active(consent) or consent.scope not in {"personalization", "style_learning"}:
        raise HTTPException(403, detail={"code": "ACTIVE_TAL_CONSENT_REQUIRED"})
    digest = _event_hash(payload)
    existing = db.get(TALEvent, payload.event_id)
    if existing is not None:
        if existing.subject_id == subject and existing.payload_hash == digest:
            return {"status": "replayed", "event_id": existing.event_id}
        raise HTTPException(409, detail={"code": "TAL_EVENT_ID_CONFLICT"})
    prior = db.scalar(select(TALEvent).where(TALEvent.subject_id == subject, TALEvent.idempotency_key == payload.idempotency_key))
    if prior is not None:
        if prior.payload_hash == digest:
            return {"status": "replayed", "event_id": prior.event_id}
        raise HTTPException(409, detail={"code": "TAL_IDEMPOTENCY_CONFLICT"})
    if payload.event_kind == "correction":
        target = db.get(TALEvent, payload.supersedes_event_id)
        if target is None or target.subject_id != subject:
            raise HTTPException(404, detail={"code": "TAL_CORRECTION_TARGET_NOT_FOUND"})
        if target.feature_key != payload.feature_key:
            raise HTTPException(409, detail={"code": "TAL_CORRECTION_FEATURE_MISMATCH"})
    row = TALEvent(
        event_id=payload.event_id, subject_id=subject, consent_receipt_id=payload.consent_receipt_id,
        idempotency_key=payload.idempotency_key, payload_hash=digest, feature_key=payload.feature_key,
        value=payload.value, event_kind=payload.event_kind, supersedes_event_id=payload.supersedes_event_id,
        observed_at=parse_time(payload.observed_at), expires_at=parse_time(payload.expires_at) if payload.expires_at else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"code": "TAL_CONCURRENT_IDEMPOTENCY_CONFLICT"})
    return {"status": "recorded", "event_id": row.event_id, "durable_persistence": True}


@app.get("/v1/tal/export/{subject_id}", dependencies=[Depends(require_internal_token)])
def export_events(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    events = list(db.scalars(select(TALEvent).where(TALEvent.subject_id == subject).order_by(TALEvent.observed_at, TALEvent.event_id)).all())
    consents = list(db.scalars(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject).order_by(ConsentReceipt.created_at)).all())
    profile = db.get(USIProfileRow, subject)
    color_profile = db.get(ColorProfileRow, subject)
    _delete_inactive_pnelly_conversations(db, subject)
    conversations = list(db.scalars(select(PnellyConversation).where(
        PnellyConversation.subject_id == subject
    ).order_by(PnellyConversation.created_at)).all())
    return {
        "subject_id": subject,
        "profile": {"profile_version": profile.profile_version, "preferences": profile.preferences} if profile else None,
        "color_profile": {"profile_version": color_profile.profile_version, "liked_colors": color_profile.liked_colors, "disliked_colors": color_profile.disliked_colors, "best_version_colors": color_profile.best_version_colors} if color_profile else None,
        "consent_receipts": [{
            "receipt_id": x.receipt_id, "consent_id": x.consent_id,
            "resource_id": x.resource_id, "scope": x.scope,
            "consent_version": x.consent_version, "granted": x.granted,
            "granted_at": x.granted_at.isoformat() if x.granted_at else None,
            "expires_at": x.expires_at.isoformat() if x.expires_at else None,
            "revoked_at": x.revoked_at.isoformat() if x.revoked_at else None,
        } for x in consents],
        "events": [{"event_id": x.event_id, "feature_key": x.feature_key, "value": x.value, "event_kind": x.event_kind, "supersedes_event_id": x.supersedes_event_id, "observed_at": x.observed_at.isoformat(), "expires_at": x.expires_at.isoformat() if x.expires_at else None, "consent_receipt_id": x.consent_receipt_id} for x in events],
        "pnelly_conversations": [_pnelly_conversation_json(x) for x in conversations],
    }


@app.delete("/v1/tal/users/{subject_id}", dependencies=[Depends(require_internal_token)])
async def delete_user_data(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    event_ids = list(db.scalars(select(TALEvent.event_id).where(TALEvent.subject_id == subject)).all())
    conversation_ids = list(db.scalars(select(PnellyConversation.conversation_id).where(
        PnellyConversation.subject_id == subject
    )).all())
    consents = list(db.scalars(
        select(ConsentReceipt)
        .where(ConsentReceipt.subject_id == subject)
        .order_by(ConsentReceipt.created_at, ConsentReceipt.receipt_id)
    ).all())
    twin_cleanup_command_ids: set[str] = set()
    cil_cleanup_command_ids: set[str] = set()
    cil_cleanup_bundles: set[tuple[str, str | None]] = set()
    for consent in consents:
        cleanup = _queue_twin_consent_cleanup(
            db,
            subject_id=subject,
            consent_id=consent.consent_id,
            resource_id=consent.resource_id,
            receipt_id=consent.receipt_id,
            scope=consent.scope,
        )
        if cleanup is not None:
            twin_cleanup_command_ids.add(cleanup.command_id)
        bundle_key = (consent.consent_id, consent.resource_id)
        if bundle_key not in cil_cleanup_bundles:
            cil_cleanup_bundles.add(bundle_key)
            for cil_cleanup in _queue_cil_provider_consent_cleanup(
                db, consent, revocation_receipt_id=consent.receipt_id
            ):
                cil_cleanup_command_ids.add(cil_cleanup.command_id)
    twin_cleanup_commands = len(twin_cleanup_command_ids)
    cil_cleanup_commands = len(cil_cleanup_command_ids)
    profile = db.get(USIProfileRow, subject)
    # DSI capture receipts bind images and measurements to consent. User deletion
    # removes these short-lived verification records before removing consent rows.
    db.execute(delete(DSICaptureVerificationReceiptRow).where(DSICaptureVerificationReceiptRow.subject_id == subject))
    db.execute(delete(DSICaptureChallengeRow).where(DSICaptureChallengeRow.subject_id == subject))
    db.execute(delete(PnellyConversation).where(PnellyConversation.subject_id == subject))
    db.execute(delete(TALEvent).where(TALEvent.subject_id == subject))
    db.execute(delete(ConsentReceipt).where(ConsentReceipt.subject_id == subject))
    if profile is not None:
        db.delete(profile)
    color_profile = db.get(ColorProfileRow, subject)
    if color_profile is not None:
        db.delete(color_profile)
    receipt = TALDeletionReceipt(
        receipt_id=str(uuid.uuid4()), subject_digest=hashlib.sha256(subject.encode()).hexdigest(),
        deleted_event_count=len(event_ids), deleted_profile=profile is not None,
    )
    db.add(receipt)
    db.commit()
    cleanup_result = await _dispatch_twin_consent_revocations_batched(
        db, sorted(twin_cleanup_command_ids),
    ) if twin_cleanup_commands else _empty_cleanup_dispatch_result()
    cil_cleanup_result = await _dispatch_cil_provider_consent_revocations_batched(
        db, sorted(cil_cleanup_command_ids),
    ) if cil_cleanup_commands else _empty_cleanup_dispatch_result()
    return {
        "status": "deleted",
        "deleted_events": len(event_ids),
        "deleted_pnelly_conversations": len(conversation_ids),
        "deleted_profile": profile is not None,
        "deleted_color_profile": color_profile is not None,
        "deletion_receipt_id": receipt.receipt_id,
        "twin_cleanup_commands": twin_cleanup_commands,
        "twin_cleanup_processed": cleanup_result["processed"],
        "twin_cleanup_delivered": cleanup_result["completed"],
        "twin_cleanup_failed": cleanup_result["failed"],
        "twin_cleanup_pending": cleanup_result["pending"] or cleanup_result["failed"] > 0,
        "cil_provider_cleanup_commands": cil_cleanup_commands,
        "cil_provider_cleanup_processed": cil_cleanup_result["processed"],
        "cil_provider_cleanup_delivered": cil_cleanup_result["completed"],
        "cil_provider_cleanup_failed": cil_cleanup_result["failed"],
        "cil_provider_cleanup_pending": cil_cleanup_result["pending"] or cil_cleanup_result["failed"] > 0,
    }


@app.post("/internal/retention/purge", dependencies=[Depends(require_internal_token)])
async def purge_expired(db: Annotated[Session, Depends(get_db)], cron_token: Annotated[str | None, Header(alias="X-Identity-Cron-Token")] = None):
    expected = os.getenv("IDENTITY_CRON_TOKEN", "").strip()
    if len(expected.encode()) < 32 or not cron_token or not hmac.compare_digest(expected, cron_token):
        raise HTTPException(401, detail={"code": "RETENTION_CRON_AUTH_FAILED"})
    now = utcnow()
    expired_resource_consents = list(db.scalars(select(ConsentReceipt).where(
        ConsentReceipt.scope.in_(TWIN_CONSENT_EXPIRY_SCOPES | {"skin_analysis"}),
        ConsentReceipt.resource_id.is_not(None),
        ConsentReceipt.granted.is_(True),
        ConsentReceipt.revoked_at.is_(None),
        ConsentReceipt.expires_at.is_not(None),
        ConsentReceipt.expires_at <= now,
    )).all())
    twin_cleanup_command_ids: set[str] = set()
    cil_cleanup_command_ids: set[str] = set()
    expired_bundle_keys: set[tuple[str, str, str]] = set()
    expired_receipt_ids: set[str] = set()

    for seed in expired_resource_consents:
        bundle_key = (seed.subject_id, seed.consent_id, seed.resource_id)
        if bundle_key in expired_bundle_keys:
            continue
        expired_bundle_keys.add(bundle_key)
        # Expiry is equivalent to withdrawal: once one resource-bound scope in
        # the bundle expires, revoke every active scope for this exact subject,
        # consent ID and resource in the same transaction.
        bundle_receipts = list(db.scalars(select(ConsentReceipt).where(
            ConsentReceipt.subject_id == seed.subject_id,
            ConsentReceipt.consent_id == seed.consent_id,
            ConsentReceipt.resource_id == seed.resource_id,
            ConsentReceipt.granted.is_(True),
            ConsentReceipt.revoked_at.is_(None),
        )).all())
        for affected in bundle_receipts:
            expired_receipt_ids.add(affected.receipt_id)
            twin_cleanup = _queue_twin_consent_cleanup(
                db,
                subject_id=affected.subject_id,
                consent_id=affected.consent_id,
                resource_id=affected.resource_id,
                receipt_id=affected.receipt_id,
                scope=affected.scope,
            )
            if twin_cleanup is not None:
                twin_cleanup_command_ids.add(twin_cleanup.command_id)
            for cleanup in _queue_cil_provider_consent_cleanup(
                db, affected, revocation_receipt_id=seed.receipt_id
            ):
                cil_cleanup_command_ids.add(cleanup.command_id)

    if expired_receipt_ids:
        db.execute(update(ConsentReceipt).where(
            ConsentReceipt.receipt_id.in_(sorted(expired_receipt_ids)),
            ConsentReceipt.revoked_at.is_(None),
        ).values(revoked_at=now))
    twin_cleanup_commands = len(twin_cleanup_command_ids)
    cil_cleanup_commands = len(cil_cleanup_command_ids)
    result = db.execute(delete(TALEvent).where(TALEvent.expires_at.is_not(None), TALEvent.expires_at <= now))
    expired_receipts = db.execute(
        delete(DSICaptureVerificationReceiptRow).where(DSICaptureVerificationReceiptRow.expires_at <= now)
    )
    expired_challenges = db.execute(
        delete(DSICaptureChallengeRow).where(DSICaptureChallengeRow.expires_at <= now)
    )
    expired_conversations = _delete_inactive_pnelly_conversations(db)
    db.commit()
    # Every scheduled retention run also retries older durable cleanup commands
    # whose first notification failed; retries must not depend on another consent event.
    cleanup_result = await _dispatch_twin_consent_revocations(db, limit=100)
    cil_cleanup_result = await _dispatch_cil_provider_consent_revocations(db, limit=100)
    return {
        "status": "complete",
        "purged_events": result.rowcount or 0,
        "purged_pnelly_conversations": expired_conversations,
        "purged_dsi_capture_challenges": expired_challenges.rowcount or 0,
        "purged_dsi_capture_receipts": expired_receipts.rowcount or 0,
        "twin_cleanup_commands": twin_cleanup_commands,
        "twin_cleanup_processed": cleanup_result["processed"],
        "twin_cleanup_delivered": cleanup_result["completed"],
        "twin_cleanup_failed": cleanup_result["failed"],
        "twin_cleanup_pending": cleanup_result["pending"] or cleanup_result["failed"] > 0,
        "cil_provider_cleanup_commands": cil_cleanup_commands,
        "cil_provider_cleanup_processed": cil_cleanup_result["processed"],
        "cil_provider_cleanup_delivered": cil_cleanup_result["completed"],
        "cil_provider_cleanup_failed": cil_cleanup_result["failed"],
        "cil_provider_cleanup_pending": cil_cleanup_result["pending"] or cil_cleanup_result["failed"] > 0,
    }


@app.get("/v1/tal/consents/{subject_id}", dependencies=[Depends(require_internal_token)])
def list_consents(subject_id: str, db: Annotated[Session, Depends(get_db)]):
    subject = subject_or_404(subject_id)
    rows = list(db.scalars(select(ConsentReceipt).where(ConsentReceipt.subject_id == subject).order_by(ConsentReceipt.created_at)).all())
    return [{
        "receipt_id": x.receipt_id, "consent_id": x.consent_id,
        "resource_id": x.resource_id, "scope": x.scope,
        "consent_version": x.consent_version, "granted": x.granted,
        "granted_at": x.granted_at.isoformat() if x.granted_at else None,
        "expires_at": x.expires_at.isoformat() if x.expires_at else None,
        "revoked_at": x.revoked_at.isoformat() if x.revoked_at else None,
    } for x in rows]

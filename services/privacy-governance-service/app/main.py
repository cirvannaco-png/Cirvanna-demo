"""Cirvanna Privacy Governance Service.

Owns purpose-bound consent receipts, legally signed jurisdiction policy bundles,
and photographed-person image-rights cases. Never stores uploaded images.

Production decisions depend on trusted external jurisdiction and content-lifecycle
providers. Missing providers fail closed; no legal policy is seeded in code.
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
from functools import lru_cache
from typing import Annotated, Iterator, Literal
from urllib.parse import quote, urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Boolean, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint,
    create_engine, func, select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SERVICE = "cirvanna-privacy-governance-service"
bearer = HTTPBearer(auto_error=False)
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
ASSET_REF_RE = re.compile(r"^[A-Za-z0-9_-]{8,160}$")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{3,160}$")
JURISDICTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
DECLARATION_SCOPES = {
    "no_people": "photographed_no_people_attestation",
    "adults_only": "photographed_people_adult_attestation",
    "contains_minor": "photographed_people_minor_attestation",
}
URGENT_REASONS = {"unmasked_face", "possible_minor", "nonconsensual"}
REQUIRED_REMOVAL_SURFACES = {
    "source", "derivatives", "replicas", "cache", "cdn",
    "merchant_surfaces", "shared_links",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def database_url() -> str:
    value = os.getenv("PRIVACY_GOVERNANCE_DATABASE_URL", "").strip()
    environment = os.getenv("PRIVACY_GOVERNANCE_ENVIRONMENT", "development").strip().lower()
    if not value:
        if environment == "production":
            raise HTTPException(503, detail={"code": "PRIVACY_GOVERNANCE_DATABASE_NOT_CONFIGURED"})
        return "sqlite:///./privacy-governance.db"
    if environment == "production" and value.startswith("sqlite"):
        raise HTTPException(503, detail={"code": "POSTGRES_REQUIRED_IN_PRODUCTION"})
    return value


@lru_cache(maxsize=4)
def _engine(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache(maxsize=4)
def _session_factory(url: str):
    return sessionmaker(bind=_engine(url), autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ConsentRecord(Base):
    __tablename__ = "privacy_consent_records"
    consent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    granted_scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    photographed_people_status: Mapped[str] = mapped_column(String(24), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    guardian_authority_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guardian_verification_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyBundle(Base):
    __tablename__ = "privacy_policy_bundles"
    __table_args__ = (
        UniqueConstraint("jurisdiction", "policy_version", name="uq_privacy_policy_jurisdiction_version"),
        Index("ix_privacy_policy_current", "jurisdiction", "active", "effective_at", "expires_at"),
    )
    bundle_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guardian_consent_required_for_minor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    child_product_discovery_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    lawful_basis_approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cross_border_transfer_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rights_response_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_review_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ImageRightsCase(Base):
    __tablename__ = "privacy_image_rights_cases"
    __table_args__ = (
        Index("ix_privacy_rights_asset_created", "asset_id", "created_at"),
        Index("ix_privacy_rights_status_created", "status", "created_at"),
    )
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    asset_reference_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_type: Mapped[str] = mapped_column(String(12), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    requester_relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction_hint_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    applicable_jurisdictions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    triage_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    legal_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_basis: Mapped[str] = mapped_column(String(48), nullable=False, default="jurisdiction_unresolved")
    resolution_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PrivacyAuditEvent(Base):
    __tablename__ = "privacy_governance_audit_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_safe: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentGrantIn(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    consent_image_processing: bool
    consent_click_it: bool
    photographed_people_status: Literal["no_people", "adults_only", "contains_minor"]
    photographed_people_consent_confirmed: bool = False
    consent_version: str = Field(min_length=1, max_length=80)
    resource_id: str | None = Field(default=None, min_length=3, max_length=160)
    guardian_verification_reference: str | None = Field(default=None, min_length=12, max_length=200)

    @field_validator("subject_id")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        value = value.strip()
        if not SUBJECT_RE.fullmatch(value):
            raise ValueError("invalid subject identifier")
        return value


class ConsentRevokeIn(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    reason_code: Literal["user_request", "guardian_request", "account_closure"] = "user_request"


class ConsentVerifyIn(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    consent_id: str = Field(min_length=8, max_length=160)
    required_scopes: list[str] = Field(min_length=1, max_length=12)
    resource_id: str | None = Field(default=None, max_length=160)


class PolicyBundleIn(StrictModel):
    jurisdiction: str = Field(min_length=2, max_length=64)
    policy_version: str = Field(min_length=1, max_length=80)
    effective_at: datetime
    expires_at: datetime
    guardian_consent_required_for_minor: bool
    child_product_discovery_allowed: bool
    lawful_basis_approved: bool
    cross_border_transfer_allowed: bool
    rights_response_deadline_hours: int = Field(ge=1, le=8760)
    approved_by: str = Field(min_length=3, max_length=160)
    legal_review_reference: str = Field(min_length=8, max_length=160)
    facial_recognition_allowed: bool = False
    face_identity_analysis_allowed: bool = False
    child_facial_identity_analysis_allowed: bool = False
    child_behavioural_profiling_allowed: bool = False
    public_unmasked_face_exposure_allowed: bool = False
    image_retention_allowed: bool = False
    public_sharing_allowed: bool = False
    signature_base64: str = Field(min_length=32, max_length=2048)

    @field_validator("jurisdiction")
    @classmethod
    def valid_jurisdiction(cls, value: str) -> str:
        value = value.strip().upper()
        if not JURISDICTION_RE.fullmatch(value):
            raise ValueError("invalid jurisdiction code")
        return value

    @field_validator("effective_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        return aware(value)


class RightsRequestIn(StrictModel):
    asset_reference: str = Field(min_length=8, max_length=160)
    request_type: Literal["report", "removal"]
    reason_code: Literal["unmasked_face", "possible_minor", "nonconsensual", "privacy_concern", "other"]
    requester_relationship: Literal["photographed_person", "parent_guardian", "authorized_representative", "other"]
    jurisdiction_hint: str | None = Field(default=None, max_length=100)
    jurisdiction_hint_is_unverified: Literal[True] = True
    requester_authentication: Literal["verification_required"] = "verification_required"

    @field_validator("asset_reference")
    @classmethod
    def opaque_reference_only(cls, value: str) -> str:
        value = value.strip()
        if not ASSET_REF_RE.fullmatch(value):
            raise ValueError("asset_reference must be an opaque Cirvanna reference")
        return value


class RightsReviewIn(StrictModel):
    decision: Literal["approve", "reject", "escalate"]
    verification_reference: str = Field(min_length=8, max_length=160)
    resolution_code: str = Field(min_length=3, max_length=64)


class AssetPublicationGateIn(StrictModel):
    asset_id: str = Field(min_length=3, max_length=160)
    asset_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    masking_attestation_id: str = Field(min_length=12, max_length=160)
    target_surface: Literal["public_profile", "community_feed", "marketplace", "merchant_surface", "shared_link"]


class JurisdictionEvaluateIn(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    service: Literal["cirvanna-click-it"]
    purpose: Literal["visual_product_discovery"]
    photographed_people_status: Literal["no_people", "adults_only", "contains_minor"]
    capture_jurisdiction_hint: str | None = Field(default=None, max_length=100)
    capture_jurisdiction_hint_is_unverified: Literal[True] = True
    service_deployment_region: str | None = Field(default=None, max_length=100)
    controller_profile_id: str | None = Field(default=None, max_length=160)
    requested_retention_seconds: Literal[0] = 0
    requested_public_display: Literal[False] = False
    prohibited_processing: list[str] = Field(min_length=1, max_length=20)
    jurisdiction_resolution: dict


def session_for_request() -> Iterator[Session]:
    session = _session_factory(database_url())()
    try:
        yield session
    finally:
        session.close()


def _internal_secret(name: str, minimum_bytes: int = 32) -> str:
    value = os.getenv(name, "").strip()
    if len(value.encode("utf-8")) < minimum_bytes:
        raise HTTPException(503, detail={"code": f"{name}_NOT_CONFIGURED"})
    return value


def require_internal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    expected = _internal_secret("PRIVACY_GOVERNANCE_INTERNAL_TOKEN")
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_policy_publisher(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    expected = _internal_secret("PRIVACY_POLICY_PUBLISH_TOKEN")
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "POLICY_PUBLISH_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_rights_reviewer(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    expected = _internal_secret("PRIVACY_RIGHTS_REVIEW_TOKEN")
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "RIGHTS_REVIEW_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def trusted_service(name: str) -> tuple[str, str]:
    raw = os.getenv(f"{name}_API_URL", "").strip().rstrip("/")
    token = os.getenv(f"{name}_API_TOKEN", "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": f"{name}_PROVIDER_NOT_CONFIGURED"})
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        raise HTTPException(503, detail={"code": f"{name}_PROVIDER_URL_INVALID"})
    return raw, token


async def post_trusted(name: str, path: str, payload: dict) -> dict:
    base, token = trusted_service(name)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": f"{name}_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": f"{name}_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404, 409, 422}:
        raise HTTPException(403 if response.status_code in {401, 403} else 409 if response.status_code == 409 else 422 if response.status_code == 422 else 404,
                            detail={"code": f"{name}_REQUEST_REJECTED"})
    if response.status_code < 200 or response.status_code >= 300:
        raise HTTPException(503, detail={"code": f"{name}_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": f"{name}_INVALID_RESPONSE"}) from exc
    if not isinstance(result, dict):
        raise HTTPException(502, detail={"code": f"{name}_INVALID_RESPONSE"})
    return result


def audit(db: Session, event_type: str, object_type: str, object_id: str, actor_type: str, metadata: dict | None = None) -> None:
    db.add(PrivacyAuditEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        actor_type=actor_type,
        metadata_safe=metadata or {},
    ))


def _policy_signing_key() -> Ed25519PublicKey:
    pem = os.getenv("PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM", "").strip()
    if not pem:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_SIGNING_KEY_NOT_CONFIGURED"})
    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, detail={"code": "PRIVACY_POLICY_SIGNING_KEY_INVALID"}) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise HTTPException(503, detail={"code": "ED25519_POLICY_KEY_REQUIRED"})
    return key


def _canonical_policy_payload(payload: PolicyBundleIn) -> bytes:
    data = payload.model_dump(mode="json", exclude={"signature_base64"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _active_policy(db: Session, jurisdiction: str, current: datetime) -> PolicyBundle | None:
    rows = db.scalars(
        select(PolicyBundle).where(
            PolicyBundle.jurisdiction == jurisdiction,
            PolicyBundle.active.is_(True),
            PolicyBundle.effective_at <= current,
            PolicyBundle.expires_at > current,
        ).order_by(PolicyBundle.effective_at.desc(), PolicyBundle.created_at.desc())
    ).all()
    return rows[0] if rows else None


app = FastAPI(
    title="Cirvanna Privacy Governance Service",
    version="0.1.0",
    description="Internal consent, signed jurisdiction-policy and image-rights case service. No image uploads are accepted.",
)


@app.on_event("startup")
def startup() -> None:
    environment = os.getenv("PRIVACY_GOVERNANCE_ENVIRONMENT", "development").strip().lower()
    auto_create = os.getenv("PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA", "true").strip().lower() == "true"
    if environment == "production" and auto_create:
        raise RuntimeError("PRIVACY_GOVERNANCE_AUTO_CREATE_SCHEMA must be false in production")
    if auto_create:
        Base.metadata.create_all(_engine(database_url()))


@app.get("/health")
def health() -> dict:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def ready(db: Session = Depends(session_for_request)) -> dict:
    try:
        db.execute(select(func.count()).select_from(ConsentRecord)).scalar_one()
        database_ready = True
    except SQLAlchemyError:
        database_ready = False
    resolver_ready = bool(os.getenv("JURISDICTION_RESOLVER_API_URL")) and bool(os.getenv("JURISDICTION_RESOLVER_API_TOKEN"))
    content_ready = bool(os.getenv("CONTENT_LIFECYCLE_API_URL")) and bool(os.getenv("CONTENT_LIFECYCLE_API_TOKEN"))
    guardian_ready = bool(os.getenv("GUARDIAN_VERIFICATION_API_URL")) and bool(os.getenv("GUARDIAN_VERIFICATION_API_TOKEN"))
    internal_ready = len(os.getenv("PRIVACY_GOVERNANCE_INTERNAL_TOKEN", "").encode()) >= 32
    signing_ready = bool(os.getenv("PRIVACY_POLICY_BUNDLE_PUBLIC_KEY_PEM"))
    review_ready = len(os.getenv("PRIVACY_RIGHTS_REVIEW_TOKEN", "").encode()) >= 32
    rights_authority_ready = bool(os.getenv("RIGHTS_AUTHORITY_VERIFICATION_API_URL")) and bool(os.getenv("RIGHTS_AUTHORITY_VERIFICATION_API_TOKEN"))
    vision_attestation_ready = bool(os.getenv("VISION_PRIVACY_ATTESTATION_API_URL")) and bool(os.getenv("VISION_PRIVACY_ATTESTATION_API_TOKEN"))
    required_providers_ready = all([
        database_ready, resolver_ready, content_ready, guardian_ready, internal_ready,
        signing_ready, review_ready, rights_authority_ready, vision_attestation_ready,
    ])
    return {
        "status": "ready" if required_providers_ready else "not_ready",
        "service": SERVICE,
        "database_ready": database_ready,
        "jurisdiction_resolver_configured": resolver_ready,
        "content_lifecycle_configured": content_ready,
        "guardian_verification_configured": guardian_ready,
        "internal_auth_configured": internal_ready,
        "policy_signing_key_configured": signing_ready,
        "rights_review_auth_configured": review_ready,
        "requester_authority_provider_configured": rights_authority_ready,
        "vision_privacy_attestation_configured": vision_attestation_ready,
        "ready": required_providers_ready,
    }


@app.post("/internal/v1/consents/grant", dependencies=[Depends(require_internal)])
async def grant_consent(payload: ConsentGrantIn, db: Session = Depends(session_for_request)) -> dict:
    if not payload.consent_image_processing or not payload.consent_click_it:
        raise HTTPException(403, detail={"code": "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"})
    if payload.photographed_people_status != "no_people" and not payload.photographed_people_consent_confirmed:
        raise HTTPException(403, detail={"code": "PHOTOGRAPHED_PEOPLE_CONSENT_REQUIRED"})
    scopes = ["image_processing", "click_it", DECLARATION_SCOPES[payload.photographed_people_status]]
    guardian_verified = False
    verification_digest = None
    if payload.photographed_people_status == "contains_minor" and payload.guardian_verification_reference:
        verified = await post_trusted(
            "GUARDIAN_VERIFICATION",
            "/internal/v1/guardian-authorizations/verify",
            {
                "subject_id": payload.subject_id,
                "verification_reference": payload.guardian_verification_reference,
                "purpose": "cirvanna_click_it_photographed_minor",
            },
        )
        guardian_verified = (
            verified.get("verified") is True
            and verified.get("active") is True
            and verified.get("guardian_authority_verified") is True
            and verified.get("subject_id") == payload.subject_id
            and verified.get("purpose") == "cirvanna_click_it_photographed_minor"
        )
        if not guardian_verified:
            raise HTTPException(403, detail={"code": "GUARDIAN_AUTHORITY_NOT_VERIFIED"})
        scopes.append("guardian_authorized")
        verification_digest = hashlib.sha256(payload.guardian_verification_reference.encode()).hexdigest()
    consent_id = str(uuid.uuid4())
    record = ConsentRecord(
        consent_id=consent_id,
        subject_id=payload.subject_id,
        resource_id=payload.resource_id,
        granted_scopes=scopes,
        photographed_people_status=payload.photographed_people_status,
        consent_version=payload.consent_version,
        active=True,
        guardian_authority_verified=guardian_verified,
        guardian_verification_digest=verification_digest,
        granted_at=utcnow(),
    )
    db.add(record)
    audit(db, "consent_granted", "consent", consent_id, "authenticated_subject", {
        "scopes": scopes,
        "photographed_people_status": payload.photographed_people_status,
        "guardian_authority_verified": guardian_verified,
        "consent_version": payload.consent_version,
    })
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, detail={"code": "CONSENT_STORAGE_UNAVAILABLE"}) from exc
    return {
        "consent_id": consent_id,
        "active": True,
        "granted_scopes": scopes,
        "photographed_people_status": payload.photographed_people_status,
        "guardian_authority_verified": guardian_verified,
        "consent_version": payload.consent_version,
    }


@app.post("/internal/v1/consents/verify", dependencies=[Depends(require_internal)])
def verify_consent(payload: ConsentVerifyIn, db: Session = Depends(session_for_request)) -> dict:
    row = db.get(ConsentRecord, payload.consent_id)
    valid = (
        row is not None
        and row.active is True
        and row.subject_id == payload.subject_id
        and (payload.resource_id is None or row.resource_id == payload.resource_id)
        and isinstance(row.granted_scopes, list)
        and set(payload.required_scopes).issubset(set(row.granted_scopes))
    )
    if not valid:
        return {
            "verified": False,
            "active": False,
            "subject_id": payload.subject_id,
            "consent_id": payload.consent_id,
            "granted_scopes": [],
            "guardian_authority_verified": False,
        }
    return {
        "verified": True,
        "active": True,
        "subject_id": row.subject_id,
        "consent_id": row.consent_id,
        "resource_id": row.resource_id,
        "granted_scopes": row.granted_scopes,
        "guardian_authority_verified": row.guardian_authority_verified is True,
    }


@app.post("/internal/v1/consents/{consent_id}/revoke", dependencies=[Depends(require_internal)])
def revoke_consent(consent_id: str, payload: ConsentRevokeIn, db: Session = Depends(session_for_request)) -> dict:
    row = db.get(ConsentRecord, consent_id)
    if row is None or row.subject_id != payload.subject_id:
        raise HTTPException(404, detail={"code": "CONSENT_NOT_FOUND"})
    if row.active:
        row.active = False
        row.revoked_at = utcnow()
        audit(db, "consent_revoked", "consent", consent_id, "authenticated_subject", {
            "reason_code": payload.reason_code,
        })
        db.commit()
    return {"consent_id": consent_id, "active": False, "revoked": True}


@app.post("/internal/v1/privacy/policies", dependencies=[Depends(require_policy_publisher)])
def publish_policy(payload: PolicyBundleIn, db: Session = Depends(session_for_request)) -> dict:
    if payload.expires_at <= payload.effective_at:
        raise HTTPException(422, detail={"code": "POLICY_EXPIRY_MUST_FOLLOW_EFFECTIVE_DATE"})
    prohibited_flags = [
        payload.facial_recognition_allowed,
        payload.face_identity_analysis_allowed,
        payload.child_facial_identity_analysis_allowed,
        payload.child_behavioural_profiling_allowed,
        payload.public_unmasked_face_exposure_allowed,
        payload.image_retention_allowed,
        payload.public_sharing_allowed,
    ]
    if any(prohibited_flags):
        raise HTTPException(422, detail={"code": "UNSAFE_PRIVACY_POLICY_CANNOT_BE_PUBLISHED"})
    if not payload.approved_by.strip() or not payload.legal_review_reference.strip():
        raise HTTPException(422, detail={"code": "LEGAL_REVIEW_METADATA_REQUIRED"})
    canonical = _canonical_policy_payload(payload)
    try:
        signature = base64.b64decode(payload.signature_base64, validate=True)
        _policy_signing_key().verify(signature, canonical)
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(403, detail={"code": "POLICY_SIGNATURE_INVALID"}) from exc
    digest = hashlib.sha256(canonical).hexdigest()
    signature_digest = hashlib.sha256(signature).hexdigest()
    existing = db.scalar(select(PolicyBundle).where(
        PolicyBundle.jurisdiction == payload.jurisdiction,
        PolicyBundle.policy_version == payload.policy_version,
    ))
    if existing is not None:
        raise HTTPException(409, detail={"code": "POLICY_VERSION_ALREADY_PUBLISHED"})
    row = PolicyBundle(
        bundle_id=str(uuid.uuid4()),
        jurisdiction=payload.jurisdiction,
        policy_version=payload.policy_version,
        effective_at=payload.effective_at,
        expires_at=payload.expires_at,
        guardian_consent_required_for_minor=payload.guardian_consent_required_for_minor,
        child_product_discovery_allowed=payload.child_product_discovery_allowed,
        lawful_basis_approved=payload.lawful_basis_approved,
        cross_border_transfer_allowed=payload.cross_border_transfer_allowed,
        rights_response_deadline_hours=payload.rights_response_deadline_hours,
        approved_by=payload.approved_by,
        legal_review_reference=payload.legal_review_reference,
        payload=payload.model_dump(mode="json", exclude={"signature_base64"}),
        policy_sha256=digest,
        signature_sha256=signature_digest,
        active=True,
    )
    db.add(row)
    audit(db, "policy_bundle_published", "policy_bundle", row.bundle_id, "legal_policy_publisher", {
        "jurisdiction": payload.jurisdiction,
        "policy_version": payload.policy_version,
        "policy_sha256": digest,
        "legal_review_reference": payload.legal_review_reference,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "POLICY_VERSION_ALREADY_PUBLISHED"}) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, detail={"code": "POLICY_STORAGE_UNAVAILABLE"}) from exc
    return {
        "bundle_id": row.bundle_id,
        "jurisdiction": row.jurisdiction,
        "policy_version": row.policy_version,
        "policy_sha256": row.policy_sha256,
        "signature_verified": True,
        "effective_at": row.effective_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
    }


@app.post("/internal/v1/privacy/click-it/evaluate", dependencies=[Depends(require_internal)])
async def evaluate_click_it_policy(payload: JurisdictionEvaluateIn, db: Session = Depends(session_for_request)) -> dict:
    if payload.photographed_people_status not in DECLARATION_SCOPES:
        raise HTTPException(403, detail={"code": "CHILD_SAFETY_STATUS_UNCONFIRMED"})
    if payload.requested_retention_seconds != 0 or payload.requested_public_display is not False:
        raise HTTPException(403, detail={"code": "CLICK_IT_RETENTION_OR_DISPLAY_NOT_ALLOWED"})
    required_prohibitions = {
        "facial_recognition", "face_identity_analysis", "face_embeddings",
        "identity_matching", "sensitive_trait_inference",
        "child_behavioural_profiling", "child_facial_identity_analysis",
    }
    if not required_prohibitions.issubset(set(payload.prohibited_processing)):
        raise HTTPException(403, detail={"code": "PROHIBITED_PROCESSING_NOT_DECLARED"})
    resolver_payload = {
        "subject_id": payload.subject_id,
        "service": SERVICE,
        "purpose": payload.purpose,
        "photographed_people_status": payload.photographed_people_status,
        "capture_jurisdiction_hint": payload.capture_jurisdiction_hint,
        "capture_jurisdiction_hint_is_unverified": True,
        "service_deployment_region": payload.service_deployment_region,
        "controller_profile_id": payload.controller_profile_id,
        "requested_retention_seconds": 0,
        "resolve_from_trusted_subject_profile": True,
        "include_controller_and_processor_establishments": True,
        "include_capture_and_processing_context": True,
        "include_processing_storage_and_transfer_destinations": True,
        "do_not_trust_client_country_claims": True,
    }
    resolution = await post_trusted(
        "JURISDICTION_RESOLVER",
        "/internal/v1/privacy/jurisdictions/resolve",
        resolver_payload,
    )
    jurisdictions = resolution.get("applicable_jurisdictions")
    required_context_lists = (
        "controller_establishments",
        "processor_establishments",
        "processing_locations",
        "storage_locations",
        "transfer_paths",
    )
    context_locations_complete = all(
        isinstance(resolution.get(name), list)
        and (name == "transfer_paths" or bool(resolution.get(name)))
        and (
            all(isinstance(item, str) and bool(item.strip()) for item in resolution.get(name, []))
            if name != "transfer_paths"
            else all(
                isinstance(item, dict)
                and isinstance(item.get("from"), str) and bool(item["from"].strip())
                and isinstance(item.get("to"), str) and bool(item["to"].strip())
                and isinstance(item.get("allowed"), bool)
                for item in resolution.get(name, [])
            )
        )
        for name in required_context_lists
    )
    resolution_complete = (
        resolution.get("jurisdiction_resolution_complete") is True
        and isinstance(jurisdictions, list)
        and bool(jurisdictions)
        and all(isinstance(value, str) and JURISDICTION_RE.fullmatch(value.upper()) for value in jurisdictions)
        and resolution.get("policy_conflicts_resolved") is True
        and context_locations_complete
    )
    if not resolution_complete:
        return {
            "decision": "BLOCK",
            "current": False,
            "block_reasons": ["JURISDICTION_RESOLUTION_INCOMPLETE_OR_CONFLICTING"],
            "policy_version": "unresolved",
            "policy_sha256": hashlib.sha256(b"unresolved").hexdigest(),
            "applicable_jurisdictions": [],
            "jurisdiction_resolution_complete": False,
            "policy_conflicts_resolved": False,
            "lawful_basis_authorized": False,
            "cross_border_transfers_authorized": False,
            "guardian_consent_required": True,
            "retention_seconds": 0,
            "rights_response_deadline_hours": None,
            "facial_recognition_allowed": False,
            "face_identity_analysis_allowed": False,
            "child_facial_identity_analysis_allowed": False,
            "child_behavioural_profiling_allowed": False,
            "public_unmasked_face_exposure_allowed": False,
            "image_retention_allowed": False,
            "public_sharing_allowed": False,
        }
    normalized_jurisdictions = sorted({value.upper() for value in jurisdictions})
    current = utcnow()
    bundles = [_active_policy(db, jurisdiction, current) for jurisdiction in normalized_jurisdictions]
    reasons: list[str] = []
    if any(bundle is None for bundle in bundles):
        reasons.append("CURRENT_SIGNED_POLICY_MISSING_OR_EXPIRED")
    usable = [bundle for bundle in bundles if bundle is not None]
    transfers = resolution.get("transfer_paths")
    if not isinstance(transfers, list):
        reasons.append("TRANSFER_PATHS_NOT_RESOLVED")
        transfers = []
    if any(not isinstance(path, dict) or path.get("allowed") is not True for path in transfers):
        reasons.append("TRANSFER_PATH_NOT_AUTHORIZED")
    if any(not row.lawful_basis_approved for row in usable):
        reasons.append("LAWFUL_BASIS_NOT_APPROVED")
    if any(not row.cross_border_transfer_allowed for row in usable):
        reasons.append("CROSS_BORDER_TRANSFER_NOT_AUTHORIZED")
    if payload.photographed_people_status == "contains_minor":
        if any(not row.child_product_discovery_allowed for row in usable):
            reasons.append("CHILD_PRODUCT_DISCOVERY_NOT_AUTHORIZED")
    guardian_required = any(row.guardian_consent_required_for_minor for row in usable) if usable else True
    complete = len(usable) == len(normalized_jurisdictions)
    policy_versions = sorted(f"{row.jurisdiction}@{row.policy_version}" for row in usable)
    combined_version = "+".join(policy_versions) if complete else "incomplete"
    combined_digest = hashlib.sha256(
        "|".join(sorted(row.policy_sha256 for row in usable)).encode("ascii")
    ).hexdigest()
    deadline = min((row.rights_response_deadline_hours for row in usable), default=None)
    passed = complete and not reasons and resolution_complete
    return {
        "decision": "PASS" if passed else "BLOCK",
        "current": complete,
        "block_reasons": reasons,
        "policy_version": combined_version,
        "policy_sha256": combined_digest,
        "applicable_jurisdictions": normalized_jurisdictions,
        "jurisdiction_resolution_complete": resolution_complete,
        "policy_conflicts_resolved": resolution.get("policy_conflicts_resolved") is True,
        "lawful_basis_authorized": complete and all(row.lawful_basis_approved for row in usable),
        "cross_border_transfers_authorized": complete and all(row.cross_border_transfer_allowed for row in usable) and all(
            isinstance(path, dict) and path.get("allowed") is True for path in transfers
        ),
        "guardian_consent_required": guardian_required,
        "retention_seconds": 0,
        "rights_response_deadline_hours": deadline,
        "facial_recognition_allowed": False,
        "face_identity_analysis_allowed": False,
        "child_facial_identity_analysis_allowed": False,
        "child_behavioural_profiling_allowed": False,
        "public_unmasked_face_exposure_allowed": False,
        "image_retention_allowed": False,
        "public_sharing_allowed": False,
    }


async def rights_deadline_context(asset_id: str, db: Session, created_at: datetime) -> dict:
    """Use the strictest current signed jurisdiction deadline; otherwise set only platform triage SLA."""
    try:
        triage_hours = int(os.getenv("PRIVACY_RIGHTS_TRIAGE_HOURS", "4"))
    except ValueError:
        triage_hours = 4
    triage_hours = max(1, min(triage_hours, 24))
    try:
        resolution = await post_trusted(
            "JURISDICTION_RESOLVER",
            "/internal/v1/privacy/image-rights/jurisdictions/resolve",
            {
                "asset_id": asset_id,
                "purpose": "photographed_person_rights",
                "resolve_from_asset_subject_and_controller_context": True,
                "include_controller_and_processor_establishments": True,
                "include_processing_and_storage_locations": True,
                "include_all_transfer_destinations": True,
            },
        )
    except HTTPException:
        resolution = {}
    jurisdictions = resolution.get("applicable_jurisdictions")
    required_context = (
        "controller_establishments",
        "processor_establishments",
        "processing_locations",
        "storage_locations",
        "transfer_paths",
    )
    context_complete = all(
        isinstance(resolution.get(name), list)
        and (name == "transfer_paths" or bool(resolution.get(name)))
        and (
            all(isinstance(item, str) and bool(item.strip()) for item in resolution.get(name, []))
            if name != "transfer_paths"
            else all(
                isinstance(item, dict)
                and isinstance(item.get("from"), str) and bool(item["from"].strip())
                and isinstance(item.get("to"), str) and bool(item["to"].strip())
                and isinstance(item.get("allowed"), bool)
                for item in resolution.get(name, [])
            )
        )
        for name in required_context
    )
    complete = (
        resolution.get("jurisdiction_resolution_complete") is True
        and resolution.get("policy_conflicts_resolved") is True
        and isinstance(jurisdictions, list)
        and bool(jurisdictions)
        and all(isinstance(value, str) and JURISDICTION_RE.fullmatch(value.upper()) for value in jurisdictions)
        and context_complete
    )
    normalized = sorted({value.upper() for value in jurisdictions}) if complete else []
    bundles = [_active_policy(db, code, created_at) for code in normalized] if complete else []
    policies_complete = complete and bool(bundles) and all(bundle is not None for bundle in bundles)
    if policies_complete:
        legal_hours = min(bundle.rights_response_deadline_hours for bundle in bundles)
        return {
            "applicable_jurisdictions": normalized,
            "legal_response_due_at": created_at + timedelta(hours=legal_hours),
            "deadline_basis": "resolved_signed_jurisdiction_policy",
            "triage_hours": triage_hours,
        }
    return {
        "applicable_jurisdictions": normalized,
        "legal_response_due_at": None,
        "deadline_basis": (
            "jurisdiction_policy_missing_platform_triage"
            if complete
            else "jurisdiction_unresolved_platform_triage"
        ),
        "triage_hours": triage_hours,
    }


async def resolve_asset_reference(asset_reference: str) -> dict:
    resolved = await post_trusted(
        "CONTENT_LIFECYCLE",
        "/internal/v1/assets/resolve",
        {"asset_reference": asset_reference, "purpose": "image_rights_request"},
    )
    asset_id = resolved.get("asset_id")
    if resolved.get("found") is not True or resolved.get("active") is not True or not isinstance(asset_id, str) or not ASSET_ID_RE.fullmatch(asset_id):
        raise HTTPException(404, detail={"code": "CIRVANNA_ASSET_NOT_FOUND"})
    return resolved


@app.post("/internal/v1/privacy/assets/publication/evaluate", dependencies=[Depends(require_internal)])
async def evaluate_asset_publication(payload: AssetPublicationGateIn) -> dict:
    """Block public exposure unless a trusted Vision service attests every face is masked."""
    if not ASSET_ID_RE.fullmatch(payload.asset_id):
        raise HTTPException(422, detail={"code": "INVALID_ASSET_ID"})
    receipt = await post_trusted(
        "VISION_PRIVACY_ATTESTATION",
        "/internal/v1/privacy/mask-attestations/verify",
        {
            "asset_id": payload.asset_id,
            "asset_sha256": payload.asset_sha256,
            "attestation_id": payload.masking_attestation_id,
            "target_surface": payload.target_surface,
            "purpose": "public_media_publication",
            "require_exact_asset_digest_match": True,
            "require_independent_human_privacy_review": True,
            "require_all_detected_faces_masked": True,
            "prohibit_face_recognition": True,
            "prohibit_face_embeddings": True,
            "prohibit_age_estimation": True,
        },
    )
    digest = receipt.get("masking_model_sha256")
    valid = (
        receipt.get("verified") is True
        and receipt.get("active") is True
        and receipt.get("asset_id") == payload.asset_id
        and receipt.get("asset_sha256") == payload.asset_sha256
        and receipt.get("human_privacy_review_passed") is True
        and receipt.get("human_reviewed_asset_sha256") == payload.asset_sha256
        and receipt.get("attestation_id") == payload.masking_attestation_id
        and receipt.get("all_detected_faces_masked") is True
        and receipt.get("unmasked_face_count") == 0
        and receipt.get("masking_applied_before_publication") is True
        and receipt.get("face_recognition_performed") is False
        and receipt.get("face_embeddings_created") is False
        and receipt.get("age_estimation_performed") is False
        and receipt.get("all_face_regions_processed") is True
        and isinstance(digest, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
    )
    if not valid:
        raise HTTPException(403, detail={"code": "PUBLICATION_PRIVACY_ATTESTATION_NOT_VALID"})
    return {
        "decision": "PASS",
        "asset_id": payload.asset_id,
        "asset_sha256": payload.asset_sha256,
        "target_surface": payload.target_surface,
        "human_privacy_review_passed": True,
        "all_detected_faces_masked": True,
        "unmasked_face_count": 0,
        "face_recognition_performed": False,
        "face_embeddings_created": False,
        "age_estimation_performed": False,
        "masking_model_sha256": digest,
        "public_unmasked_face_exposure_allowed": False,
    }


@app.post("/internal/v1/image-rights/requests", dependencies=[Depends(require_internal)])
async def create_image_rights_request(payload: RightsRequestIn, db: Session = Depends(session_for_request)) -> dict:
    resolved = await resolve_asset_reference(payload.asset_reference)
    asset_id = resolved["asset_id"]
    since = utcnow() - timedelta(minutes=10)
    recent_count = db.scalar(select(func.count()).select_from(ImageRightsCase).where(
        ImageRightsCase.asset_id == asset_id,
        ImageRightsCase.created_at >= since,
    )) or 0
    if recent_count >= 10:
        raise HTTPException(429, detail={"code": "IMAGE_RIGHTS_ASSET_RATE_LIMITED"})
    request_id = str(uuid.uuid4())
    status_token = secrets.token_urlsafe(36)
    created_at = utcnow()
    deadline_context = await rights_deadline_context(asset_id, db, created_at)
    triage_due_at = created_at + timedelta(hours=deadline_context["triage_hours"])
    status_digest = hashlib.sha256(status_token.encode("utf-8")).hexdigest()
    urgent = payload.reason_code in URGENT_REASONS
    row = ImageRightsCase(
        request_id=request_id,
        asset_id=asset_id,
        asset_reference_digest=hashlib.sha256(payload.asset_reference.encode()).hexdigest(),
        request_type=payload.request_type,
        reason_code=payload.reason_code,
        requester_relationship=payload.requester_relationship,
        jurisdiction_hint_digest=hashlib.sha256(payload.jurisdiction_hint.encode()).hexdigest() if payload.jurisdiction_hint else None,
        status="quarantine_pending" if urgent else "under_review",
        quarantined=False,
        status_token_digest=status_digest,
        applicable_jurisdictions=deadline_context["applicable_jurisdictions"],
        triage_due_at=triage_due_at,
        legal_response_due_at=deadline_context["legal_response_due_at"],
        deadline_basis=deadline_context["deadline_basis"],
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    audit(db, "image_rights_request_created", "image_rights_case", request_id, "anonymous_reporter", {
        "reason_code": payload.reason_code,
        "request_type": payload.request_type,
        "urgent_quarantine_required": urgent,
        "asset_reference_digest": row.asset_reference_digest,
    })
    db.commit()
    if urgent:
        try:
            quarantine = await post_trusted(
                "CONTENT_LIFECYCLE",
                "/internal/v1/assets/" + quote(asset_id, safe="") + "/quarantine",
                {"request_id": request_id, "reason_code": payload.reason_code, "unpublish_required": True},
            )
        except HTTPException:
            row.status = "quarantine_failed"
            row.updated_at = utcnow()
            audit(db, "urgent_quarantine_failed", "image_rights_case", request_id, "system", {
                "reason_code": payload.reason_code,
            })
            db.commit()
            raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_QUARANTINE_NOT_CONFIRMED"})
        if quarantine.get("quarantined") is not True or quarantine.get("unpublished") is not True:
            row.status = "quarantine_failed"
            row.updated_at = utcnow()
            db.commit()
            raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_QUARANTINE_NOT_CONFIRMED"})
        row.status = "quarantined"
        row.quarantined = True
        row.updated_at = utcnow()
        audit(db, "urgent_asset_quarantined", "image_rights_case", request_id, "content_lifecycle", {
            "quarantined": True,
            "unpublished": True,
        })
        db.commit()
    return {
        "request_id": request_id,
        "status": row.status,
        "quarantined": row.quarantined,
        "status_token": status_token,
    }


@app.get("/internal/v1/image-rights/requests/{request_id}", dependencies=[Depends(require_internal)])
def image_rights_status(
    request_id: str,
    status_token: str = Header(alias="X-Requester-Status-Token", min_length=24, max_length=512),
    db: Session = Depends(session_for_request),
) -> dict:
    row = db.get(ImageRightsCase, request_id)
    supplied_digest = hashlib.sha256(status_token.encode("utf-8")).hexdigest()
    if row is None or not hmac.compare_digest(row.status_token_digest, supplied_digest):
        raise HTTPException(404, detail={"code": "IMAGE_RIGHTS_REQUEST_NOT_FOUND"})
    return {
        "request_id": row.request_id,
        "status": row.status,
        "quarantined": row.quarantined,
        "updated_at": row.updated_at.isoformat(),
        "triage_due_at": row.triage_due_at.isoformat(),
        "legal_response_due_at": row.legal_response_due_at.isoformat() if row.legal_response_due_at else None,
        "deadline_basis": row.deadline_basis,
        "applicable_jurisdictions": row.applicable_jurisdictions,
        "resolution_code": row.resolution_code,
    }


@app.get("/internal/v1/image-rights/queue", dependencies=[Depends(require_rights_reviewer)])
def image_rights_queue(db: Session = Depends(session_for_request)) -> dict:
    rows = db.scalars(select(ImageRightsCase).where(
        ImageRightsCase.status.in_(["quarantined", "under_review", "quarantine_failed", "escalated"])
    ).order_by(ImageRightsCase.created_at.asc()).limit(200)).all()
    return {
        "items": [
            {
                "request_id": row.request_id,
                "asset_id": row.asset_id,
                "request_type": row.request_type,
                "reason_code": row.reason_code,
                "requester_relationship": row.requester_relationship,
                "status": row.status,
                "quarantined": row.quarantined,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
                "triage_due_at": row.triage_due_at.isoformat(),
                "legal_response_due_at": row.legal_response_due_at.isoformat() if row.legal_response_due_at else None,
                "deadline_basis": row.deadline_basis,
            }
            for row in rows
        ]
    }


@app.post("/internal/v1/image-rights/requests/{request_id}/review", dependencies=[Depends(require_rights_reviewer)])
async def review_image_rights_request(
    request_id: str,
    payload: RightsReviewIn,
    db: Session = Depends(session_for_request),
) -> dict:
    row = db.get(ImageRightsCase, request_id)
    if row is None:
        raise HTTPException(404, detail={"code": "IMAGE_RIGHTS_REQUEST_NOT_FOUND"})
    if payload.decision == "escalate":
        row.status = "escalated"
        row.resolution_code = payload.resolution_code
        row.updated_at = utcnow()
        audit(db, "image_rights_case_escalated", "image_rights_case", request_id, "privacy_reviewer", {
            "resolution_code": payload.resolution_code,
            "verification_reference_digest": hashlib.sha256(payload.verification_reference.encode()).hexdigest(),
        })
        db.commit()
        return {"request_id": request_id, "status": row.status, "quarantined": row.quarantined}
    if payload.decision == "approve":
        authority = await post_trusted(
            "RIGHTS_AUTHORITY_VERIFICATION",
            "/internal/v1/image-rights/authority/verify",
            {
                "request_id": request_id,
                "asset_id": row.asset_id,
                "requester_relationship": row.requester_relationship,
                "verification_reference": payload.verification_reference,
            },
        )
        if not (
            authority.get("verified") is True
            and authority.get("active") is True
            and authority.get("request_id") == request_id
            and authority.get("asset_id") == row.asset_id
            and authority.get("requester_relationship") == row.requester_relationship
            and authority.get("authority_confirmed") is True
        ):
            raise HTTPException(403, detail={"code": "REQUESTER_AUTHORITY_NOT_VERIFIED"})
        deletion = await post_trusted(
            "CONTENT_LIFECYCLE",
            "/internal/v1/assets/" + quote(row.asset_id, safe="") + "/delete",
            {
                "request_id": request_id,
                "resolution_code": payload.resolution_code,
                "delete_derivatives": True,
                "invalidate_caches": True,
                "unpublish_shared_links": True,
            },
        )
        surfaces = deletion.get("deleted_surfaces")
        complete = deletion.get("propagation_complete") is True and isinstance(surfaces, list) and REQUIRED_REMOVAL_SURFACES.issubset(set(surfaces))
        if not complete:
            raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_DELETION_PROPAGATION_INCOMPLETE"})
        row.status = "completed"
        row.resolution_code = payload.resolution_code
        row.updated_at = utcnow()
        audit(db, "image_rights_removal_completed", "image_rights_case", request_id, "content_lifecycle", {
            "propagation_complete": True,
            "deleted_surfaces": sorted(REQUIRED_REMOVAL_SURFACES),
            "authority_verified": True,
            "verification_reference_digest": hashlib.sha256(payload.verification_reference.encode()).hexdigest(),
        })
        db.commit()
        return {"request_id": request_id, "status": row.status, "quarantined": row.quarantined, "deletion_propagated": True}
    if row.quarantined:
        release = await post_trusted(
            "CONTENT_LIFECYCLE",
            "/internal/v1/assets/" + quote(row.asset_id, safe="") + "/unquarantine",
            {"request_id": request_id, "resolution_code": payload.resolution_code},
        )
        if release.get("unquarantined") is not True:
            raise HTTPException(503, detail={"code": "IMAGE_RIGHTS_UNQUARANTINE_NOT_CONFIRMED"})
        row.quarantined = False
    row.status = "rejected"
    row.resolution_code = payload.resolution_code
    row.updated_at = utcnow()
    audit(db, "image_rights_case_rejected", "image_rights_case", request_id, "privacy_reviewer", {
        "resolution_code": payload.resolution_code,
        "verification_reference_digest": hashlib.sha256(payload.verification_reference.encode()).hexdigest(),
    })
    db.commit()
    return {"request_id": request_id, "status": row.status, "quarantined": row.quarantined}


@app.get("/internal/v1/privacy/policies", dependencies=[Depends(require_policy_publisher)])
def list_policy_bundles(db: Session = Depends(session_for_request)) -> dict:
    rows = db.scalars(select(PolicyBundle).order_by(PolicyBundle.jurisdiction, PolicyBundle.effective_at.desc()).limit(500)).all()
    return {
        "items": [
            {
                "jurisdiction": row.jurisdiction,
                "policy_version": row.policy_version,
                "policy_sha256": row.policy_sha256,
                "effective_at": row.effective_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
                "active": row.active,
                "approved_by": row.approved_by,
                "legal_review_reference": row.legal_review_reference,
            }
            for row in rows
        ]
    }

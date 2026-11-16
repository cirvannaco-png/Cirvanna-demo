"""Private appearance look-session API.

Stores versioned composition metadata and opaque private asset references only.
It does not render images, store image bytes, infer user identity, or authorize
Marketplace product display.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from appearance_intelligence import (  # noqa: E402
    AppearanceComponent,
    ComponentOperation,
    EditAction,
    FidelityAssessment,
    FidelityGate,
    FidelityGate as _FidelityGate,
    GateStatus,
    LookBase,
    LookBaseKind,
    LookComposition,
    OperationOrigin,
    RecommendationTrack,
    ReferenceKind,
)
from app.store import (  # noqa: E402
    AppearanceLookConsentEventRow,
    AppearanceLookDeletionRow,
    AppearanceLookRow,
    AppearanceLookVersionRow,
    Base,
    engine,
    find_command,
    get_look,
    get_version,
    open_session,
    utcnow,
)

SERVICE = "cirvanna-appearance-intelligence-service"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{1,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna Appearance Intelligence",
    version="0.1.0",
    description="Private versioned appearance look-session metadata API.",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque identifier")
    value = value.strip()
    if not IDENTIFIER_RE.fullmatch(value) or "://" in value or "/" in value or "\\" in value:
        raise ValueError(f"{field} must be an opaque identifier, not a URL or path")
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _db_url() -> str:
    value = os.getenv("APPEARANCE_DATABASE_URL", "").strip()
    if not value:
        raise HTTPException(503, detail={"code": "APPEARANCE_DATABASE_NOT_CONFIGURED"})
    return value


def _database() -> Session:
    try:
        return open_session(_db_url())
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(503, detail={"code": "APPEARANCE_DATABASE_UNAVAILABLE"}) from exc


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("APPEARANCE_SERVICE_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "APPEARANCE_SERVICE_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def require_renderer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("APPEARANCE_RENDERER_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "APPEARANCE_RENDERER_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "RENDERER_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _provider_base(url_key: str, token_key: str) -> tuple[str, str]:
    raw = os.getenv(url_key, "").strip()
    token = os.getenv(token_key, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": f"{url_key}_NOT_CONFIGURED"})
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        raise HTTPException(503, detail={"code": f"{url_key}_MUST_BE_TRUSTED_HTTPS"})
    return raw.rstrip("/"), token


async def _post_json(base: str, path: str, token: str, body: dict) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            return await client.post(
                base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "APPEARANCE_PROVIDER_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "APPEARANCE_PROVIDER_UNAVAILABLE"}) from exc


async def _verify_consent(
    *, subject_id: str, consent_id: str, resource_id: str, required_scopes: list[str],
) -> dict:
    base, token = _provider_base("IDENTITY_SERVICE_URL", "IDENTITY_SERVICE_TOKEN")
    response = await _post_json(
        base,
        "/internal/v1/consents/verify",
        token,
        {
            "subject_id": subject_id,
            "consent_id": consent_id,
            "resource_id": resource_id,
            "required_scopes": required_scopes,
            "require_expiring": True,
        },
    )
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "APPEARANCE_CONSENT_NOT_VERIFIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "APPEARANCE_CONSENT_PROVIDER_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "APPEARANCE_CONSENT_RESPONSE_INVALID"}) from exc
    if not (
        isinstance(result, dict)
        and result.get("verified") is True
        and result.get("active") is True
        and result.get("subject_id") == subject_id
        and result.get("consent_id") == consent_id
        and result.get("resource_id") == resource_id
        and set(required_scopes).issubset(set(result.get("granted_scopes", [])))
        and isinstance(result.get("consent_version"), str)
        and isinstance(result.get("expires_at"), str)
    ):
        raise HTTPException(403, detail={"code": "APPEARANCE_CONSENT_BINDING_INVALID"})
    try:
        expiry = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "APPEARANCE_CONSENT_EXPIRY_INVALID"}) from exc
    if expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= datetime.now(timezone.utc):
        raise HTTPException(403, detail={"code": "APPEARANCE_CONSENT_EXPIRED"})
    return result


async def _authorize_asset(
    *, subject_id: str, asset_id: str, purpose: str, parent_id: str,
) -> dict:
    base, token = _provider_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    response = await _post_json(
        base, "/internal/v1/assets/authorize", token,
        {
            "subject_id": subject_id,
            "asset_id": asset_id,
            "purpose": purpose,
            "parent_id": parent_id,
        },
    )
    if response.status_code in {403, 404}:
        raise HTTPException(404, detail={"code": "APPEARANCE_ASSET_NOT_FOUND_OR_NOT_AUTHORIZED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "APPEARANCE_ASSET_AUTHORIZATION_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "APPEARANCE_ASSET_RESPONSE_INVALID"}) from exc
    if not (
        isinstance(result, dict)
        and result.get("authorized") is True
        and result.get("active") is True
        and result.get("subject_id") == subject_id
        and result.get("asset_id") == asset_id
        and result.get("purpose") == purpose
        and result.get("parent_id") == parent_id
    ):
        raise HTTPException(403, detail={"code": "APPEARANCE_ASSET_BINDING_INVALID"})
    return result


async def _authorize_twin(*, subject_id: str, twin_id: str) -> dict:
    base, token = _provider_base("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN")
    response = await _post_json(
        base, "/internal/v1/twins/authorize", token,
        {"subject_id": subject_id, "twin_id": twin_id},
    )
    if response.status_code in {403, 404}:
        raise HTTPException(404, detail={"code": "APPEARANCE_TWIN_NOT_FOUND_OR_NOT_AUTHORIZED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "APPEARANCE_TWIN_AUTHORIZATION_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "APPEARANCE_TWIN_RESPONSE_INVALID"}) from exc
    source_ids = result.get("source_image_asset_ids") if isinstance(result, dict) else None
    if not (
        isinstance(result, dict)
        and result.get("authorized") is True
        and result.get("active") is True
        and result.get("subject_id") == subject_id
        and result.get("twin_id") == twin_id
        and result.get("representation_type") == "full_body_mesh"
        and isinstance(source_ids, list)
        and source_ids
        and all(isinstance(item, str) and IDENTIFIER_RE.fullmatch(item) for item in source_ids)
    ):
        raise HTTPException(403, detail={"code": "APPEARANCE_TWIN_BINDING_INVALID"})
    return result


class OperationIn(StrictModel):
    operation_id: str = Field(min_length=3, max_length=160)
    component: AppearanceComponent
    action: EditAction
    origin: OperationOrigin = OperationOrigin.USER_DIRECTED
    reference_kind: ReferenceKind | None = None
    reference_id: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    target_regions: list[str] = Field(default_factory=list)
    recommendation_track: RecommendationTrack | None = None
    recommendation_id: str | None = Field(default=None, max_length=160)
    parameters: dict[str, str] = Field(default_factory=dict)
    preserve_unrequested_regions: Literal[True] = True

    def domain(self) -> ComponentOperation:
        return ComponentOperation(
            operation_id=self.operation_id,
            component=self.component,
            action=self.action,
            origin=self.origin,
            reference_kind=self.reference_kind,
            reference_id=self.reference_id,
            description=self.description,
            target_regions=tuple(self.target_regions),
            recommendation_track=self.recommendation_track,
            recommendation_id=self.recommendation_id,
            parameters=tuple(sorted(self.parameters.items())),
            preserve_unrequested_regions=self.preserve_unrequested_regions,
        )

    def document(self) -> dict:
        # Persist normalized default regions and canonical component parameters,
        # not the caller's shorthand representation.
        return _operation_documents((self.domain(),))[0]


class BaseIn(StrictModel):
    kind: Literal["source_photo", "virtual_twin"]
    source_asset_ids: list[str] = Field(default_factory=list)
    twin_id: str | None = Field(default=None, min_length=3, max_length=160)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "source_photo":
            if not self.source_asset_ids or self.twin_id is not None:
                raise ValueError("source_photo requires source_asset_ids and must not contain twin_id")
        if self.kind == "virtual_twin":
            if self.twin_id is None or self.source_asset_ids:
                raise ValueError("virtual_twin requires twin_id; source assets are resolved from Twin Registry")
            _identifier(self.twin_id, "twin_id")
        for item in self.source_asset_ids:
            _identifier(item, "source_asset_id")
        if len(self.source_asset_ids) != len(set(self.source_asset_ids)):
            raise ValueError("source_asset_ids must be unique")
        return self


class CreateLookIn(StrictModel):
    look_id: str = Field(min_length=8, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    base: BaseIn
    operations: list[OperationIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_composition(self):
        _identifier(self.look_id, "look_id")
        _identifier(self.subject_id, "subject_id")
        _identifier(self.consent_id, "consent_id")
        components = [operation.component for operation in self.operations]
        if len(components) != len(set(components)):
            raise ValueError("a look version may contain only one current operation per component")
        for operation in self.operations:
            operation.domain()
        return self


class MutateLookIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)


class DeleteLookIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_subject(self):
        _identifier(self.subject_id, "subject_id")
        _identifier(self.command_id, "command_id")
        return self


class ApplyOperationIn(MutateLookIn):
    operation: OperationIn


class UndoLookIn(MutateLookIn):
    target_version: int = Field(ge=1)


class BranchLookIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    new_look_id: str = Field(min_length=8, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    command_id: str = Field(min_length=8, max_length=128)
    parent_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_ids(self):
        _identifier(self.subject_id, "subject_id")
        _identifier(self.new_look_id, "new_look_id")
        _identifier(self.consent_id, "consent_id")
        return self


class ConsentRenewalIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    consent_id: str = Field(min_length=8, max_length=128)
    consent_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_ids(self):
        _identifier(self.subject_id, "subject_id")
        _identifier(self.consent_id, "consent_id")
        return self


class FavoriteIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    is_favorite: bool


class GateIn(StrictModel):
    gate: FidelityGate
    status: GateStatus


class RenderResultIn(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    version: int = Field(ge=1)
    output_asset_id: str = Field(min_length=36, max_length=36)
    renderer_id: str = Field(min_length=3, max_length=128)
    renderer_version: str = Field(min_length=64, max_length=180)
    assessment_id: str = Field(min_length=8, max_length=160)
    checks: list[GateIn]

    @model_validator(mode="after")
    def validate_digests(self):
        _identifier(self.subject_id, "subject_id")
        _identifier(self.renderer_id, "renderer_id")
        if not SHA256_RE.fullmatch(self.renderer_version.rsplit("@sha256:", 1)[-1]):
            raise ValueError("renderer_version must end with @sha256:<lowercase sha256>")
        return self


def _base_document(base: LookBase) -> dict:
    return {
        "kind": base.kind.value,
        "source_asset_ids": list(base.source_asset_ids),
        "source_asset_parent_id": base.source_asset_parent_id,
        "twin_id": base.twin_id,
        "parent_look_id": base.parent_look_id,
        "parent_render_asset_id": base.parent_render_asset_id,
    }


def _base_from_document(data: dict) -> LookBase:
    return LookBase(
        kind=LookBaseKind(data["kind"]),
        source_asset_ids=tuple(data["source_asset_ids"]),
        source_asset_parent_id=data.get("source_asset_parent_id"),
        twin_id=data.get("twin_id"),
        parent_look_id=data.get("parent_look_id"),
        parent_render_asset_id=data.get("parent_render_asset_id"),
    )


def _operations_from_documents(items: list[dict]) -> tuple[ComponentOperation, ...]:
    result = []
    for item in items:
        result.append(ComponentOperation(
            operation_id=item["operation_id"],
            component=AppearanceComponent(item["component"]),
            action=EditAction(item["action"]),
            origin=OperationOrigin(item.get("origin", "user_directed")),
            reference_kind=ReferenceKind(item["reference_kind"]) if item.get("reference_kind") else None,
            reference_id=item.get("reference_id"),
            description=item.get("description"),
            target_regions=tuple(item.get("target_regions", [])),
            recommendation_track=RecommendationTrack(item["recommendation_track"]) if item.get("recommendation_track") else None,
            recommendation_id=item.get("recommendation_id"),
            parameters=tuple(sorted(item.get("parameters", {}).items())),
            preserve_unrequested_regions=True,
        ))
    return tuple(result)


def _operation_documents(operations: tuple[ComponentOperation, ...]) -> list[dict]:
    return [{
        "operation_id": item.operation_id,
        "component": item.component.value,
        "action": item.action.value,
        "origin": item.origin.value,
        "reference_kind": item.reference_kind.value if item.reference_kind else None,
        "reference_id": item.reference_id,
        "description": item.description,
        "target_regions": list(item.target_regions),
        "recommendation_track": item.recommendation_track.value if item.recommendation_track else None,
        "recommendation_id": item.recommendation_id,
        "parameters": dict(item.parameters),
        "preserve_unrequested_regions": True,
    } for item in operations]


def _validate_composition(*, look_id: str, subject_id: str, version: int, base: dict, operations: list[dict]) -> None:
    LookComposition(
        look_id=look_id,
        subject_id=subject_id,
        version=version,
        base=_base_from_document(base),
        operations=_operations_from_documents(operations),
    )


def _version_payload(version: AppearanceLookVersionRow) -> dict:
    return {
        "look_id": version.look_id,
        "subject_id": version.subject_id,
        "version": version.version,
        "action": version.action,
        "base": version.base_snapshot,
        "operations": version.operations_snapshot,
        "output_asset_id": version.output_asset_id,
        "renderer_id": version.renderer_id,
        "renderer_version": version.renderer_version,
        "fidelity_assessment": version.fidelity_assessment,
        "created_at": version.created_at.isoformat(),
    }


def _look_payload(row: AppearanceLookRow, *, version_row: AppearanceLookVersionRow | None = None) -> dict:
    version = version_row.version if version_row is not None else row.current_version
    base = version_row.base_snapshot if version_row is not None else row.base
    operations = version_row.operations_snapshot if version_row is not None else row.operations
    return {
        "look_id": row.look_id,
        "subject_id": row.subject_id,
        "consent_id": row.consent_id,
        "consent_version": row.consent_version,
        "version": version,
        "current_version": row.current_version,
        "base": base,
        "operations": operations,
        "is_favorite": row.is_favorite,
        "status": row.status,
        "output_asset_id": version_row.output_asset_id if version_row is not None else None,
    }


def _command_replay(db: Session, *, subject_id: str, command_id: str, payload_hash: str):
    existing = find_command(db, subject_id, command_id)
    if existing is None:
        return None
    if not hmac.compare_digest(existing.payload_sha256, payload_hash):
        raise HTTPException(409, detail={"code": "APPEARANCE_IDEMPOTENCY_CONFLICT"})
    row = db.get(AppearanceLookRow, existing.look_id)
    if row is None or row.subject_id != subject_id:
        raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
    return {"status": "replayed", "look": _look_payload(row, version_row=existing)}


def _save_version(
    db: Session, *, row: AppearanceLookRow, command_id: str, payload_hash: str,
    action: str, operations: list[dict], version: int,
) -> AppearanceLookVersionRow:
    _validate_composition(
        look_id=row.look_id, subject_id=row.subject_id, version=version,
        base=row.base, operations=operations,
    )
    now = utcnow()
    snapshot = AppearanceLookVersionRow(
        look_id=row.look_id,
        version=version,
        subject_id=row.subject_id,
        command_id=command_id,
        payload_sha256=payload_hash,
        action=action,
        base_snapshot=row.base,
        operations_snapshot=operations,
        output_asset_id=None,
        renderer_id=None,
        renderer_version=None,
        fidelity_assessment=None,
        created_at=now,
    )
    row.operations = operations
    row.current_version = version
    row.updated_at = now
    db.add(snapshot)
    return snapshot


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", dependencies=[Depends(require_internal_token)])
def ready():
    try:
        with _database() as db:
            db.execute(select(AppearanceLookRow.look_id).limit(1))
    except (HTTPException, SQLAlchemyError) as exc:
        raise HTTPException(503, detail={"code": "APPEARANCE_SCHEMA_NOT_READY"}) from exc
    providers = {}
    for url_key, token_key in (
        ("IDENTITY_SERVICE_URL", "IDENTITY_SERVICE_TOKEN"),
        ("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN"),
    ):
        providers[url_key] = bool(os.getenv(url_key, "").strip() and len(os.getenv(token_key, "").strip().encode()) >= 32)
    if not all(providers.values()):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": SERVICE, "ready": False, "providers": providers},
        )
    return {"status": "ready", "service": SERVICE, "ready": True, "database": "reachable", "providers": providers}


@app.post("/v1/looks", status_code=201, dependencies=[Depends(require_internal_token)])
async def create_look(payload: CreateLookIn):
    request_doc = payload.model_dump(mode="json", exclude_none=True)
    request_hash = _sha(request_doc)
    # A persistent look requires a distinct, expiring storage consent for this look.
    consent = await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=payload.consent_id,
        resource_id=payload.look_id,
        required_scopes=["appearance_session_storage"] if payload.base.kind == "virtual_twin"
        else ["appearance_session_storage", "appearance_source_storage", "image_processing"],
    )
    if payload.base.kind == "source_photo":
        for asset_id in payload.base.source_asset_ids:
            await _authorize_asset(
                subject_id=payload.subject_id,
                asset_id=asset_id,
                purpose="appearance_source_image",
                parent_id=payload.look_id,
            )
        base = LookBase(
            kind=LookBaseKind.SOURCE_PHOTO,
            source_asset_ids=tuple(payload.base.source_asset_ids),
            source_asset_parent_id=payload.look_id,
        )
    else:
        twin = await _authorize_twin(subject_id=payload.subject_id, twin_id=payload.base.twin_id)
        base = LookBase(
            kind=LookBaseKind.VIRTUAL_TWIN,
            source_asset_ids=tuple(twin["source_image_asset_ids"]),
            twin_id=payload.base.twin_id,
            source_asset_parent_id=payload.base.twin_id,
        )
    base_doc = _base_document(base)
    operations = _operation_documents(tuple(item.domain() for item in payload.operations))
    _validate_composition(
        look_id=payload.look_id, subject_id=payload.subject_id, version=1,
        base=base_doc, operations=operations,
    )

    with _database() as db:
        replay = _command_replay(
            db, subject_id=payload.subject_id, command_id=payload.idempotency_key,
            payload_hash=request_hash,
        )
        if replay is not None:
            return JSONResponse(status_code=200, content=replay)
        if db.get(AppearanceLookRow, payload.look_id) is not None:
            raise HTTPException(409, detail={"code": "APPEARANCE_LOOK_ALREADY_EXISTS"})
        now = utcnow()
        row = AppearanceLookRow(
            look_id=payload.look_id,
            subject_id=payload.subject_id,
            consent_id=payload.consent_id,
            consent_version=consent["consent_version"],
            base=base_doc,
            operations=operations,
            current_version=1,
            is_favorite=False,
            status="active",
            created_at=now,
            updated_at=now,
        )
        version_row = AppearanceLookVersionRow(
            look_id=payload.look_id,
            version=1,
            subject_id=payload.subject_id,
            command_id=payload.idempotency_key,
            payload_sha256=request_hash,
            action="create",
            base_snapshot=base_doc,
            operations_snapshot=operations,
            created_at=now,
        )
        db.add(row)
        db.add(version_row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, detail={"code": "APPEARANCE_LOOK_CREATE_CONFLICT"}) from exc
        return JSONResponse(status_code=201, content={"status": "created", "look": _look_payload(row, version_row=version_row)})


@app.get("/v1/looks", dependencies=[Depends(require_internal_token)])
async def list_looks(
    subject_id: str = Query(min_length=3, max_length=128),
    limit: int = Query(default=24, ge=1, le=50),
):
    """List minimal owner-scoped look metadata; expired sessions remain re-consentable."""
    _identifier(subject_id, "subject_id")
    with _database() as db:
        rows = list(db.scalars(
            select(AppearanceLookRow)
            .where(
                AppearanceLookRow.subject_id == subject_id,
                AppearanceLookRow.status == "active",
            )
            .order_by(AppearanceLookRow.updated_at.desc())
            .limit(limit)
        ).all())
        summaries = []
        for row in rows:
            try:
                await _verify_consent(
                    subject_id=subject_id,
                    consent_id=row.consent_id,
                    resource_id=row.look_id,
                    required_scopes=["appearance_session_storage"],
                )
                consent_required = False
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                consent_required = True
            summaries.append({
                "look_id": row.look_id,
                "base_kind": row.base.get("kind"),
                "version": row.current_version,
                "is_favorite": row.is_favorite,
                "updated_at": row.updated_at.isoformat(),
                "consent_required": consent_required,
            })
        return {"looks": summaries, "count": len(summaries)}


@app.get("/v1/looks/{look_id}", dependencies=[Depends(require_internal_token)])
async def get_look_endpoint(look_id: str, subject_id: str = Query(min_length=3, max_length=128)):
    _identifier(look_id, "look_id")
    consent_id = _consent_id_for_look(look_id, subject_id)
    await _verify_consent(
        subject_id=subject_id, consent_id=consent_id,
        resource_id=look_id, required_scopes=["appearance_session_storage"],
    )
    with _database() as db:
        row = get_look(db, subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        return {"look": _look_payload(row)}


@app.get("/v1/looks/{look_id}/versions", dependencies=[Depends(require_internal_token)])
async def list_versions(
    look_id: str,
    subject_id: str = Query(min_length=3, max_length=128),
):
    _identifier(look_id, "look_id")
    consent_id = _consent_id_for_look(look_id, subject_id)
    await _verify_consent(
        subject_id=subject_id, consent_id=consent_id,
        resource_id=look_id, required_scopes=["appearance_session_storage"],
    )
    with _database() as db:
        row = get_look(db, subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        versions = list(db.scalars(select(AppearanceLookVersionRow).where(
            AppearanceLookVersionRow.subject_id == subject_id,
            AppearanceLookVersionRow.look_id == look_id,
        ).order_by(AppearanceLookVersionRow.version.asc())).all())
        return {"look_id": look_id, "current_version": row.current_version, "versions": [_version_payload(v) for v in versions]}


@app.get("/v1/looks/{look_id}/compare", dependencies=[Depends(require_internal_token)])
async def compare_versions(
    look_id: str,
    subject_id: str = Query(min_length=3, max_length=128),
    from_version: int = Query(ge=1),
    to_version: int = Query(ge=1),
):
    _identifier(look_id, "look_id")
    consent_id = _consent_id_for_look(look_id, subject_id)
    await _verify_consent(
        subject_id=subject_id, consent_id=consent_id,
        resource_id=look_id, required_scopes=["appearance_session_storage"],
    )
    with _database() as db:
        row = get_look(db, subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        left = get_version(db, subject_id, look_id, from_version)
        right = get_version(db, subject_id, look_id, to_version)
        if left is None or right is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_VERSION_NOT_FOUND"})
        left_ops = {item["component"]: item for item in left.operations_snapshot}
        right_ops = {item["component"]: item for item in right.operations_snapshot}
        changed = sorted(
            key for key in set(left_ops) | set(right_ops)
            if left_ops.get(key) != right_ops.get(key)
        )
        return {
            "look_id": look_id,
            "from_version": from_version,
            "to_version": to_version,
            "changed_components": changed,
            "from_operations": left.operations_snapshot,
            "to_operations": right.operations_snapshot,
        }


async def _mutate(
    look_id: str,
    payload: MutateLookIn,
    *,
    action: str,
    new_operations: list[dict],
    request_doc: dict,
) -> dict:
    _identifier(look_id, "look_id")
    await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=_consent_id_for_look(look_id, payload.subject_id),
        resource_id=look_id,
        required_scopes=["appearance_session_storage"],
    )
    payload_hash = _sha(request_doc)
    with _database() as db:
        replay = _command_replay(
            db, subject_id=payload.subject_id, command_id=payload.command_id,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return replay
        row = get_look(db, payload.subject_id, look_id, lock=True)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        if row.current_version != payload.expected_version:
            raise HTTPException(409, detail={"code": "APPEARANCE_VERSION_CONFLICT", "current_version": row.current_version})
        version = row.current_version + 1
        try:
            version_row = _save_version(
                db, row=row, command_id=payload.command_id, payload_hash=payload_hash,
                action=action, operations=new_operations, version=version,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, detail={"code": "APPEARANCE_COMMAND_CONFLICT"}) from exc
        return {"status": "updated", "look": _look_payload(row, version_row=version_row)}


def _consent_id_for_look(look_id: str, subject_id: str) -> str:
    with _database() as db:
        row = get_look(db, subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        return row.consent_id


async def _revoke_identity_consent_bundle(
    *, subject_id: str, consent_id: str, resource_id: str,
) -> None:
    """Withdraw one exact subject/bundle/resource; one receipt revokes the complete bundle."""
    base, token = _provider_base("IDENTITY_SERVICE_URL", "IDENTITY_SERVICE_TOKEN")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=2.0),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        listing = await client.get(
            base + f"/v1/tal/consents/{subject_id}",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        if listing.status_code != 200:
            raise HTTPException(503, detail={"code": "APPEARANCE_OLD_CONSENT_LIST_UNAVAILABLE"})
        try:
            receipts = listing.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "APPEARANCE_OLD_CONSENT_LIST_INVALID"}) from exc
        if not isinstance(receipts, list):
            raise HTTPException(502, detail={"code": "APPEARANCE_OLD_CONSENT_LIST_INVALID"})
        active = [
            item for item in receipts
            if isinstance(item, dict)
            and item.get("consent_id") == consent_id
            and item.get("resource_id") == resource_id
            and item.get("granted") is True
            and item.get("revoked_at") is None
        ]
        if not active:
            return
        receipt_id = active[0].get("receipt_id")
        if not isinstance(receipt_id, str):
            raise HTTPException(502, detail={"code": "APPEARANCE_OLD_CONSENT_RECEIPT_INVALID"})
        response = await client.post(
            base + f"/v1/tal/consents/{receipt_id}/revoke",
            params={"subject_id": subject_id},
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        if response.status_code != 200:
            raise HTTPException(503, detail={"code": "APPEARANCE_OLD_CONSENT_REVOCATION_FAILED"})
        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "APPEARANCE_OLD_CONSENT_REVOCATION_INVALID"}) from exc
        if not isinstance(result, dict) or result.get("status") not in {"revoked", "already_denied"}:
            raise HTTPException(502, detail={"code": "APPEARANCE_OLD_CONSENT_REVOCATION_INVALID"})


def _deletion_payload(job: AppearanceLookDeletionRow) -> dict:
    return {
        "job_id": job.job_id,
        "look_id": job.look_id,
        "status": job.status,
        "consent_revoked": job.consent_revoked,
        "pending_asset_count": len(job.pending_asset_references),
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
    }


def _deletion_asset_references(db: Session, row: AppearanceLookRow) -> list[dict[str, str]]:
    """Collect only appearance-owned assets and preserve assets referenced by live child looks."""
    candidates: dict[str, dict[str, str]] = {}
    base = row.base
    base_kind = base.get("kind")

    if base_kind == LookBaseKind.SOURCE_PHOTO.value:
        for asset_id in base.get("source_asset_ids", []):
            candidates[asset_id] = {
                "asset_id": asset_id,
                "purpose": "appearance_source_image",
                "parent_id": row.look_id,
            }
    elif base_kind == LookBaseKind.PREVIOUS_RENDER.value:
        asset_id = base.get("parent_render_asset_id")
        parent_id = base.get("parent_look_id")
        if isinstance(asset_id, str) and isinstance(parent_id, str):
            candidates[asset_id] = {
                "asset_id": asset_id,
                "purpose": "appearance_render_output",
                "parent_id": parent_id,
            }
    # Virtual Twin source images belong to Twin Registry and are never deleted here.

    versions = list(db.scalars(select(AppearanceLookVersionRow).where(
        AppearanceLookVersionRow.subject_id == row.subject_id,
        AppearanceLookVersionRow.look_id == row.look_id,
    )).all())
    for version in versions:
        if version.output_asset_id:
            candidates[version.output_asset_id] = {
                "asset_id": version.output_asset_id,
                "purpose": "appearance_render_output",
                "parent_id": row.look_id,
            }

    referenced_by_live_looks: set[str] = set()
    other_looks = list(db.scalars(select(AppearanceLookRow).where(
        AppearanceLookRow.subject_id == row.subject_id,
        AppearanceLookRow.status == "active",
        AppearanceLookRow.look_id != row.look_id,
    )).all())
    for other in other_looks:
        other_base = other.base
        referenced_by_live_looks.update(
            item for item in other_base.get("source_asset_ids", [])
            if isinstance(item, str)
        )
        parent_render = other_base.get("parent_render_asset_id")
        if isinstance(parent_render, str):
            referenced_by_live_looks.add(parent_render)

    return [
        reference for asset_id, reference in sorted(candidates.items())
        if asset_id not in referenced_by_live_looks
    ]


async def _process_deletion_job(job_id: str) -> dict:
    """Retryable consent-revocation and private-asset deletion outbox processor."""
    with _database() as db:
        job = db.scalar(select(AppearanceLookDeletionRow).where(
            AppearanceLookDeletionRow.job_id == job_id
        ).with_for_update())
        if job is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_DELETION_JOB_NOT_FOUND"})
        if job.status == "completed":
            return _deletion_payload(job)
        if job.status == "processing" and job.updated_at > utcnow() - timedelta(minutes=5):
            return _deletion_payload(job)
        job.status = "processing"
        job.updated_at = utcnow()
        subject_id = job.subject_id
        consent_id = job.consent_id
        consent_revoked = job.consent_revoked
        pending = [dict(item) for item in job.pending_asset_references]
        db.commit()

    failures: list[str] = []
    if not consent_revoked:
        try:
            identity_base, identity_token = _provider_base(
                "IDENTITY_SERVICE_URL", "IDENTITY_SERVICE_TOKEN"
            )
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=2.0),
                trust_env=False,
                follow_redirects=False,
            ) as client:
                listing = await client.get(
                    identity_base + f"/v1/tal/consents/{subject_id}",
                    headers={"Authorization": "Bearer " + identity_token, "Accept": "application/json"},
                )
                if listing.status_code != 200:
                    raise RuntimeError("IDENTITY_CONSENT_LIST_UNAVAILABLE")
                receipts = listing.json()
                if not isinstance(receipts, list):
                    raise RuntimeError("IDENTITY_CONSENT_LIST_INVALID")
                matching = [
                    item for item in receipts
                    if isinstance(item, dict)
                    and item.get("consent_id") == consent_id
                    and item.get("resource_id") == job.look_id
                    and item.get("granted") is True
                ]
                active = [item for item in matching if item.get("revoked_at") is None]
                if active:
                    receipt_id = active[0].get("receipt_id")
                    if not isinstance(receipt_id, str):
                        raise RuntimeError("IDENTITY_CONSENT_RECEIPT_INVALID")
                    revoked = await client.post(
                        identity_base + f"/v1/tal/consents/{receipt_id}/revoke",
                        params={"subject_id": subject_id},
                        headers={"Authorization": "Bearer " + identity_token, "Accept": "application/json"},
                    )
                    if revoked.status_code != 200:
                        raise RuntimeError("IDENTITY_CONSENT_REVOCATION_FAILED")
                    revocation_result = revoked.json()
                    if not isinstance(revocation_result, dict) or revocation_result.get("status") not in {"revoked", "already_denied"}:
                        raise RuntimeError("IDENTITY_CONSENT_REVOCATION_RESPONSE_INVALID")
            consent_revoked = True
        except (HTTPException, httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
            failures.append(getattr(exc, "detail", None) or str(exc) or "IDENTITY_CONSENT_REVOCATION_FAILED")

    remaining: list[dict[str, str]] = []
    if pending:
        try:
            asset_base, asset_token = _provider_base(
                "ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN"
            )
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=2.0),
                trust_env=False,
                follow_redirects=False,
            ) as client:
                for reference in pending:
                    asset_id = reference["asset_id"]
                    try:
                        response = await client.delete(
                            asset_base + f"/v1/assets/{asset_id}",
                            headers={
                                "Authorization": "Bearer " + asset_token,
                                "X-Asset-Owner-ID": subject_id,
                                "Idempotency-Key": f"appearance-delete-{job_id}-{asset_id}",
                            },
                        )
                        if response.status_code != 204:
                            remaining.append(reference)
                            failures.append(f"ASSET_DELETE_{response.status_code}")
                    except httpx.HTTPError:
                        remaining.append(reference)
                        failures.append("ASSET_DELETE_PROVIDER_UNAVAILABLE")
        except HTTPException as exc:
            remaining = pending
            failures.append(exc.detail.get("code", "ASSET_SERVICE_NOT_CONFIGURED") if isinstance(exc.detail, dict) else "ASSET_SERVICE_NOT_CONFIGURED")
        except (httpx.HTTPError, ValueError):
            remaining = pending
            failures.append("ASSET_SERVICE_UNAVAILABLE")

    with _database() as db:
        job = db.scalar(select(AppearanceLookDeletionRow).where(
            AppearanceLookDeletionRow.job_id == job_id
        ).with_for_update())
        if job is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_DELETION_JOB_NOT_FOUND"})
        job.consent_revoked = consent_revoked
        job.pending_asset_references = remaining
        job.attempt_count += 1
        job.last_error = ";".join(failures)[:160] if failures else None
        job.status = "completed" if consent_revoked and not remaining else "retry"
        job.updated_at = utcnow()
        db.commit()
        db.refresh(job)
        return _deletion_payload(job)


@app.delete("/v1/looks/{look_id}", dependencies=[Depends(require_internal_token)])
async def delete_look(look_id: str, payload: DeleteLookIn):
    """Soft-delete the look immediately; revoke its bundle and delete unshared assets via a durable outbox."""
    _identifier(look_id, "look_id")
    request_document = {
        "look_id": look_id,
        "subject_id": payload.subject_id,
        "expected_version": payload.expected_version,
        "command_id": payload.command_id,
    }
    payload_hash = _sha(request_document)
    with _database() as db:
        replay = db.scalar(select(AppearanceLookDeletionRow).where(
            AppearanceLookDeletionRow.subject_id == payload.subject_id,
            AppearanceLookDeletionRow.command_id == payload.command_id,
        ))
        if replay is not None:
            if not hmac.compare_digest(replay.payload_sha256, payload_hash):
                raise HTTPException(409, detail={"code": "APPEARANCE_IDEMPOTENCY_CONFLICT"})
            job_id = replay.job_id
        else:
            row = db.scalar(select(AppearanceLookRow).where(
                AppearanceLookRow.subject_id == payload.subject_id,
                AppearanceLookRow.look_id == look_id,
            ).with_for_update())
            if row is None:
                raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
            existing_job = db.scalar(select(AppearanceLookDeletionRow).where(
                AppearanceLookDeletionRow.subject_id == payload.subject_id,
                AppearanceLookDeletionRow.look_id == look_id,
            ))
            if existing_job is not None:
                job_id = existing_job.job_id
            else:
                if row.status != "active":
                    raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
                if row.current_version != payload.expected_version:
                    raise HTTPException(409, detail={
                        "code": "APPEARANCE_VERSION_CONFLICT",
                        "current_version": row.current_version,
                    })
                asset_references = _deletion_asset_references(db, row)
                job_id = str(uuid.uuid4())
                now = utcnow()
                job = AppearanceLookDeletionRow(
                    job_id=job_id,
                    look_id=look_id,
                    subject_id=payload.subject_id,
                    consent_id=row.consent_id,
                    command_id=payload.command_id,
                    payload_sha256=payload_hash,
                    consent_revoked=False,
                    asset_references=asset_references,
                    pending_asset_references=asset_references,
                    status="queued",
                    attempt_count=0,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
                row.status = "deleted"
                row.updated_at = now
                db.add(job)
                db.commit()

    result = await _process_deletion_job(job_id)
    return {"status": "deleted" if result["status"] == "completed" else "deletion_pending", "deletion": result}


@app.post("/internal/v1/deletions/process", dependencies=[Depends(require_internal_token)])
async def process_deletions(limit: int = Query(default=20, ge=1, le=100)):
    with _database() as db:
        jobs = list(db.scalars(select(AppearanceLookDeletionRow).where(or_(
            AppearanceLookDeletionRow.status.in_(["queued", "retry"]),
            (
                (AppearanceLookDeletionRow.status == "processing")
                & (AppearanceLookDeletionRow.updated_at < utcnow() - timedelta(minutes=5))
            ),
        )).order_by(AppearanceLookDeletionRow.created_at.asc()).limit(limit)).all())
        job_ids = [job.job_id for job in jobs]
    results = []
    for job_id in job_ids:
        results.append(await _process_deletion_job(job_id))
    return {
        "processed": len(results),
        "completed": sum(item["status"] == "completed" for item in results),
        "pending": sum(item["status"] != "completed" for item in results),
        "jobs": results,
    }


@app.get("/internal/v1/looks/{look_id}/consent-context", dependencies=[Depends(require_internal_token)])
def get_look_consent_context(
    look_id: str,
    subject_id: str = Query(min_length=3, max_length=128),
):
    """Return only the metadata needed to request a fresh consent after expiry."""
    _identifier(look_id, "look_id")
    with _database() as db:
        row = get_look(db, subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        base_kind = row.base.get("kind")
        if base_kind == LookBaseKind.SOURCE_PHOTO.value:
            scopes = ["appearance_session_storage", "appearance_source_storage", "image_processing"]
        elif base_kind in {LookBaseKind.VIRTUAL_TWIN.value, LookBaseKind.PREVIOUS_RENDER.value}:
            scopes = ["appearance_session_storage"]
        else:
            raise HTTPException(409, detail={"code": "APPEARANCE_BASE_KIND_INVALID"})
        return {
            "look_id": row.look_id,
            "subject_id": row.subject_id,
            "base_kind": base_kind,
            "required_scopes": scopes,
            "consent_version": row.consent_version,
        }


@app.post("/internal/v1/looks/{look_id}/renew-consent", dependencies=[Depends(require_internal_token)])
async def renew_look_consent(look_id: str, payload: ConsentRenewalIn):
    """Atomically bind a new, verified consent bundle while preserving its history."""
    _identifier(look_id, "look_id")
    if consent["consent_version"] != payload.consent_version:
        raise HTTPException(403, detail={"code": "APPEARANCE_CONSENT_VERSION_MISMATCH"})
    if payload.consent_id != previous_consent_id:
        await _revoke_identity_consent_bundle(
            subject_id=payload.subject_id,
            consent_id=previous_consent_id,
            resource_id=look_id,
        )
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id, lock=True)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        base_kind = row.base.get("kind")
        if base_kind == LookBaseKind.SOURCE_PHOTO.value:
            required_scopes = ["appearance_session_storage", "appearance_source_storage", "image_processing"]
        elif base_kind in {LookBaseKind.VIRTUAL_TWIN.value, LookBaseKind.PREVIOUS_RENDER.value}:
            required_scopes = ["appearance_session_storage"]
        else:
            raise HTTPException(409, detail={"code": "APPEARANCE_BASE_KIND_INVALID"})
        previous_consent_id = row.consent_id

    consent = await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=payload.consent_id,
        resource_id=look_id,
        required_scopes=required_scopes,
    )
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id, lock=True)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        if row.consent_id == payload.consent_id:
            return {
                "status": "already_current",
                "look_id": look_id,
                "consent_version": row.consent_version,
                "granted_scopes": required_scopes,
            }
        if row.consent_id != previous_consent_id:
            raise HTTPException(409, detail={"code": "APPEARANCE_CONSENT_RENEWAL_CONFLICT"})
        event = AppearanceLookConsentEventRow(
            event_id=__import__("uuid").uuid4().__str__(),
            look_id=look_id,
            subject_id=payload.subject_id,
            previous_consent_id=previous_consent_id,
            consent_id=payload.consent_id,
            consent_version=consent["consent_version"],
            granted_scopes=required_scopes,
            created_at=utcnow(),
        )
        row.consent_id = payload.consent_id
        row.consent_version = consent["consent_version"]
        row.updated_at = utcnow()
        db.add(event)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, detail={"code": "APPEARANCE_CONSENT_RENEWAL_CONFLICT"}) from exc
        return {
            "status": "renewed",
            "look_id": look_id,
            "consent_version": row.consent_version,
            "granted_scopes": required_scopes,
        }


@app.post("/v1/looks/{look_id}/operations", dependencies=[Depends(require_internal_token)])
async def apply_operation(look_id: str, payload: ApplyOperationIn):
    operation = payload.operation.domain()
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        operations = [item for item in row.operations if item.get("component") != operation.component.value]
    operations.append(payload.operation.document())
    _validate_composition(
        look_id=look_id, subject_id=payload.subject_id,
        version=payload.expected_version + 1, base=row.base, operations=operations,
    )
    return await _mutate(
        look_id, payload, action="operation", new_operations=operations,
        request_doc={
            "look_id": look_id, "expected_version": payload.expected_version,
            "command_id": payload.command_id, "operation": payload.operation.document(),
        },
    )


@app.post("/v1/looks/{look_id}/reset", dependencies=[Depends(require_internal_token)])
async def reset_look(look_id: str, payload: MutateLookIn):
    return await _mutate(
        look_id, payload, action="reset", new_operations=[],
        request_doc={
            "look_id": look_id, "expected_version": payload.expected_version,
            "command_id": payload.command_id, "action": "reset",
        },
    )


@app.post("/v1/looks/{look_id}/undo", dependencies=[Depends(require_internal_token)])
async def undo_look(look_id: str, payload: UndoLookIn):
    if payload.target_version >= payload.expected_version:
        raise HTTPException(422, detail={"code": "APPEARANCE_UNDO_TARGET_MUST_BE_OLDER"})
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id)
        target = get_version(db, payload.subject_id, look_id, payload.target_version)
        if row is None or target is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_VERSION_NOT_FOUND"})
        operations = target.operations_snapshot
    return await _mutate(
        look_id, payload, action="undo", new_operations=operations,
        request_doc={
            "look_id": look_id, "expected_version": payload.expected_version,
            "target_version": payload.target_version, "command_id": payload.command_id,
            "action": "undo",
        },
    )


@app.post("/v1/looks/{look_id}/favorite", dependencies=[Depends(require_internal_token)])
async def set_favorite(look_id: str, payload: FavoriteIn):
    _identifier(look_id, "look_id")
    consent_id = _consent_id_for_look(look_id, payload.subject_id)
    await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=consent_id,
        resource_id=look_id,
        required_scopes=["appearance_session_storage"],
    )
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id, lock=True)
        if row is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_LOOK_NOT_FOUND"})
        row.is_favorite = payload.is_favorite
        row.updated_at = utcnow()
        db.commit()
        return {"look": _look_payload(row), "status": "updated"}


@app.post("/v1/looks/{look_id}/branch", status_code=201, dependencies=[Depends(require_internal_token)])
async def branch_from_render(look_id: str, payload: BranchLookIn):
    _identifier(look_id, "look_id")
    parent_consent_id = _consent_id_for_look(look_id, payload.subject_id)
    await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=parent_consent_id,
        resource_id=look_id,
        required_scopes=["appearance_session_storage"],
    )
    branch_consent = await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=payload.consent_id,
        resource_id=payload.new_look_id,
        required_scopes=["appearance_session_storage"],
    )
    with _database() as db:
        parent = get_look(db, payload.subject_id, look_id)
        parent_version = get_version(db, payload.subject_id, look_id, payload.parent_version)
        if parent is None or parent_version is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_PARENT_VERSION_NOT_FOUND"})
        if parent_version.output_asset_id is None or not parent_version.fidelity_assessment:
            raise HTTPException(409, detail={"code": "APPEARANCE_PARENT_RENDER_NOT_READY"})
        if parent_version.fidelity_assessment.get("disposition") != "releasable":
            raise HTTPException(409, detail={"code": "APPEARANCE_PARENT_RENDER_NOT_RELEASABLE"})
        if db.get(AppearanceLookRow, payload.new_look_id) is not None:
            raise HTTPException(409, detail={"code": "APPEARANCE_LOOK_ALREADY_EXISTS"})
        parent_base = _base_from_document(parent_version.base_snapshot)
        branch_base = LookBase(
            kind=LookBaseKind.PREVIOUS_RENDER,
            source_asset_ids=(parent_version.output_asset_id,),
            source_asset_parent_id=look_id,
            twin_id=parent_base.twin_id,
            parent_look_id=look_id,
            parent_render_asset_id=parent_version.output_asset_id,
        )
        branch_doc = _base_document(branch_base)
        _validate_composition(
            look_id=payload.new_look_id, subject_id=payload.subject_id,
            version=1, base=branch_doc, operations=[],
        )
    await _authorize_asset(
        subject_id=payload.subject_id,
        asset_id=parent_version.output_asset_id,
        purpose="appearance_render_output",
        parent_id=look_id,
    )
    request_hash = _sha(payload.model_dump(mode="json"))
    with _database() as db:
        replay = _command_replay(
            db, subject_id=payload.subject_id, command_id=payload.command_id,
            payload_hash=request_hash,
        )
        if replay is not None:
            return JSONResponse(status_code=200, content=replay)
        if db.get(AppearanceLookRow, payload.new_look_id) is not None:
            raise HTTPException(409, detail={"code": "APPEARANCE_LOOK_ALREADY_EXISTS"})
        now = utcnow()
        row = AppearanceLookRow(
            look_id=payload.new_look_id, subject_id=payload.subject_id,
            consent_id=payload.consent_id, consent_version=branch_consent["consent_version"],
            base=branch_doc, operations=[], current_version=1,
            is_favorite=False, status="active", created_at=now, updated_at=now,
        )
        version = AppearanceLookVersionRow(
            look_id=payload.new_look_id, version=1, subject_id=payload.subject_id,
            command_id=payload.command_id, payload_sha256=request_hash,
            action="branch", base_snapshot=branch_doc, operations_snapshot=[],
            created_at=now,
        )
        db.add(row)
        db.add(version)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, detail={"code": "APPEARANCE_BRANCH_CONFLICT"}) from exc
        return JSONResponse(status_code=201, content={"status": "created", "look": _look_payload(row, version_row=version)})


@app.post("/internal/v1/looks/{look_id}/render-result", dependencies=[Depends(require_renderer_token)])
async def attach_render_result(look_id: str, payload: RenderResultIn):
    _identifier(look_id, "look_id")
    consent_id = _consent_id_for_look(look_id, payload.subject_id)
    await _verify_consent(
        subject_id=payload.subject_id,
        consent_id=consent_id,
        resource_id=look_id,
        required_scopes=["appearance_session_storage"],
    )
    checks = tuple((item.gate, item.status) for item in payload.checks)
    try:
        assessment = FidelityAssessment(
            assessment_id=payload.assessment_id,
            look_id=look_id,
            look_version=payload.version,
            output_asset_id=payload.output_asset_id,
            model_version=payload.renderer_version,
            checks=checks,
        )
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "APPEARANCE_FIDELITY_ASSESSMENT_INVALID"}) from exc
    if assessment.disposition != "releasable":
        raise HTTPException(409, detail={"code": "APPEARANCE_RENDER_NOT_RELEASABLE", "disposition": assessment.disposition})
    await _authorize_asset(
        subject_id=payload.subject_id,
        asset_id=payload.output_asset_id,
        purpose="appearance_render_output",
        parent_id=look_id,
    )
    assessment_doc = {
        "assessment_id": assessment.assessment_id,
        "look_id": assessment.look_id,
        "look_version": assessment.look_version,
        "output_asset_id": assessment.output_asset_id,
        "model_version": assessment.model_version,
        "checks": [{"gate": gate.value, "status": status.value} for gate, status in assessment.checks],
        "disposition": assessment.disposition,
    }
    with _database() as db:
        row = get_look(db, payload.subject_id, look_id, lock=True)
        version = get_version(db, payload.subject_id, look_id, payload.version)
        if row is None or version is None:
            raise HTTPException(404, detail={"code": "APPEARANCE_VERSION_NOT_FOUND"})
        if version.output_asset_id and version.output_asset_id != payload.output_asset_id:
            raise HTTPException(409, detail={"code": "APPEARANCE_RENDER_ALREADY_ATTACHED"})
        version.output_asset_id = payload.output_asset_id
        version.renderer_id = payload.renderer_id
        version.renderer_version = payload.renderer_version
        version.fidelity_assessment = assessment_doc
        db.commit()
        return {"status": "attached", "look_id": look_id, "version": payload.version, "output_asset_id": payload.output_asset_id, "fidelity": assessment_doc}


@app.get("/ready/schema", dependencies=[Depends(require_internal_token)])
def schema_ready():
    try:
        with _database() as db:
            db.execute(select(AppearanceLookVersionRow.look_id).limit(1))
    except (HTTPException, SQLAlchemyError) as exc:
        raise HTTPException(503, detail={"code": "APPEARANCE_SCHEMA_NOT_READY"}) from exc
    return {"ready": True, "tables": ["appearance_look_sessions", "appearance_look_versions"]}


if os.getenv("APPEARANCE_AUTO_CREATE_SCHEMA", "").strip().lower() == "true":
    database_url = os.getenv("APPEARANCE_DATABASE_URL", "").strip()
    if database_url:
        Base.metadata.create_all(bind=engine(database_url))

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError

from app.store import Base as TryOnBase, engine as tryon_engine, get_store

SERVICE_NAME = "cirvanna-virtual-try-on"
API_VERSION = "2.0.0"
ASSET_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
bearer = HTTPBearer(auto_error=False)

app = FastAPI(
    title="Cirvanna Virtual Try-On API",
    version=API_VERSION,
    description="Consent-gated, idempotent orchestration around a private VTON GPU worker and owner-scoped asset service.",
)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent_id: str = Field(min_length=8, max_length=160)
    image_processing: bool
    virtual_try_on: bool
    retention_policy: Literal["ephemeral"] = "ephemeral"


class TryOnRequest(BaseModel):
    """Internal asset references and versioned look context; never accept URLs."""
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=8, max_length=128)
    product_id: str = Field(min_length=3, max_length=128)
    person_image_asset_id: str = Field(min_length=36, max_length=36)
    garment_image_asset_id: str = Field(min_length=36, max_length=36)
    garment_asset_purpose: Literal["catalog_garment_image", "wardrobe_garment_image"] = "catalog_garment_image"
    garment_asset_parent_id: str | None = Field(default=None, min_length=3, max_length=160)
    garment_category: Literal["upper_body", "lower_body", "dress", "outerwear", "full_outfit"]
    look_id: str | None = Field(default=None, min_length=3, max_length=128)
    look_version: int | None = Field(default=None, ge=1)
    wardrobe_snapshot_version: int | None = Field(default=None, ge=1)
    consent: ConsentInput

    @field_validator("person_image_asset_id", "garment_image_asset_id")
    @classmethod
    def validate_asset_ids(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not ASSET_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Asset IDs must be opaque UUIDs, not URLs or paths.")
        return normalized

    @field_validator("request_id", "subject_id", "twin_id", "product_id")
    @classmethod
    def trim_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identifier must not be blank.")
        return normalized

    @model_validator(mode="after")
    def consistent_look_version(self):
        if self.garment_asset_purpose == "catalog_garment_image":
            if self.garment_asset_parent_id and self.garment_asset_parent_id != self.product_id:
                raise ValueError("Catalog garment asset parent must match product_id.")
        elif not self.garment_asset_parent_id:
            raise ValueError("Wardrobe garment assets require their wardrobe item parent ID.")
        if self.look_id and (self.look_version is None or self.wardrobe_snapshot_version is None):
            raise ValueError("A PNELLY look render requires both look_version and wardrobe_snapshot_version.")
        if not self.look_id and (self.look_version is not None or self.wardrobe_snapshot_version is not None):
            raise ValueError("Look versions cannot be supplied without look_id.")
        return self

    @property
    def garment_parent(self) -> str:
        return self.garment_asset_parent_id or self.product_id


class TryOnResult(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    request_id: str
    status: Literal["complete"]
    renderer_id: str
    renderer_version: str
    output_asset_id: str
    output_expires_after_hours: int
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)


class CapabilityResponse(BaseModel):
    service: str
    api_version: str
    orchestration_api: bool
    renderer_configured: bool
    consent_verifier_configured: bool
    asset_service_configured: bool
    twin_service_configured: bool
    database_ready: bool
    supported_categories: list[str]
    raw_image_upload: bool
    arbitrary_remote_urls: bool
    output_persistence: bool
    reason: str | None = None


def _trusted_base(url_key: str, token_key: str) -> tuple[str, str] | None:
    raw = os.getenv(url_key, "").strip().rstrip("/")
    token = os.getenv(token_key, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        if (
            not host or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
            or (parts.scheme != "https" and not (parts.scheme == "http" and local))
        ):
            return None
    except ValueError:
        return None
    return raw, token


def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("VIRTUAL_TRY_ON_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"}, headers={"WWW-Authenticate": "Bearer"})


def _payload_hash(payload: TryOnRequest) -> str:
    serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def _json_request(method: str, base: str, path: str, token: str, *, json_body: dict | None = None):
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            return await client.request(
                method, base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=json_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "INTERNAL_PROVIDER_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "INTERNAL_PROVIDER_UNAVAILABLE"}) from exc


async def _verify_consent_bundle(subject_id: str, consent_id: str, twin_id: str) -> dict:
    config = _trusted_base("CONSENT_API_URL", "CONSENT_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    base, token = config
    response = await _json_request(
        "POST", base, "/internal/v1/consents/verify", token,
        json_body={
            "subject_id": subject_id,
            "consent_id": consent_id,
            "required_scopes": ["image_processing", "virtual_try_on", "virtual_twin_storage"],
            "resource_id": twin_id,
        },
    )
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CONSENT_VERIFIER_INVALID_RESPONSE"}) from exc
    if not (
        isinstance(receipt, dict) and receipt.get("verified") is True
        and receipt.get("active") is True and receipt.get("subject_id") == subject_id
        and receipt.get("consent_id") == consent_id
        and receipt.get("resource_id") == twin_id
        and set(["image_processing", "virtual_try_on", "virtual_twin_storage"]).issubset(set(receipt.get("granted_scopes", [])))
    ):
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})
    return receipt


async def _verify_consent(payload: TryOnRequest) -> dict:
    return await _verify_consent_bundle(payload.subject_id, payload.consent.consent_id, payload.twin_id)

async def _resolve_twin_by_ids(subject_id: str, twin_id: str) -> dict:
    """Use the canonical owner/consent/asset-checked Twin registry contract."""
    config = _trusted_base("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_SERVICE_NOT_CONFIGURED"})
    base, token = config
    response = await _json_request(
        "POST", base, "/internal/v1/twins/authorize", token,
        json_body={"subject_id": subject_id, "twin_id": twin_id},
    )
    if response.status_code in {403, 404}:
        raise HTTPException(404, detail={"code": "TWIN_NOT_FOUND_OR_NOT_AUTHORIZED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_SERVICE_UNAVAILABLE"})
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "TWIN_SERVICE_INVALID_RESPONSE"}) from exc
    source_ids = body.get("source_image_asset_ids") if isinstance(body, dict) else None
    if not (
        isinstance(body, dict) and body.get("authorized") is True
        and body.get("active") is True and body.get("subject_id") == subject_id
        and body.get("twin_id") == twin_id
        and body.get("representation_type") == "full_body_mesh"
        and isinstance(source_ids, list) and source_ids
        and all(isinstance(item, str) and item for item in source_ids)
    ):
        raise HTTPException(403, detail={"code": "TWIN_NOT_AUTHORIZED"})
    return {**body, "status": "active", "source_image_asset_ids": source_ids}


async def _resolve_twin(payload: TryOnRequest) -> dict:
    twin = await _resolve_twin_by_ids(payload.subject_id, payload.twin_id)
    if payload.person_image_asset_id not in twin.get("source_image_asset_ids", []):
        raise HTTPException(403, detail={"code": "TWIN_PERSON_ASSET_MISMATCH"})
    return twin


async def _read_authorized_asset(
    *, subject_id: str, asset_id: str, purpose: str, parent_id: str,
) -> tuple[bytes, str]:
    config = _trusted_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_NOT_CONFIGURED"})
    base, token = config
    authorized = await _json_request(
        "POST", base, "/internal/v1/assets/authorize", token,
        json_body={
            "subject_id": subject_id, "asset_id": asset_id,
            "purpose": purpose, "parent_id": parent_id,
        },
    )
    if authorized.status_code in {403, 404}:
        raise HTTPException(403, detail={"code": "ASSET_ACCESS_DENIED"})
    if authorized.status_code != 200:
        raise HTTPException(503, detail={"code": "ASSET_AUTHORIZATION_UNAVAILABLE"})
    try:
        metadata = authorized.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "ASSET_AUTHORIZATION_INVALID"}) from exc
    if not (
        isinstance(metadata, dict) and metadata.get("authorized") is True
        and metadata.get("subject_id") == subject_id and metadata.get("asset_id") == asset_id
        and metadata.get("purpose") == purpose and metadata.get("parent_id") == parent_id
    ):
        raise HTTPException(403, detail={"code": "ASSET_ACCESS_DENIED"})
    response = await _json_request(
        "GET", base,
        f"/internal/v1/assets/{quote(asset_id, safe='')}/content?{urlencode({'subject_id': subject_id, 'purpose': purpose, 'parent_id': parent_id})}",
        token,
    )
    if response.status_code in {403, 404}:
        raise HTTPException(403, detail={"code": "ASSET_ACCESS_DENIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "ASSET_CONTENT_UNAVAILABLE"})
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(415, detail={"code": "ASSET_CONTENT_TYPE_INVALID"})
    data = response.content
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "ASSET_CONTENT_SIZE_INVALID"})
    return data, content_type


async def _worker_ready() -> tuple[str, str] | None:
    config = _trusted_base("VTON_WORKER_URL", "VTON_WORKER_TOKEN")
    if config is None:
        return None
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.get(
                base + "/ready",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
        if response.status_code != 200:
            return None
        result = response.json()
        source_commit = result.get("source_commit") if isinstance(result, dict) else None
        if not isinstance(source_commit, str) or not SHA40.fullmatch(source_commit):
            return None
        return base, token
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _validated_png(data: bytes) -> bool:
    if not data or len(data) > MAX_IMAGE_BYTES:
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width < 64 or image.height < 64:
                return False
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return False
            image.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


async def _render_with_worker(payload: TryOnRequest, person: tuple[bytes, str], garment: tuple[bytes, str]) -> tuple[bytes, str]:
    config = await _worker_ready()
    if config is None:
        raise HTTPException(503, detail={"code": "VTON_RENDERER_NOT_READY"})
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=5.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/v1/render",
                headers={"Authorization": "Bearer " + token, "Accept": "image/png"},
                data={
                    "consent_image_processing": "true",
                    "consent_virtual_try_on": "true",
                    "category": payload.garment_category,
                },
                files={
                    "person_image": ("person.png", person[0], person[1]),
                    "garment_image": ("garment.png", garment[0], garment[1]),
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "VTON_RENDER_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "VTON_RENDER_WORKER_UNAVAILABLE"}) from exc
    if response.status_code != 200 or response.headers.get("content-type", "").split(";")[0].lower() != "image/png":
        raise HTTPException(502, detail={"code": "VTON_RENDER_FAILED"})
    if not _validated_png(response.content):
        raise HTTPException(502, detail={"code": "VTON_RENDER_OUTPUT_INVALID"})
    model_commit = response.headers.get("X-Cirvanna-Model-Commit", "")
    if not SHA40.fullmatch(model_commit):
        raise HTTPException(502, detail={"code": "VTON_MODEL_PROVENANCE_MISSING"})
    return response.content, "fashn-vton-1.5@" + model_commit


async def _persist_output_asset(payload: TryOnRequest, image_bytes: bytes) -> str:
    config = _trusted_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_NOT_CONFIGURED"})
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/assets",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                data={
                    "owner_user_id": payload.subject_id,
                    "purpose": "try_on_output",
                    "parent_id": payload.twin_id,
                    "retention_days": "1",
                },
                files={"file": ("try-on.png", image_bytes, "image/png")},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "VTON_OUTPUT_STORAGE_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "VTON_OUTPUT_STORAGE_UNAVAILABLE"}) from exc
    if response.status_code != 201:
        raise HTTPException(503, detail={"code": "VTON_OUTPUT_STORAGE_FAILED"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "VTON_OUTPUT_STORAGE_INVALID"}) from exc
    output_id = result.get("asset_id") if isinstance(result, dict) else None
    if (
        not isinstance(output_id, str) or not ASSET_ID_PATTERN.fullmatch(output_id)
        or result.get("owner_user_id") != payload.subject_id
        or result.get("purpose") != "try_on_output" or result.get("parent_id") != payload.twin_id
    ):
        raise HTTPException(502, detail={"code": "VTON_OUTPUT_ASSET_SCOPE_MISMATCH"})
    return output_id


async def _delete_output_asset(subject_id: str, twin_id: str, asset_id: str) -> None:
    config = _trusted_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    if config is None:
        return
    base, token = config
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            await client.delete(
                base + f"/v1/assets/{asset_id}",
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Asset-Owner-ID": subject_id,
                    "Idempotency-Key": "vton-rollback-" + asset_id,
                },
            )
    except httpx.HTTPError:
        pass


def _response_from_job(job: dict) -> TryOnResult:
    result = job["result"]
    return TryOnResult(
        request_id=result["request_id"],
        status="complete",
        renderer_id=result["renderer_id"],
        renderer_version=result["renderer_version"],
        output_asset_id=result["output_asset_id"],
        output_expires_after_hours=24,
        created_at=datetime.fromisoformat(result["created_at"]),
        warnings=result.get("warnings", []),
    )


@app.on_event("startup")
def initialize_tryon_schema() -> None:
    if os.getenv("VIRTUAL_TRY_ON_AUTO_CREATE_SCHEMA", "false").lower() == "true":
        url = os.getenv("VIRTUAL_TRY_ON_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("VIRTUAL_TRY_ON_DATABASE_URL is required")
        TryOnBase.metadata.create_all(bind=tryon_engine(url))


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/ready", tags=["operations"])
async def ready() -> dict[str, object]:
    database_ready = False
    try:
        get_store().ready()
        database_ready = True
    except Exception:
        pass
    consent_ready = _trusted_base("CONSENT_API_URL", "CONSENT_API_TOKEN") is not None
    asset_ready = _trusted_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN") is not None
    twin_ready = _trusted_base("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN") is not None
    worker_ready = await _worker_ready() is not None
    auth_ready = len(os.getenv("VIRTUAL_TRY_ON_API_TOKEN", "").encode()) >= 32
    ready_now = all((database_ready, consent_ready, asset_ready, twin_ready, worker_ready, auth_ready))
    if not ready_now:
        missing = [
            key for key, value in (
                ("database", database_ready), ("consent_provider", consent_ready),
                ("asset_service", asset_ready), ("twin_service", twin_ready),
                ("gpu_renderer", worker_ready), ("api_auth", auth_ready),
            ) if not value
        ]
        raise HTTPException(503, detail={
            "status": "not_ready", "service": SERVICE_NAME, "ready": False,
            "missing_dependencies": missing,
        })
    return {
        "status": "ready", "service": SERVICE_NAME, "ready": True,
        "database": "reachable", "consent_provider": True,
        "asset_service": True, "twin_service": True, "gpu_renderer": True,
    }


@app.get("/capabilities", response_model=CapabilityResponse, tags=["operations"])
async def capabilities() -> CapabilityResponse:
    database_ready = False
    try:
        get_store().ready()
        database_ready = True
    except Exception:
        pass
    consent_ready = _trusted_base("CONSENT_API_URL", "CONSENT_API_TOKEN") is not None
    asset_ready = _trusted_base("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN") is not None
    twin_ready = _trusted_base("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN") is not None
    renderer_ready = await _worker_ready() is not None
    configured = database_ready and consent_ready and asset_ready and twin_ready and renderer_ready
    return CapabilityResponse(
        service=SERVICE_NAME, api_version=API_VERSION, orchestration_api=True,
        renderer_configured=renderer_ready, consent_verifier_configured=consent_ready,
        asset_service_configured=asset_ready, twin_service_configured=twin_ready,
        database_ready=database_ready,
        supported_categories=["upper_body", "lower_body", "dress", "outerwear", "full_outfit"],
        raw_image_upload=False, arbitrary_remote_urls=False,
        output_persistence=asset_ready,
        reason=None if configured else "postgres_consent_twin_asset_or_pinned_gpu_renderer_not_ready",
    )


@app.post("/v1/try-ons", response_model=TryOnResult, tags=["try-on"])
async def create_try_on(payload: TryOnRequest, _: Annotated[None, Depends(require_api_token)]) -> TryOnResult:
    """Render only while current consent, Twin ownership and asset bindings remain valid."""
    if not payload.consent.image_processing or not payload.consent.virtual_try_on:
        raise HTTPException(403, detail={"code": "CONSENT_REQUIRED"})
    if _trusted_base("CONSENT_API_URL", "CONSENT_API_TOKEN") is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    try:
        store = get_store()
        store.ready()
    except Exception as exc:
        raise HTTPException(503, detail={"code": "TRY_ON_DATABASE_NOT_READY"}) from exc

    digest = _payload_hash(payload)
    consent = await _verify_consent(payload)
    consent_version = consent.get("consent_version")
    if not isinstance(consent_version, str) or not consent_version:
        raise HTTPException(502, detail={"code": "CONSENT_VERSION_MISSING"})
    await _resolve_twin(payload)

    try:
        reservation = store.reserve({
            "subject_id": payload.subject_id, "request_id": payload.request_id,
            "payload_hash": digest, "twin_id": payload.twin_id,
            "product_id": payload.product_id,
            "person_image_asset_id": payload.person_image_asset_id,
            "garment_image_asset_id": payload.garment_image_asset_id,
            "garment_asset_purpose": payload.garment_asset_purpose,
            "garment_asset_parent_id": payload.garment_parent,
            "garment_category": payload.garment_category,
            "look_id": payload.look_id, "look_version": payload.look_version,
            "wardrobe_snapshot_version": payload.wardrobe_snapshot_version,
            "consent_id": payload.consent.consent_id, "consent_version": consent_version,
        })
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "TRY_ON_IDEMPOTENCY_CONFLICT"}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "TRY_ON_JOB_RESERVATION_FAILED"}) from exc
    if not reservation["acquired"]:
        existing = reservation["job"]
        if existing["status"] == "complete":
            await _read_authorized_asset(
                subject_id=payload.subject_id,
                asset_id=existing["output_asset_id"],
                purpose="try_on_output",
                parent_id=payload.twin_id,
            )
            return _response_from_job(existing)
        raise HTTPException(409, detail={"code": "TRY_ON_ALREADY_IN_PROGRESS"})

    output_asset_id: str | None = None
    try:
        person = await _read_authorized_asset(subject_id=payload.subject_id, asset_id=payload.person_image_asset_id, purpose="twin_source_image", parent_id=payload.twin_id)
        garment = await _read_authorized_asset(subject_id=payload.subject_id, asset_id=payload.garment_image_asset_id, purpose=payload.garment_asset_purpose, parent_id=payload.garment_parent)
        rendered, renderer_version = await _render_with_worker(payload, person, garment)

        # Inference may outlive consent or asset authorization. Revalidate before writing output.
        consent_after = await _verify_consent(payload)
        if consent_after.get("consent_version") != consent_version:
            raise HTTPException(403, detail={"code": "CONSENT_CHANGED_DURING_RENDER"})
        await _resolve_twin(payload)
        await _read_authorized_asset(subject_id=payload.subject_id, asset_id=payload.person_image_asset_id, purpose="twin_source_image", parent_id=payload.twin_id)
        await _read_authorized_asset(subject_id=payload.subject_id, asset_id=payload.garment_image_asset_id, purpose=payload.garment_asset_purpose, parent_id=payload.garment_parent)

        output_asset_id = await _persist_output_asset(payload, rendered)
        # Re-check after the storage write and before marking the job complete.
        final_consent = await _verify_consent(payload)
        if final_consent.get("consent_version") != consent_version:
            raise HTTPException(403, detail={"code": "CONSENT_REVOKED_BEFORE_COMPLETION"})
        await _resolve_twin(payload)
        await _read_authorized_asset(subject_id=payload.subject_id, asset_id=output_asset_id, purpose="try_on_output", parent_id=payload.twin_id)

        created_at = datetime.now(timezone.utc)
        result = {
            "request_id": payload.request_id, "renderer_id": "fashn-vton-1.5",
            "renderer_version": renderer_version, "output_asset_id": output_asset_id,
            "created_at": created_at.isoformat(),
            "warnings": [
                "Visual preview only; not a fit guarantee.",
                "Output asset expires after 24 hours unless retained under a separate explicit product action.",
            ],
        }
        try:
            saved = store.complete(payload.subject_id, payload.request_id, {
                "output_asset_id": output_asset_id, "renderer_id": "fashn-vton-1.5",
                "renderer_version": renderer_version, "created_at": created_at, "result": result,
            })
        except Exception as exc:
            raise HTTPException(503, detail={"code": "TRY_ON_RESULT_PERSISTENCE_FAILED"}) from exc
        return _response_from_job(saved)
    except Exception:
        if output_asset_id is not None:
            await _delete_output_asset(payload.subject_id, payload.twin_id, output_asset_id)
        try:
            store.fail(payload.subject_id, payload.request_id)
        except Exception:
            pass
        raise


@app.get("/v1/try-ons/{request_id}", tags=["try-on"])
async def get_try_on(
    request_id: str,
    subject_id: str,
    _: Annotated[None, Depends(require_api_token)],
):
    try:
        result = get_store().get(subject_id, request_id)
    except Exception as exc:
        raise HTTPException(503, detail={"code": "TRY_ON_DATABASE_UNAVAILABLE"}) from exc
    if result is None:
        raise HTTPException(404, detail={"code": "TRY_ON_NOT_FOUND"})
    await _verify_consent_bundle(subject_id, result["consent_id"], result["twin_id"])
    twin = await _resolve_twin_by_ids(subject_id, result["twin_id"])
    if result["person_image_asset_id"] not in twin.get("source_image_asset_ids", []):
        raise HTTPException(410, detail={"code": "TWIN_SOURCE_VERSION_CHANGED"})
    await _read_authorized_asset(
        subject_id=subject_id,
        asset_id=result["output_asset_id"],
        purpose="try_on_output",
        parent_id=result["twin_id"],
    )
    return JSONResponse(content=result["result"], headers={"Cache-Control": "no-store, private"})

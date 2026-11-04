"""Guarded Virtual Try-On orchestration API.

No renderer is enabled by default. This API accepts opaque internal asset IDs,
not arbitrary image URLs or uploaded photos, and will not fabricate render
results. A provider must implement the Renderer protocol and pass validation
before being registered in RENDERER.
"""
from __future__ import annotations

import hmac
import os
import re
import uuid
from urllib.parse import urlsplit

import httpx
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette import status

SERVICE_NAME = "cirvanna-virtual-try-on"
API_VERSION = "1.0.0"
ASSET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
bearer = HTTPBearer(auto_error=False)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent_id: str = Field(min_length=8, max_length=160)
    image_processing: bool
    virtual_try_on: bool
    retention_policy: str = Field(default="ephemeral", min_length=1, max_length=32)


class TryOnRequest(BaseModel):
    """Asset references must resolve through an authenticated internal asset service."""
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=128)
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=3, max_length=128)
    product_id: str = Field(min_length=3, max_length=128)
    person_image_asset_id: str = Field(min_length=3, max_length=160)
    garment_image_asset_id: str = Field(min_length=3, max_length=160)
    garment_category: Literal["upper_body", "lower_body", "dress", "outerwear", "full_outfit"]
    consent: ConsentInput

    @field_validator("person_image_asset_id", "garment_image_asset_id")
    @classmethod
    def validate_asset_ids(cls, value: str) -> str:
        normalized = value.strip()
        if not ASSET_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Asset IDs must be opaque internal identifiers, not URLs or file paths.")
        if "://" in normalized or "/" in normalized or "\\" in normalized:
            raise ValueError("External URLs and file paths are not accepted.")
        return normalized

    @field_validator("request_id", "subject_id", "twin_id", "product_id")
    @classmethod
    def trim_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identifier must not be blank.")
        return normalized


class TryOnResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    status: Literal["complete"]
    renderer_id: str
    renderer_version: str
    output_asset_id: str
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)


class CapabilityResponse(BaseModel):
    service: str
    api_version: str
    orchestration_api: bool
    renderer_configured: bool
    consent_verifier_configured: bool
    asset_authorizer_configured: bool
    supported_categories: list[str]
    raw_image_upload: bool
    arbitrary_remote_urls: bool
    output_persistence: bool
    reason: str | None = None


class ConsentVerifier(Protocol):
    """Verify the consent record server-side; never trust request booleans alone."""

    def verify(self, subject_id: str, twin_id: str, consent: ConsentInput) -> bool:
        ...


class AssetAuthorizer(Protocol):
    """Verify ownership and access to both private assets and their parent records."""

    def authorize(
        self,
        subject_id: str,
        twin_id: str,
        product_id: str,
        person_image_asset_id: str,
        garment_image_asset_id: str,
    ) -> bool:
        ...


class Renderer(Protocol):
    """Provider boundary; real implementation must resolve assets securely."""

    renderer_id: str
    renderer_version: str

    def render(self, request: TryOnRequest) -> str:
        """Return an opaque output asset ID after storing a validated result."""
        ...


class IdentityConsentVerifier:
    """Live identity-service adapter; consent is checked for the exact Twin resource."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def verify(self, subject_id: str, twin_id: str, consent: ConsentInput) -> bool:
        try:
            with httpx.Client(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    self.base_url + "/internal/v1/consents/verify",
                    headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"},
                    json={
                        "subject_id": subject_id,
                        "consent_id": consent.consent_id,
                        "required_scopes": ["image_processing", "virtual_try_on", "asset_reuse"],
                        "resource_id": twin_id,
                    },
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError("consent verification timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("consent verification unavailable") from exc
        if response.status_code in {401, 403, 404}:
            return False
        if response.status_code != 200:
            raise RuntimeError("consent verification unavailable")
        try:
            receipt = response.json()
        except ValueError as exc:
            raise RuntimeError("consent verifier returned invalid JSON") from exc
        scopes = receipt.get("granted_scopes") if isinstance(receipt, dict) else None
        return bool(
            isinstance(receipt, dict)
            and receipt.get("verified") is True
            and receipt.get("active") is True
            and receipt.get("subject_id") == subject_id
            and receipt.get("consent_id") == consent.consent_id
            and receipt.get("resource_id") == twin_id
            and isinstance(scopes, list)
            and {"image_processing", "virtual_try_on", "asset_reuse"}.issubset(set(scopes))
        )


class TwinRegistryAssetAuthorizer:
    """Live registry adapter for subject/Twin/person/garment ownership checks."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def authorize(
        self,
        subject_id: str,
        twin_id: str,
        product_id: str,
        person_image_asset_id: str,
        garment_image_asset_id: str,
    ) -> bool:
        try:
            with httpx.Client(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    self.base_url + "/internal/v1/assets/authorize",
                    headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"},
                    json={
                        "subject_id": subject_id,
                        "twin_id": twin_id,
                        "product_id": product_id,
                        "person_image_asset_id": person_image_asset_id,
                        "garment_image_asset_id": garment_image_asset_id,
                    },
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError("asset authorization timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("asset authorization unavailable") from exc
        if response.status_code in {401, 403, 404}:
            return False
        if response.status_code != 200:
            raise RuntimeError("asset authorization unavailable")
        try:
            receipt = response.json()
        except ValueError as exc:
            raise RuntimeError("asset authorizer returned invalid JSON") from exc
        return bool(
            isinstance(receipt, dict)
            and receipt.get("authorized") is True
            and receipt.get("active") is True
            and receipt.get("subject_id") == subject_id
            and receipt.get("twin_id") == twin_id
            and receipt.get("product_id") == product_id
            and receipt.get("person_image_asset_id") == person_image_asset_id
            and receipt.get("garment_image_asset_id") == garment_image_asset_id
        )


def _trusted_internal_config(url_key: str, token_key: str) -> tuple[str, str] | None:
    raw = os.getenv(url_key, "").strip().rstrip("/")
    token = os.getenv(token_key, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        return None
    return raw, token


def _configured_consent_verifier() -> ConsentVerifier | None:
    config = _trusted_internal_config("CONSENT_API_URL", "CONSENT_API_TOKEN")
    return IdentityConsentVerifier(*config) if config else None


def _configured_asset_authorizer() -> AssetAuthorizer | None:
    config = _trusted_internal_config("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN")
    return TwinRegistryAssetAuthorizer(*config) if config else None


# Only real remote identity/registry adapters are configured from trusted service URLs.
# The renderer remains disabled until a secure object-store adapter and GPU model are deployed.
# and independent integration tests exist. Environment flags cannot enable them.
CONSENT_VERIFIER: ConsentVerifier | None = _configured_consent_verifier()
ASSET_AUTHORIZER: AssetAuthorizer | None = _configured_asset_authorizer()
RENDERER: Renderer | None = None

app = FastAPI(
    title="Cirvanna Virtual Try-On API",
    version=API_VERSION,
    description=(
        "Consent-gated try-on orchestration contract. Rendering stays disabled "
        "until a real renderer and secure asset adapter are validated."
    ),
)


def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("VIRTUAL_TRY_ON_API_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AUTH_NOT_CONFIGURED", "message": "Try-on API is not accepting traffic until authentication is configured."},
        )
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/ready", tags=["operations"])
def ready() -> dict[str, object]:
    ready_now = (
        RENDERER is not None
        and CONSENT_VERIFIER is not None
        and ASSET_AUTHORIZER is not None
        and bool(os.getenv("VIRTUAL_TRY_ON_API_TOKEN"))
    )
    if not ready_now:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "renderer_configured": RENDERER is not None,
                "consent_verifier_configured": CONSENT_VERIFIER is not None,
                "asset_authorizer_configured": ASSET_AUTHORIZER is not None,
                "reason": "validated_renderer_consent_and_asset_authorization_adapters_not_integrated",
            },
        )
    return {
        "status": "ready",
        "service": SERVICE_NAME,
        "renderer_configured": True,
        "consent_verifier_configured": True,
        "asset_authorizer_configured": True,
    }


@app.get("/capabilities", response_model=CapabilityResponse, tags=["operations"])
def capabilities() -> CapabilityResponse:
    configured = RENDERER is not None
    return CapabilityResponse(
        service=SERVICE_NAME,
        api_version=API_VERSION,
        orchestration_api=True,
        renderer_configured=configured,
        consent_verifier_configured=CONSENT_VERIFIER is not None,
        asset_authorizer_configured=ASSET_AUTHORIZER is not None,
        supported_categories=["upper_body", "lower_body", "dress", "outerwear", "full_outfit"],
        raw_image_upload=False,
        arbitrary_remote_urls=False,
        output_persistence=False,
        reason=None if configured else "validated_renderer_and_secure_asset_adapter_not_integrated",
    )


@app.post(
    "/v1/try-ons",
    response_model=TryOnResult,
    status_code=status.HTTP_200_OK,
    tags=["try-on"],
)
def create_try_on(
    payload: TryOnRequest,
    _: Annotated[None, Depends(require_api_token)],
) -> TryOnResult:
    """Request a render only when explicit consent and a real renderer exist."""
    if not payload.consent.image_processing or not payload.consent.virtual_try_on:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CONSENT_REQUIRED", "message": "Explicit image-processing and virtual-try-on consent are both required."},
        )
    if payload.consent.retention_policy != "ephemeral":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "RETENTION_POLICY_UNSUPPORTED", "message": "Only ephemeral processing is currently supported."},
        )
    consent_verifier = CONSENT_VERIFIER
    asset_authorizer = ASSET_AUTHORIZER
    renderer = RENDERER
    if consent_verifier is None or asset_authorizer is None or renderer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "TRY_ON_DEPENDENCIES_NOT_CONFIGURED",
                "message": "Validated consent, asset authorization, and rendering integrations are required. No image was processed and no output was created.",
            },
        )
    try:
        consent_is_valid = consent_verifier.verify(payload.subject_id, payload.twin_id, payload.consent)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CONSENT_VERIFICATION_UNAVAILABLE", "message": "Consent could not be verified; rendering was not started."},
        ) from exc
    if not consent_is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CONSENT_NOT_VERIFIED", "message": "No matching active server-side consent record was verified."},
        )
    try:
        assets_are_authorized = asset_authorizer.authorize(
            payload.subject_id,
            payload.twin_id,
            payload.product_id,
            payload.person_image_asset_id,
            payload.garment_image_asset_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ASSET_AUTHORIZATION_UNAVAILABLE", "message": "Asset access could not be verified; rendering was not started."},
        ) from exc
    if not assets_are_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ASSET_ACCESS_DENIED", "message": "The subject is not authorized to use one or more referenced assets."},
        )
    try:
        output_asset_id = renderer.render(payload)
    except Exception as exc:
        # Do not expose provider internals, request data, or upstream response bodies.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "RENDERER_FAILED", "message": "Rendering failed; no successful output can be claimed."},
        ) from exc
    if not isinstance(output_asset_id, str) or not ASSET_ID_PATTERN.fullmatch(output_asset_id):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "RENDERER_INVALID_OUTPUT", "message": "Renderer returned an invalid output asset identifier."},
        )
    return TryOnResult(
        request_id=payload.request_id,
        status="complete",
        renderer_id=renderer.renderer_id,
        renderer_version=renderer.renderer_version,
        output_asset_id=output_asset_id,
        created_at=datetime.now(timezone.utc),
    )

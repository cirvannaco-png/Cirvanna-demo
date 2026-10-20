"""Guarded Virtual Twin API foundation.

This service deliberately refuses to claim that a twin was generated until a
real, configured reconstruction/model adapter is integrated and validated.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated
from urllib.parse import urlsplit

import httpx

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette import status

SERVICE_NAME = "cirvanna-virtual-twin"
# Flip only when a real adapter is implemented, configured, and covered by tests.
MODEL_ADAPTER_IMPLEMENTED = False
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 30 * 1024 * 1024

app = FastAPI(
    title="Cirvanna Virtual Twin API",
    version="0.1.0",
    description=(
        "Guarded API foundation. Reconstruction and skin-analysis inference "
        "remain unavailable until validated model adapters are integrated."
    ),
)
bearer = HTTPBearer(auto_error=False)


class TwinResponse(BaseModel):
    status: str
    code: str
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    service: str
    model_adapter_configured: bool
    ready: bool


def require_api_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer)
    ],
) -> None:
    expected = os.getenv("VIRTUAL_TWIN_API_TOKEN", "")
    if not expected or credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Liveness only; does not imply model or dependency readiness."""
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/ready", response_model=ReadinessResponse, tags=["operations"])
def ready() -> ReadinessResponse:
    configured = MODEL_ADAPTER_IMPLEMENTED
    is_ready = configured and bool(os.getenv("VIRTUAL_TWIN_API_TOKEN"))
    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "model_adapter_configured": configured,
                "reason": "validated_model_adapter_not_integrated",
            },
        )
    return ReadinessResponse(
        status="ready",
        service=SERVICE_NAME,
        model_adapter_configured=True,
        ready=True,
    )


async def _dermalsight_config() -> tuple[str, str] | None:
    """Resolve the explicitly configured internal service and bearer token."""
    base_url = os.getenv("DERMALSIGHT_API_URL", "").strip().rstrip("/")
    token = os.getenv("DERMALSIGHT_API_TOKEN", "").strip()
    if not base_url or not token:
        return None
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    return base_url, token


async def _dermalsight_ready() -> bool:
    config = await _dermalsight_config()
    if config is None:
        return False
    base_url, _token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(2.0, connect=1.0), follow_redirects=False, trust_env=False
        ) as client:
            response = await client.get(base_url + "/ready")
        return response.status_code == 200 and response.json().get("ready") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


@app.get("/capabilities", tags=["operations"])
async def capabilities() -> dict[str, object]:
    """Report only verified implementation state, not roadmap promises."""
    dermalsight_ready = await _dermalsight_ready()
    return {
        "service": SERVICE_NAME,
        "twin_generation": False,
        "body_reconstruction": False,
        "skin_analysis": dermalsight_ready,
        "dermalsight_ready": dermalsight_ready,
        "skin_analysis_reason": None if dermalsight_ready else "dermalsight_not_ready_or_not_configured",
        "fit_prediction": False,
        "ar_rendering": False,
        "click_it_product_reconstruction": False,
        "decision_governance_connected_to_rendering": False,
        "reason": "validated_model_and_rendering_adapters_not_integrated",
    }


@app.post(
    "/skin-analysis",
    tags=["skin-analysis"],
)
async def proxy_skin_analysis(
    _: Annotated[None, Depends(require_api_token)],
    consent: Annotated[bool, Form(description="Explicitly consent to in-memory skin analysis.")],
    image: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image; not persisted by Virtual Twin.")],
):
    """Forward consented image analysis to the separately deployed DermalSight service."""
    if not consent:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EXPLICIT_CONSENT_REQUIRED"},
        )
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "UNSUPPORTED_IMAGE_TYPE"},
        )

    config = await _dermalsight_config()
    if config is None:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DERMALSIGHT_NOT_CONFIGURED"},
        )

    base_url, service_token = config
    try:
        content = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await image.close()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES},
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_IMAGE"},
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=2.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            upstream = await client.post(
                base_url + "/api/v1/analyze",
                headers={"Authorization": "Bearer " + service_token},
                data={"consent": "true"},
                files={"image": (image.filename or "capture", content, image.content_type)},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "DERMALSIGHT_TIMEOUT"},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DERMALSIGHT_UNAVAILABLE"},
        ) from exc

    if upstream.status_code == 200:
        try:
            payload = upstream.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "DERMALSIGHT_INVALID_RESPONSE"},
            ) from exc
        return JSONResponse(status_code=200, content=payload, headers={"Cache-Control": "no-store"})

    # Only forward known client-side validation statuses and opaque error codes.
    if upstream.status_code in {400, 413, 415}:
        try:
            detail = upstream.json().get("detail", {})
            code = detail.get("code", "DERMALSIGHT_REQUEST_REJECTED") if isinstance(detail, dict) else "DERMALSIGHT_REQUEST_REJECTED"
        except ValueError:
            code = "DERMALSIGHT_REQUEST_REJECTED"
        raise HTTPException(
            status_code=upstream.status_code,
            detail={"code": code},
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "DERMALSIGHT_UNAVAILABLE"},
    )


@app.post(
    "/twin",
    response_model=TwinResponse,
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    tags=["twin"],
)
async def create_twin(
    _: Annotated[None, Depends(require_api_token)],
    height_cm: Annotated[float, Form(gt=0, le=260)],
    weight_kg: Annotated[float | None, Form(gt=0, le=500)] = None,
    images: Annotated[list[UploadFile], File()] = [],
    video: Annotated[UploadFile | None, File()] = None,
) -> TwinResponse:
    """Fail closed until validated reconstruction is actually available.

    Upload processing is intentionally not started while the model adapter is
    absent. This prevents unnecessary handling of sensitive body imagery.
    """
    del height_cm, weight_kg
    try:
        if len(images) > MAX_IMAGES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": "TOO_MANY_IMAGES", "maximum": MAX_IMAGES},
            )
        if any(image.size is None or image.size > MAX_IMAGE_BYTES for image in images):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES},
            )
        if video is not None and (video.size is None or video.size > MAX_VIDEO_BYTES):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": "VIDEO_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_VIDEO_BYTES},
            )
    finally:
        # Starlette may spool multipart uploads to temporary files before this
        # endpoint runs. Close every upload promptly; no image is processed.
        for image in images:
            await image.close()
        if video is not None:
            await video.close()

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "unavailable",
            "code": "MODEL_ADAPTER_NOT_CONFIGURED",
            "detail": (
                "Twin generation is disabled until a real reconstruction "
                "adapter, validated assets, and integration tests are supplied."
            ),
        },
    )



@app.post(
    "/click-it",
    response_model=TwinResponse,
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    tags=["click-it"],
)
async def click_it(
    _: Annotated[None, Depends(require_api_token)],
    twin_id: Annotated[str, Form(min_length=1, max_length=128)],
    product_image: Annotated[UploadFile, File()],
) -> TwinResponse:
    """Guarded Click It contract: photo-to-twin rendering is not yet available.

    Until reconstruction and decision-governance adapters are integrated, the
    service validates only request metadata and closes the upload; it neither
    decodes, stores nor forwards the product image.
    """
    try:
        if not twin_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "TWIN_ID_REQUIRED"},
            )
        if product_image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={"code": "UNSUPPORTED_PRODUCT_IMAGE_TYPE"},
            )
        if product_image.size is None or product_image.size > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES},
            )
    finally:
        await product_image.close()

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "unavailable",
            "code": "CLICK_IT_PIPELINE_NOT_CONFIGURED",
            "detail": (
                "Click It is not connected to a validated product reconstruction adapter "
                "and CAL decision-governance service; the uploaded image was not processed."
            ),
        },
    )

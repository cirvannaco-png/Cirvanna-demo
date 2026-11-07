"""Consent-gated Virtual Twin pose inference and Click It marketplace search.

The present model output is a pose skeleton, not a persistent avatar mesh or a
calibrated body model. Click It returns marketplace candidates pending CAL.
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
# Adapter code is implemented; availability remains gated on a real worker, consent
# verifier and (for Click It) a user-scoped Twin registry integration.
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_SKIN_ANALYSIS_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 30 * 1024 * 1024

app = FastAPI(
    title="Cirvanna Virtual Twin API",
    version="0.1.0",
    description=(
        "Pose-skeleton inference and Click It candidate retrieval use a private, "
        "model-backed vision adapter; full-body reconstruction, calibrated fit "
        "measurements and skin analysis remain separately gated."
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
    consent_verifier_configured: bool
    twin_registry_configured: bool
    ready: bool
    reason: str | None = None


def require_api_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer)
    ],
) -> None:
    expected = os.getenv("VIRTUAL_TWIN_API_TOKEN", "")
    if len(expected.encode("utf-8")) < 32 or credentials is None:
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
async def ready() -> ReadinessResponse:
    vision_ready = await _vision_worker_ready()
    consent_configured = _internal_config("CONSENT_API_URL", "CONSENT_API_TOKEN") is not None
    twin_registry_configured = _internal_config("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN") is not None
    api_token_configured = len(os.getenv("VIRTUAL_TWIN_API_TOKEN", "").encode("utf-8")) >= 32
    ready_now = vision_ready and consent_configured and api_token_configured
    reason = None
    if not api_token_configured:
        reason = "api_auth_not_configured"
    elif not vision_ready:
        reason = "vision_worker_not_ready"
    elif not consent_configured:
        reason = "consent_verifier_not_configured"
    result = ReadinessResponse(
        status="ready" if ready_now else "not_ready",
        service=SERVICE_NAME,
        model_adapter_configured=vision_ready,
        consent_verifier_configured=consent_configured,
        twin_registry_configured=twin_registry_configured,
        ready=ready_now,
        reason=reason,
    )
    if not ready_now:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.model_dump())
    return result


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


def _internal_config(url_name: str, token_name: str) -> tuple[str, str] | None:
    raw = os.getenv(url_name, "").strip().rstrip("/")
    token = os.getenv(token_name, "").strip()
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


async def _verify_consent(
    subject_id: str,
    consent_id: str,
    required_scopes: list[str],
    resource_id: str | None = None,
) -> None:
    """Verify durable, revocable user consent with the configured identity service."""
    config = _internal_config("CONSENT_API_URL", "CONSENT_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_NOT_CONFIGURED"})
    base, token = config
    request_body: dict[str, object] = {
        "subject_id": subject_id,
        "consent_id": consent_id,
        "required_scopes": required_scopes,
    }
    if resource_id is not None:
        request_body["resource_id"] = resource_id
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/consents/verify",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "CONSENT_VERIFICATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "CONSENT_VERIFIER_INVALID_RESPONSE"}) from exc
    scopes = receipt.get("granted_scopes") if isinstance(receipt, dict) else None
    valid = (
        isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("consent_id") == consent_id
        and isinstance(scopes, list)
        and set(required_scopes).issubset(set(scopes))
        and (resource_id is None or receipt.get("resource_id") == resource_id)
    )
    if not valid:
        raise HTTPException(403, detail={"code": "CONSENT_NOT_VERIFIED"})


async def _authorize_twin(subject_id: str, twin_id: str) -> None:
    """Prevent Click It from resolving a Twin belonging to a different account."""
    config = _internal_config("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN")
    if config is None:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_NOT_CONFIGURED"})
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/internal/v1/twins/authorize",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json={"subject_id": subject_id, "twin_id": twin_id},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TWIN_AUTHORIZATION_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403, 404}:
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_UNAVAILABLE"})
    try:
        receipt = response.json()
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "TWIN_REGISTRY_INVALID_RESPONSE"}) from exc
    if not (
        isinstance(receipt, dict)
        and receipt.get("authorized") is True
        and receipt.get("active") is True
        and receipt.get("subject_id") == subject_id
        and receipt.get("twin_id") == twin_id
    ):
        raise HTTPException(403, detail={"code": "TWIN_ACCESS_DENIED"})


async def _vision_config() -> tuple[str, str] | None:
    return _internal_config("VISION_INTELLIGENCE_API_URL", "VISION_INTELLIGENCE_API_TOKEN")


async def _vision_worker_ready() -> bool:
    config = await _vision_config()
    if config is None:
        return False
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(2.5, connect=1.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.get(
                base + "/ready", headers={"Authorization": "Bearer " + token, "Accept": "application/json"}
            )
        return response.status_code == 200 and response.json().get("ready") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


async def _run_vision(
    endpoint: str,
    fields: dict[str, str],
    upload_field: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict[str, object]:
    config = await _vision_config()
    if config is None:
        raise HTTPException(503, detail={"code": "VISION_INFERENCE_NOT_CONFIGURED"})
    base, token = config
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=2.0), trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + endpoint,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                data=fields,
                files={upload_field: (filename, content, content_type)},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "VISION_INFERENCE_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "VISION_WORKER_UNAVAILABLE"}) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "VISION_WORKER_INVALID_RESPONSE"}) from exc
    if response.status_code == 200 and isinstance(payload, dict):
        return payload
    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    upstream_code = detail.get("code") if isinstance(detail, dict) else None
    safe_detail: dict[str, object] = {
        "code": upstream_code if isinstance(upstream_code, str) else "VISION_REQUEST_FAILED"
    }
    if isinstance(detail, dict):
        for key in ("quality", "message", "maximum_bytes", "visibility"):
            if key in detail:
                safe_detail[key] = detail[key]
    if response.status_code in {400, 403, 413, 415, 422}:
        raise HTTPException(response.status_code, detail=safe_detail)
    if response.status_code == 504:
        raise HTTPException(504, detail={"code": "VISION_INFERENCE_TIMEOUT"})
    if response.status_code in {502, 503}:
        raise HTTPException(503 if response.status_code == 503 else 502, detail={
            "code": "VISION_MODEL_UNAVAILABLE" if response.status_code == 503 else "VISION_INFERENCE_FAILED"
        })
    raise HTTPException(502, detail={"code": "VISION_INFERENCE_FAILED"})


@app.get("/capabilities", tags=["operations"])
async def capabilities() -> dict[str, object]:
    """Report verified model/service state and deliberately separate partial inference."""
    dermalsight_ready = await _dermalsight_ready()
    vision_ready = await _vision_worker_ready()
    consent_configured = _internal_config("CONSENT_API_URL", "CONSENT_API_TOKEN") is not None
    twin_registry_configured = _internal_config("TWIN_REGISTRY_API_URL", "TWIN_REGISTRY_API_TOKEN") is not None
    return {
        "service": SERVICE_NAME,
        "twin_generation": False,
        "persistent_twin_generation": False,
        "persistent_twin_preview": False,
        "pose_skeleton_inference": vision_ready and consent_configured,
        "body_reconstruction": False,
        "full_surface_mesh": False,
        "calibrated_body_measurements": False,
        "skin_analysis": dermalsight_ready,
        "dermalsight_ready": dermalsight_ready,
        "skin_analysis_reason": None if dermalsight_ready else "dermalsight_not_ready_or_not_configured",
        "fit_prediction": False,
        "ar_rendering": False,
        "click_it_product_reconstruction": False,
        "click_it_marketplace_search": vision_ready and consent_configured,
        "click_it_twin_personalization": vision_ready and consent_configured and twin_registry_configured,
        "decision_governance_connected_to_rendering": False,
        "image_persistence": False,
        "display_authorization": "CAL_required_before_candidates_are_shown_or_used_to_purchase",
        "reason": None if vision_ready else "vision_worker_not_ready_or_not_configured",
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
        content = await image.read(MAX_SKIN_ANALYSIS_IMAGE_BYTES + 1)
    finally:
        await image.close()
    if len(content) > MAX_SKIN_ANALYSIS_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_SKIN_ANALYSIS_IMAGE_BYTES},
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
    tags=["twin"],
)
async def create_twin(
    _: Annotated[None, Depends(require_api_token)],
    subject_id: Annotated[str, Form(min_length=3, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=160)],
    consent_image_processing: Annotated[bool, Form()],
    consent_body_measurements: Annotated[bool, Form()],
    height_cm: Annotated[float, Form(gt=80, le=260)],
    weight_kg: Annotated[float | None, Form(gt=0, le=500)] = None,
    images: Annotated[list[UploadFile], File()] = [],
    video: Annotated[UploadFile | None, File()] = None,
):
    """Run a consent-verified pose inference and return an ephemeral skeleton.

    This deliberately does not claim body-surface reconstruction, calibrated
    measurements, or a persisted Virtual Twin record.
    """
    del weight_kg
    try:
        if not consent_image_processing or not consent_body_measurements:
            raise HTTPException(400, detail={"code": "EXPLICIT_TWIN_CONSENT_REQUIRED"})
        if len(images) > MAX_IMAGES:
            raise HTTPException(413, detail={"code": "TOO_MANY_IMAGES", "maximum": MAX_IMAGES})
        if video is not None and (video.size is None or video.size > MAX_VIDEO_BYTES):
            raise HTTPException(413, detail={"code": "VIDEO_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_VIDEO_BYTES})
        if video is not None:
            raise HTTPException(422, detail={"code": "VIDEO_INFERENCE_NOT_SUPPORTED", "message": "The current model adapter accepts one still image."})
        if not images:
            raise HTTPException(422, detail={"code": "INPUT_IMAGE_REQUIRED"})
        if len(images) != 1:
            raise HTTPException(422, detail={"code": "SINGLE_IMAGE_REQUIRED", "message": "The current pose model accepts one full-body image per request."})
        uploaded = images[0]
        if uploaded.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_TYPE"})
        if uploaded.size is not None and uploaded.size > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
        # Check configuration before contacting a consent provider, but never send
        # uploaded bytes to the inference worker until durable consent is verified.
        if _internal_config("VISION_INTELLIGENCE_API_URL", "VISION_INTELLIGENCE_API_TOKEN") is None:
            raise HTTPException(503, detail={"code": "VISION_INFERENCE_NOT_CONFIGURED"})
        await _verify_consent(subject_id, consent_id, ["image_processing", "body_measurements"])
        content = await uploaded.read(MAX_IMAGE_BYTES + 1)
        if not content:
            raise HTTPException(400, detail={"code": "EMPTY_IMAGE"})
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
        result = await _run_vision(
            "/v1/twin/infer",
            {
                "consent_image_processing": "true",
                "consent_body_measurements": "true",
                "height_cm": str(height_cm),
            },
            "image",
            uploaded.filename or "capture",
            content,
            uploaded.content_type or "application/octet-stream",
        )
        result["record_persisted"] = False
        result["full_surface_mesh_available"] = False
        result["calibrated_body_measurements_available"] = False
        result["decision_status"] = "REVIEW_REQUIRED"
        result["decision_notice"] = "Pose landmarks are not fit evidence; CAL/FCI must independently evaluate any downstream product decision."
        return JSONResponse(content=result, headers={"Cache-Control": "no-store, private"})
    finally:
        for image in images:
            await image.close()
        if video is not None:
            await video.close()


@app.post(
    "/click-it",
    tags=["click-it"],
)
async def click_it(
    _: Annotated[None, Depends(require_api_token)],
    subject_id: Annotated[str, Form(min_length=3, max_length=128)],
    consent_id: Annotated[str, Form(min_length=8, max_length=160)],
    consent_image_processing: Annotated[bool, Form()],
    consent_click_it: Annotated[bool, Form()],
    product_image: Annotated[UploadFile, File()],
    twin_id: Annotated[str | None, Form(min_length=3, max_length=128)] = None,
    category: Annotated[str | None, Form(max_length=80)] = None,
    limit: Annotated[int, Form(ge=1, le=25)] = 10,
):
    """Scan an uploaded product photo, retrieve live marketplace candidates, and stop.

    Candidate ranking is not CAL authorization. Results cannot be displayed,
    personalized, or purchased until downstream arbitration permits them.
    """
    try:
        if not consent_image_processing or not consent_click_it:
            raise HTTPException(400, detail={"code": "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"})
        if product_image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, detail={"code": "UNSUPPORTED_PRODUCT_IMAGE_TYPE"})
        if product_image.size is not None and product_image.size > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
        if _internal_config("VISION_INTELLIGENCE_API_URL", "VISION_INTELLIGENCE_API_TOKEN") is None:
            raise HTTPException(503, detail={"code": "VISION_INFERENCE_NOT_CONFIGURED"})
        await _verify_consent(
            subject_id, consent_id, ["image_processing", "click_it"], resource_id=twin_id
        )
        if twin_id:
            await _authorize_twin(subject_id, twin_id)
        content = await product_image.read(MAX_IMAGE_BYTES + 1)
        if not content:
            raise HTTPException(400, detail={"code": "EMPTY_PRODUCT_IMAGE"})
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, detail={"code": "PRODUCT_IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
        fields = {
            "consent_image_processing": "true",
            "consent_click_it": "true",
            "limit": str(limit),
        }
        if category and category.strip():
            fields["category"] = category.strip()
        result = await _run_vision(
            "/v1/click-it/scan",
            fields,
            "image",
            product_image.filename or "product-reference",
            content,
            product_image.content_type or "application/octet-stream",
        )
        # Keep candidates separate from policy-authorized display items. In
        # particular, this endpoint does not bypass NPL or cultural requirements.
        candidates = result.pop("results", [])
        result["candidates"] = candidates
        result["display_authorized"] = False
        result["decision_status"] = "PENDING_CAL"
        result["decision_notice"] = "Candidates require the canonical CAL decision, NPL hard veto and cultural-identity checks before display or purchase."
        result["twin_id"] = twin_id
        result["personalization_available"] = bool(twin_id)
        return JSONResponse(content=result, headers={"Cache-Control": "no-store, private"})
    finally:
        await product_image.close()


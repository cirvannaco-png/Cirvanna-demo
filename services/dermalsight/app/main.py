"""DermalSight API with explicit consent and fail-closed model readiness."""
from __future__ import annotations

import hmac
import io
import os
from functools import lru_cache
from typing import Annotated, Any

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel
from starlette import status

from .dsi.api import router as dsi_analysis_router
from .dsi.capture import CapturePlanRequest, build_capture_plan
from .dsi.media import read_and_decode_image
from .dsi.router import router as dsi_router
from .model_adapter import ModelConfigurationError, SkinAnalysisEngine
from .validation import verify_signed_validation_report

SERVICE_NAME = "cirvanna-dermalsight"
SERVICE_VERSION = "0.2.0"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}

app = FastAPI(
    title="Cirvanna DermalSight API",
    version=SERVICE_VERSION,
    description=(
        "Non-diagnostic cosmetic skin-attribute inference and the governed DSI "
        "contract surface. DSI inference remains disabled until task-specific "
        "models, validation evidence and authorization controls pass."
    ),
)
app.include_router(dsi_router)
app.include_router(dsi_analysis_router)
bearer = HTTPBearer(auto_error=False)


class ReadinessResponse(BaseModel):
    status: str
    service: str
    model_adapter_configured: bool
    ready: bool


class AnalysisResponse(BaseModel):
    status: str
    service: str
    contract_version: str
    model_version: str
    score_semantics: str
    attributes: list[dict[str, Any]]
    disclaimer: str


@lru_cache(maxsize=4)
def _load_model(model_path: str, manifest_path: str) -> SkinAnalysisEngine:
    return SkinAnalysisEngine(model_path, manifest_path)


def get_model_adapter() -> SkinAnalysisEngine | None:
    model_path = os.getenv("DERMALSIGHT_MODEL_PATH", "").strip()
    manifest_path = os.getenv("DERMALSIGHT_MODEL_MANIFEST_PATH", "").strip()
    report_path = os.getenv("DERMALSIGHT_VALIDATION_REPORT_PATH", "").strip()
    signing_key = os.getenv("DERMALSIGHT_VALIDATION_SIGNING_KEY", "")
    if not model_path or not manifest_path:
        return None
    if not report_path or not signing_key:
        raise ModelConfigurationError("Signed validation report or signing key is not configured.")
    adapter = _load_model(model_path, manifest_path)
    verify_signed_validation_report(
        report_path,
        signing_key,
        model_sha256=adapter.model_sha256,
        model_version=adapter.model_version,
    )
    return adapter


def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("DERMALSIGHT_API_TOKEN", "")
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


@app.middleware("http")
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.post(
    "/api/v1/dsi/capture-plan",
    tags=["dsi", "capture"],
    dependencies=[Depends(require_api_token)],
)
def create_dsi_capture_plan(request: CapturePlanRequest) -> dict[str, object]:
    """Return capture guidance only; this route never accepts or processes media."""
    return build_capture_plan(request).model_dump(mode="json")


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Liveness only. It does not imply that inference is available."""
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/ready", response_model=ReadinessResponse, tags=["operations"])
def ready() -> ReadinessResponse:
    if not os.getenv("DERMALSIGHT_API_TOKEN", "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "model_adapter_configured": False,
                "reason": "api_token_not_configured",
            },
        )
    try:
        adapter = get_model_adapter()
    except ModelConfigurationError:
        adapter = None
        reason = "model_artifact_or_manifest_invalid"
    else:
        reason = "model_assets_not_configured"
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "model_adapter_configured": False,
                "reason": reason,
            },
        )
    return ReadinessResponse(
        status="ready", service=SERVICE_NAME, model_adapter_configured=True, ready=True
    )


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    """Report actual contract limits, not planned or clinically unvalidated features."""
    try:
        adapter = get_model_adapter()
        adapter_configured = adapter is not None
    except ModelConfigurationError:
        adapter_configured = False
    return {
        "service": SERVICE_NAME,
        "contract_version": "1",
        "inference_enabled": adapter_configured,
        "model_type": "hash_verified_onnx_cpu",
        "signed_validation_report_required": True,
        "explicit_consent_required": True,
        "authentication_required": True,
        "image_persistence": False,
        "clinical_diagnosis": False,
        "recommendations": False,
        "longitudinal_forecasting": False,
        "forecast_status": "unavailable_until_validated_longitudinal_model_and_dataset_exist",
        "reason": None if adapter_configured else "validated_model_artifact_not_configured",
    }


async def _read_and_decode_image(upload: UploadFile) -> np.ndarray:
    """Compatibility wrapper around the shared in-memory DSI upload decoder."""
    return await read_and_decode_image(
        upload,
        max_bytes=MAX_IMAGE_BYTES,
        max_pixels=MAX_IMAGE_PIXELS,
        allowed_mime_types=ALLOWED_MIME_TYPES,
        mime_to_format=MIME_TO_FORMAT,
    )


@app.post(
    "/api/v1/analyze",
    response_model=AnalysisResponse,
    tags=["analysis"],
    dependencies=[Depends(require_api_token)],
)
async def analyze_skin(
    consent: Annotated[bool, Form(description="Must be true to consent to in-memory image analysis.")],
    image: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image; never persisted by the service.")],
) -> AnalysisResponse:
    """Analyze a user-provided image in memory only; requires a verified model."""
    if not consent:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EXPLICIT_CONSENT_REQUIRED"},
        )

    try:
        adapter = get_model_adapter()
    except ModelConfigurationError as exc:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MODEL_CONFIGURATION_INVALID", "detail": "Validated inference is unavailable."},
        ) from exc
    if adapter is None:
        await image.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "MODEL_NOT_CONFIGURED",
                "detail": "No verified ONNX model is configured; heuristic fallback is disabled.",
            },
        )

    rgb_image = await _read_and_decode_image(image)
    try:
        prediction = adapter.predict(rgb_image)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INFERENCE_FAILED", "detail": "Skin-attribute inference failed safely."},
        ) from exc

    return AnalysisResponse(
        status="completed",
        service=SERVICE_NAME,
        contract_version="1",
        model_version=prediction["model_version"],
        score_semantics=prediction["score_semantics"],
        attributes=prediction["attributes"],
        disclaimer=(
            "For cosmetic information only. Scores are not calibrated probabilities, "
            "not a medical diagnosis, and not validated clinical advice."
        ),
    )

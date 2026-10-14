"""Guarded Virtual Twin API foundation.

This service deliberately refuses to claim that a twin was generated until a
real, configured reconstruction/model adapter is integrated and validated.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
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


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    """Report only verified implementation state, not roadmap promises."""
    return {
        "service": SERVICE_NAME,
        "twin_generation": False,
        "body_reconstruction": False,
        "skin_analysis": False,
        "fit_prediction": False,
        "ar_rendering": False,
        "reason": "validated_model_and_rendering_adapters_not_integrated",
    }


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
    del height_cm, weight_kg, images, video
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

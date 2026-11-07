"""Private GPU inference worker for pinned FASHN VTON.

This service is internal-only. It never resolves URLs or persists input images.
The API/orchestrator remains responsible for consent, asset authorization and
persisting the validated output under a new opaque asset ID.
"""
from __future__ import annotations

import asyncio
import hmac
import io
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError

SERVICE = "cirvanna-vton-gpu-worker"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp"}
CATEGORY_MAP = {
    "upper_body": "tops",
    "outerwear": "tops",
    "lower_body": "bottoms",
    "dress": "one-pieces",
    "full_outfit": "one-pieces",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna Private VTON GPU Worker", version="0.1.0")
_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()


def _source_checkout_matches() -> bool:
    source_ref = os.getenv("FASHN_VTON_SOURCE_REF", "")
    source_dir = os.getenv("FASHN_VTON_SOURCE_DIR", "")
    if not SHA40.fullmatch(source_ref) or not source_dir or not Path(source_dir, ".git").exists():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", source_dir, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == source_ref


def _required_weights_present() -> bool:
    root = Path(os.getenv("FASHN_VTON_WEIGHTS_DIR", ""))
    required = (
        root / "model.safetensors",
        root / "dwpose" / "yolox_l.onnx",
        root / "dwpose" / "dw-ll_ucoco_384.onnx",
    )
    try:
        return root.is_dir() and all(path.is_file() and path.stat().st_size > 0 for path in required)
    except OSError:
        return False


def _configured() -> tuple[bool, str]:
    token = os.getenv("VTON_WORKER_TOKEN", "")
    if len(token.encode()) < 32:
        return False, "worker_token_not_configured"
    if not _source_checkout_matches():
        return False, "source_checkout_does_not_match_pin"
    if not _required_weights_present():
        return False, "required_model_weights_missing"
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "cuda_gpu_unavailable"
        if torch.cuda.get_device_properties(0).total_memory < 8 * 1024**3:
            return False, "gpu_vram_below_8_gib"
    except Exception:
        return False, "pytorch_cuda_runtime_unavailable"
    return True, "ready"


def require_worker_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("VTON_WORKER_TOKEN", "")
    if len(expected.encode()) < 32:
        raise HTTPException(503, detail={"code": "WORKER_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"}, headers={"WWW-Authenticate": "Bearer"})


def _pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        with _PIPELINE_LOCK:
            if _PIPELINE is None:
                # The constructor loads the TryOn model, DWPose and human parser.
                from fashn_vton import TryOnPipeline
                weights = os.environ["FASHN_VTON_WEIGHTS_DIR"]
                _PIPELINE = TryOnPipeline(weights_dir=weights, device="cuda")
    return _PIPELINE


def _decode_image(data: bytes, content_type: str) -> Image.Image:
    if content_type not in SUPPORTED_MIME:
        raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_TYPE"})
    if not data:
        raise HTTPException(400, detail={"code": "EMPTY_IMAGE"})
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": MAX_IMAGE_BYTES})
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_FORMAT"})
            if source.width < 64 or source.height < 64:
                raise HTTPException(422, detail={"code": "IMAGE_DIMENSIONS_TOO_SMALL"})
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(413, detail={"code": "IMAGE_PIXEL_LIMIT_EXCEEDED"})
            source.load()
            image = source.convert("RGB")
            image.info.clear()
            return image
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "INVALID_IMAGE_DATA"}) from exc


def _render(person: Image.Image, garment: Image.Image, category: str, garment_photo_type: str) -> bytes:
    try:
        result = _pipeline()(
            person_image=person,
            garment_image=garment,
            category=CATEGORY_MAP[category],
            garment_photo_type=garment_photo_type,
        )
        output = result.images[0]
        if not isinstance(output, Image.Image):
            raise ValueError("renderer did not return a PIL image")
        if output.width < 64 or output.height < 64 or output.width * output.height > MAX_IMAGE_PIXELS:
            raise ValueError("renderer output dimensions are invalid")
        stream = io.BytesIO()
        output.convert("RGB").save(stream, format="PNG", optimize=True)
        encoded = stream.getvalue()
        if not encoded or len(encoded) > MAX_IMAGE_BYTES:
            raise ValueError("renderer output size is invalid")
        # Re-decode bytes so the worker never returns malformed encoded output.
        with Image.open(io.BytesIO(encoded)) as check:
            check.verify()
        return encoded
    except Exception as exc:
        raise HTTPException(502, detail={"code": "INFERENCE_FAILED"}) from exc


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", tags=["operations"])
def ready() -> dict[str, object]:
    configured, reason = _configured()
    if not configured:
        raise HTTPException(503, detail={"status": "not_ready", "service": SERVICE, "ready": False, "reason": reason})
    try:
        _pipeline()
    except Exception:
        raise HTTPException(503, detail={"status": "not_ready", "service": SERVICE, "ready": False, "reason": "model_initialization_failed"})
    return {"status": "ready", "service": SERVICE, "ready": True, "model_loaded": True, "source_commit": os.environ["FASHN_VTON_SOURCE_REF"]}


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    return {
        "service": SERVICE,
        "supported_categories": sorted(CATEGORY_MAP),
        "input_persistence": False,
        "output_persistence": False,
        "remote_urls_accepted": False,
        "consent_enforced_by_worker": False,
        "requires_orchestrator_consent_gate": True,
        "model_source_pinned": _source_checkout_matches(),
        "required_weights_present": _required_weights_present(),
    }


@app.post("/v1/render", dependencies=[Depends(require_worker_auth)], tags=["inference"])
async def render(
    category: Annotated[Literal["upper_body", "outerwear", "lower_body", "dress", "full_outfit"], Form()],
    garment_photo_type: Annotated[Literal["model", "flat-lay"], Form()] = "flat-lay",
    person_image: Annotated[UploadFile, File()] = ...,
    garment_image: Annotated[UploadFile, File()] = ...,
) -> Response:
    # Consent is verified by the authenticated orchestration service before this
    # private worker is called. Client form booleans are not consent evidence.
    if category not in CATEGORY_MAP:
        await person_image.close()
        await garment_image.close()
        raise HTTPException(422, detail={"code": "UNSUPPORTED_CATEGORY"})
    try:
        person_bytes = await person_image.read(MAX_IMAGE_BYTES + 1)
        garment_bytes = await garment_image.read(MAX_IMAGE_BYTES + 1)
        person_type, garment_type = person_image.content_type or "", garment_image.content_type or ""
    finally:
        await person_image.close()
        await garment_image.close()
    person = _decode_image(person_bytes, person_type)
    garment = _decode_image(garment_bytes, garment_type)
    await asyncio.to_thread(_INFERENCE_LOCK.acquire)
    try:
        output = await asyncio.to_thread(_render, person, garment, category, garment_photo_type)
    finally:
        _INFERENCE_LOCK.release()
    return Response(
        content=output,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, private",
            "X-Cirvanna-Renderer": SERVICE,
            "X-Cirvanna-Model-Commit": os.getenv("FASHN_VTON_SOURCE_REF", "unconfigured"),
        },
    )

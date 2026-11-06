"""Private GPU inference worker for pinned FASHN VTON.

This service is internal-only. It never resolves URLs or persists input images.
The API/orchestrator remains responsible for consent, asset authorization and
persisting the validated output under a new opaque asset ID.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import re
from functools import lru_cache
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


def _weights_manifest_valid(weights_dir: Path) -> bool:
    """Verify every mounted weight file against the artifact's SHA256SUMS."""
    manifest = Path(os.getenv("FASHN_VTON_WEIGHTS_MANIFEST", str(weights_dir / "SHA256SUMS")))
    try:
        root = weights_dir.resolve(strict=True)
        manifest_path = manifest.resolve(strict=True)
        if not manifest_path.is_file() or not manifest_path.is_relative_to(root):
            return False
        entries = 0
        for raw in manifest_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                return False
            target = (root / parts[1].lstrip("*").strip()).resolve(strict=True)
            if not target.is_file() or not target.is_relative_to(root):
                return False
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if not hmac.compare_digest(actual, parts[0].lower()):
                return False
            entries += 1
        return entries > 0
    except (OSError, ValueError):
        return False


def _configured() -> tuple[bool, str]:
    token = os.getenv("VTON_WORKER_TOKEN", "")
    weights = os.getenv("FASHN_VTON_WEIGHTS_DIR", "")
    source_ref = os.getenv("FASHN_VTON_SOURCE_REF", "")
    if len(token.encode()) < 32:
        return False, "worker_token_not_configured"
    if not SHA40.fullmatch(source_ref):
        return False, "pinned_source_commit_required"
    if not weights or not Path(weights).is_dir():
        return False, "model_weights_directory_missing"
    if not _weights_manifest_valid(Path(weights)):
        return False, "model_weights_checksum_manifest_invalid"
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "cuda_gpu_unavailable"
    except Exception:
        return False, "pytorch_runtime_unavailable"
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
        # Heavy import is deferred so health and contract tests do not load model weights.
        from fashn_vton import TryOnPipeline
        weights = os.environ["FASHN_VTON_WEIGHTS_DIR"]
        _PIPELINE = TryOnPipeline(weights_dir=weights)
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


def _render(person: Image.Image, garment: Image.Image, category: str) -> bytes:
    try:
        result = _pipeline()(
            person_image=person,
            garment_image=garment,
            category=CATEGORY_MAP[category],
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
        # Readiness proves the actual pinned inference pipeline loads its weights.
        _pipeline()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "service": SERVICE, "ready": False, "reason": "model_initialization_failed"},
        ) from exc
    return {"status": "ready", "service": SERVICE, "ready": True, "source_commit": os.environ["FASHN_VTON_SOURCE_REF"]}


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, object]:
    return {
        "service": SERVICE,
        "supported_categories": sorted(CATEGORY_MAP),
        "input_persistence": False,
        "output_persistence": False,
        "remote_urls_accepted": False,
        "consent_enforced": True,
        "model_source_pinned": bool(SHA40.fullmatch(os.getenv("FASHN_VTON_SOURCE_REF", ""))),
    }


@app.post("/v1/render", dependencies=[Depends(require_worker_auth)], tags=["inference"])
async def render(
    consent_image_processing: Annotated[bool, Form()],
    consent_virtual_try_on: Annotated[bool, Form()],
    category: Annotated[Literal["upper_body", "outerwear", "lower_body", "dress", "full_outfit"], Form()],
    person_image: Annotated[UploadFile, File()],
    garment_image: Annotated[UploadFile, File()],
) -> Response:
    if not consent_image_processing or not consent_virtual_try_on:
        await person_image.close()
        await garment_image.close()
        raise HTTPException(403, detail={"code": "EXPLICIT_CONSENT_REQUIRED"})
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
    output = _render(person, garment, category)
    return Response(
        content=output,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, private",
            "X-Cirvanna-Renderer": SERVICE,
            "X-Cirvanna-Model-Commit": os.getenv("FASHN_VTON_SOURCE_REF", "unconfigured"),
        },
    )

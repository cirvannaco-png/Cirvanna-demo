"""Private GPU inference worker for pinned FASHN VTON.

This service is internal-only. It never resolves URLs or persists input images.
The API/orchestrator remains responsible for consent, asset authorization and
persisting the validated output under a new opaque asset ID.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
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
from starlette.concurrency import run_in_threadpool

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
PINNED_FASHN_VTON_COMMIT = "7c0f10af3f91ad4048fe9729c470a13ef905d25a"
MIN_GPU_VRAM_BYTES = 8 * 1024**3
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna Private VTON GPU Worker", version="0.1.0")
_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()
_INFERENCE_SLOT = threading.BoundedSemaphore(value=1)


REQUIRED_ARTIFACTS = (
    "model.safetensors",
    "dwpose/yolox_l.onnx",
    "dwpose/dw-ll_ucoco_384.onnx",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_artifact_manifest(weights_dir: Path, source_ref: str) -> tuple[bool, str]:
    """Require a source-bound SHA-256 manifest for every downloaded core weight."""
    manifest_path = weights_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "model_artifact_manifest_missing_or_invalid"
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return False, "model_artifact_manifest_invalid"
    if manifest.get("source_commit") != source_ref:
        return False, "model_artifact_source_mismatch"
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return False, "model_artifact_manifest_invalid"
    for relative in REQUIRED_ARTIFACTS:
        expected = artifacts.get(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            return False, "model_artifact_checksum_missing"
        target = (weights_dir / relative).resolve()
        if weights_dir.resolve() not in target.parents:
            return False, "model_artifact_path_invalid"
        if not target.is_file():
            return False, "model_artifact_missing"
        try:
            digest = _sha256_file(target)
        except OSError:
            return False, "model_artifact_unreadable"
        if not hmac.compare_digest(digest, expected):
            return False, "model_artifact_checksum_mismatch"
    return True, "verified"


def _source_checkout_matches() -> bool:
    """Verify the on-disk source checkout, not just an environment string."""
    source_ref = os.getenv("FASHN_VTON_SOURCE_REF", "")
    built_ref = os.getenv("FASHN_VTON_BUILT_SOURCE_REF", "")
    source_dir = os.getenv("FASHN_VTON_SOURCE_DIR", "")
    if source_ref != PINNED_FASHN_VTON_COMMIT or built_ref != PINNED_FASHN_VTON_COMMIT:
        return False
    root = Path(source_dir)
    if not source_dir or not (root / ".git").exists():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == PINNED_FASHN_VTON_COMMIT


def _configured() -> tuple[bool, str]:
    token = os.getenv("VTON_WORKER_TOKEN", "")
    weights = os.getenv("FASHN_VTON_WEIGHTS_DIR", "")
    usage_mode = os.getenv("CIRVANNA_DEPLOYMENT_MODE", "production").strip().lower()
    parser_license_approved = os.getenv(
        "FASHN_HUMAN_PARSER_COMMERCIAL_LICENSE_APPROVED", ""
    ).lower() == "true"
    if len(token.encode()) < 32:
        return False, "worker_token_not_configured"
    if os.getenv("FASHN_VTON_SOURCE_REF", "") != PINNED_FASHN_VTON_COMMIT:
        return False, "unexpected_or_unpinned_source_commit"
    if os.getenv("FASHN_VTON_BUILT_SOURCE_REF", "") != PINNED_FASHN_VTON_COMMIT:
        return False, "built_source_commit_mismatch"
    if not _source_checkout_matches():
        return False, "source_checkout_does_not_match_pin"
    if usage_mode not in {"research", "production"}:
        return False, "invalid_deployment_mode"
    if usage_mode == "production" and not parser_license_approved:
        return False, "human_parser_commercial_license_not_cleared"
    if not weights or not Path(weights).is_dir():
        return False, "model_weights_directory_missing"
    verified, reason = _verify_artifact_manifest(Path(weights), PINNED_FASHN_VTON_COMMIT)
    if not verified:
        return False, reason
    try:
        import torch
        import onnxruntime

        if not torch.cuda.is_available():
            return False, "cuda_gpu_unavailable"
        if torch.cuda.get_device_properties(0).total_memory < MIN_GPU_VRAM_BYTES:
            return False, "gpu_vram_below_8_gib"
        if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
            return False, "onnx_cuda_provider_unavailable"
    except Exception:
        return False, "gpu_runtime_unavailable"
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
                # Never trigger network downloads during runtime. Provision the
                # exact parser/model cache before the worker can become ready.
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
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


def _render(
    person: Image.Image, garment: Image.Image, category: str, garment_photo_type: str
) -> bytes:
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
        # Readiness must prove all model components load, not just that files exist.
        _pipeline()
    except Exception:
        raise HTTPException(503, detail={"status": "not_ready", "service": SERVICE, "ready": False, "reason": "model_load_failed"})
    return {"status": "ready", "service": SERVICE, "ready": True, "source_commit": os.environ["FASHN_VTON_SOURCE_REF"]}


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
        "required_weights_present": bool(
            os.getenv("FASHN_VTON_WEIGHTS_DIR")
            and _verify_artifact_manifest(
                Path(os.getenv("FASHN_VTON_WEIGHTS_DIR", "")),
                PINNED_FASHN_VTON_COMMIT,
            )[0]
        ),
        "artifact_manifest_required": True,
        "commercial_license_gate": os.getenv("FASHN_HUMAN_PARSER_COMMERCIAL_LICENSE_APPROVED", "").lower() == "true",
    }


@app.post("/v1/render", dependencies=[Depends(require_worker_auth)], tags=["inference"])
async def render(
    category: Annotated[
        Literal["upper_body", "outerwear", "lower_body", "dress", "full_outfit"], Form()
    ],
    person_image: Annotated[UploadFile, File()],
    garment_image: Annotated[UploadFile, File()],
    garment_photo_type: Annotated[Literal["model", "flat-lay"], Form()] = "flat-lay",
) -> Response:
    # Consent is verified by the authenticated orchestrator before this private
    # worker is called. Browser-supplied booleans are not consent evidence.
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
    if not _INFERENCE_SLOT.acquire(blocking=False):
        raise HTTPException(
            429,
            detail={"code": "GPU_WORKER_BUSY", "retryable": True},
            headers={"Retry-After": "2"},
        )
    try:
        output = await run_in_threadpool(
            _render, person, garment, category, garment_photo_type
        )
    finally:
        _INFERENCE_SLOT.release()
    return Response(
        content=output,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, private",
            "X-Cirvanna-Renderer": SERVICE,
            "X-Cirvanna-Model-Commit": PINNED_FASHN_VTON_COMMIT,
        },
    )


from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import logging
import os
from functools import lru_cache
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

PINNED_SAM3D_BODY_SOURCE_COMMIT = "b5c765a0d89d789985e186d396315e7590887b94"
DEFAULT_MODEL_ID = "facebook/sam-3d-body-dinov3"
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MIN_IMAGE_EDGE = 512
MIN_GPU_VRAM_GIB = 16

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("cirvanna.twin_generation_worker")

_ESTIMATOR: Any | None = None
_LOAD_ERROR: str | None = None
_INFERENCE_LOCK = threading.Lock()

app = FastAPI(
    title="Cirvanna SAM 3D Body Generation Worker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_digest(model_id: str, model_revision: str, source_commit: str, files: dict[str, str]) -> str:
    canonical = json.dumps(
        {
            "model_id": model_id,
            "model_revision": model_revision,
            "source_commit": source_commit,
            "files": dict(sorted(files.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _artifact_manifest() -> tuple[dict[str, Any] | None, str | None]:
    artifact_dir = Path(os.getenv("SAM3D_BODY_ARTIFACT_DIR", "/models/sam3d-body")).resolve()
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        return None, "artifact_manifest_missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "artifact_manifest_invalid"

    model_id = os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID).strip()
    model_revision = os.getenv("SAM3D_BODY_MODEL_REVISION", "").strip()
    expected_release = os.getenv("SAM3D_BODY_MODEL_RELEASE_SHA256", "").strip().lower()
    if manifest.get("schema_version") != 1:
        return None, "artifact_manifest_schema_unsupported"
    if manifest.get("model_id") != model_id:
        return None, "artifact_model_id_mismatch"
    if manifest.get("model_revision") != model_revision:
        return None, "artifact_model_revision_mismatch"
    if manifest.get("source_commit") != PINNED_SAM3D_BODY_SOURCE_COMMIT:
        return None, "artifact_source_commit_mismatch"
    if not re.fullmatch(r"[0-9a-f]{40}", model_revision):
        return None, "model_revision_not_pinned"

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return None, "artifact_file_manifest_missing"
    required_files = {
        os.getenv("SAM3D_BODY_CHECKPOINT_FILE", "model.ckpt"),
        os.getenv("SAM3D_BODY_CONFIG_FILE", "model_config.yaml"),
        os.getenv("SAM3D_BODY_MHR_FILE", "assets/mhr_model.pt"),
    }
    if not required_files.issubset(files.keys()):
        return None, "required_model_artifact_not_manifested"
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            return None, "artifact_file_manifest_invalid"
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            return None, "artifact_path_invalid"
        path = (artifact_dir / relative_path).resolve()
        if artifact_dir not in path.parents or not path.is_file():
            return None, "artifact_file_missing"
        if not re.fullmatch(r"[0-9a-f]{64}", expected.lower()):
            return None, "artifact_file_digest_invalid"
        if not hmac.compare_digest(_sha256_file(path), expected.lower()):
            return None, "artifact_file_digest_mismatch"

    computed_release = _release_digest(
        model_id, model_revision, PINNED_SAM3D_BODY_SOURCE_COMMIT, files
    )
    if not re.fullmatch(r"[0-9a-f]{64}", expected_release):
        return None, "model_release_digest_not_configured"
    if not hmac.compare_digest(computed_release, expected_release):
        return None, "model_release_digest_mismatch"
    if manifest.get("model_release_sha256") != computed_release:
        return None, "artifact_manifest_release_digest_mismatch"
    return manifest, None


def _gpu_status() -> tuple[bool, str]:
    try:
        import torch
    except Exception:
        return False, "pytorch_unavailable"
    if not torch.cuda.is_available():
        return False, "cuda_unavailable"
    try:
        properties = torch.cuda.get_device_properties(0)
        minimum = int(float(os.getenv("SAM3D_BODY_MIN_GPU_VRAM_GIB", MIN_GPU_VRAM_GIB)) * (1024 ** 3))
        if int(properties.total_memory) < minimum:
            return False, "insufficient_gpu_vram"
    except Exception:
        return False, "gpu_properties_unavailable"
    return True, "ready"


@lru_cache(maxsize=1)
def _configured() -> tuple[bool, str]:
    token = os.getenv("TWIN_GENERATION_WORKER_TOKEN", "")
    if len(token) < 32:
        return False, "internal_token_not_configured"
    if os.getenv("SAM3D_BODY_SOURCE_REF", "") != PINNED_SAM3D_BODY_SOURCE_COMMIT:
        return False, "source_revision_not_pinned"
    if os.getenv("SAM3D_BODY_LICENSE_ACCEPTED", "").lower() != "true":
        return False, "model_license_acceptance_not_recorded"
    if not os.getenv("SAM3D_BODY_LICENSE_EVIDENCE_ID", "").strip():
        return False, "model_license_evidence_missing"
    if os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID) != DEFAULT_MODEL_ID:
        return False, "unsupported_model_id"
    manifest, error = _artifact_manifest()
    if error:
        return False, error
    gpu_ready, gpu_reason = _gpu_status()
    if not gpu_ready:
        return False, gpu_reason
    return True, "ready"


def _artifact_path(env_name: str, default: str) -> Path:
    root = Path(os.getenv("SAM3D_BODY_ARTIFACT_DIR", "/models/sam3d-body")).resolve()
    relative = Path(os.getenv(env_name, default))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Invalid relative artifact path: {env_name}")
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise RuntimeError(f"Required model artifact is missing: {env_name}")
    return path


def _load_estimator() -> Any:
    import torch
    from sam_3d_body.build_models import load_sam_3d_body
    from sam_3d_body.sam_3d_body_estimator import SAM3DBodyEstimator

    checkpoint_path = _artifact_path("SAM3D_BODY_CHECKPOINT_FILE", "model.ckpt")
    config_path = _artifact_path("SAM3D_BODY_CONFIG_FILE", "model_config.yaml")
    mhr_path = _artifact_path("SAM3D_BODY_MHR_FILE", "assets/mhr_model.pt")
    if config_path.parent != checkpoint_path.parent:
        raise RuntimeError("model_config.yaml must be beside the checkpoint file.")
    model, model_cfg = load_sam_3d_body(
        checkpoint_path=str(checkpoint_path),
        device=torch.device("cuda"),
        mhr_path=str(mhr_path),
    )
    # No external detector, segmentation service or hosted FOV provider is used.
    # The worker accepts one user-confirmed full-body image and keeps it in memory.
    return SAM3DBodyEstimator(
        sam_3d_body_model=model,
        model_cfg=model_cfg,
        human_detector=None,
        human_segmentor=None,
        fov_estimator=None,
    )


def _image_from_bytes(raw: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_FORMAT"})
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(413, detail={"code": "IMAGE_PIXEL_LIMIT_EXCEEDED"})
            image = ImageOps.exif_transpose(source).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, detail={"code": "INVALID_IMAGE"})
    if min(image.size) < MIN_IMAGE_EDGE:
        raise HTTPException(422, detail={"code": "IMAGE_RESOLUTION_TOO_LOW"})
    return image


def _build_glb(vertices: Any, faces: Any, camera_translation: Any) -> tuple[bytes, int, int]:
    import numpy as np
    import trimesh

    vertices_array = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
    faces_array = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    translation = np.asarray(camera_translation, dtype=np.float32).reshape(3)
    if len(vertices_array) < 1000 or len(faces_array) < 1000:
        raise ValueError("Reconstruction did not produce a full-body mesh.")
    if not np.isfinite(vertices_array).all() or not np.isfinite(translation).all():
        raise ValueError("Reconstruction produced non-finite geometry.")
    if faces_array.min() < 0 or faces_array.max() >= len(vertices_array):
        raise ValueError("Reconstruction produced invalid face indices.")

    mesh = trimesh.Trimesh(
        vertices=vertices_array + translation,
        faces=faces_array,
        vertex_colors=np.tile(np.array([[145, 145, 145, 255]], dtype=np.uint8), (len(vertices_array), 1)),
        process=False,
    )
    rotation = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    mesh.apply_transform(rotation)
    extents = np.asarray(mesh.bounding_box.extents)
    if not np.isfinite(extents).all() or np.any(extents <= 1e-5):
        raise ValueError("Reconstruction produced degenerate body geometry.")
    exported = mesh.export(file_type="glb")
    if not isinstance(exported, bytes) or not exported.startswith(b"glTF"):
        raise ValueError("GLB serialization failed.")
    return exported, len(vertices_array), len(faces_array)


def _reconstruct(image: Image.Image) -> tuple[bytes, int, int]:
    import numpy as np

    if _ESTIMATOR is None:
        raise RuntimeError("Model estimator is not loaded.")
    rgb = np.asarray(image, dtype=np.uint8)
    # SAM 3D Body's "body" mode still returns a full-body mesh; hand refinement
    # is intentionally excluded from this first provider spike.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        outputs = _ESTIMATOR.process_one_image(rgb, inference_type="body")
    if not isinstance(outputs, list) or len(outputs) != 1:
        raise ValueError("Exactly one full-body subject is required.")
    output = outputs[0]
    return _build_glb(
        output["pred_vertices"],
        _ESTIMATOR.faces,
        output["pred_cam_t"],
    )


def _reconstruct_with_lock(image: Image.Image) -> tuple[bytes, int, int]:
    with _INFERENCE_LOCK:
        return _reconstruct(image)


def _require_internal_auth(authorization: str | None) -> None:
    expected = f"Bearer {os.getenv('TWIN_GENERATION_WORKER_TOKEN', '')}"
    if len(expected) <= 7 or not hmac.compare_digest(authorization or "", expected):
        raise HTTPException(401, detail={"code": "INTERNAL_AUTH_REQUIRED"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "twin-generation-worker"}


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    configured, reason = _configured()
    return {
        "provider_id": "sam3d-body-self-hosted",
        "model_id": os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID),
        "source_commit": PINNED_SAM3D_BODY_SOURCE_COMMIT,
        "generation_enabled": bool(configured and _ESTIMATOR is not None),
        "representation": "full_body_mesh",
        "input_mode": "single_full_body_image",
        "external_data_transfer": False,
        "measurement_calibrated": False,
        "registry_persistence_enabled": False,
        "reason": reason if not configured else ("model_not_loaded" if _ESTIMATOR is None else "ready"),
    }


@app.get("/ready")
def ready() -> JSONResponse | dict[str, Any]:
    configured, reason = _configured()
    if not configured:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": reason})
    if _ESTIMATOR is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": _LOAD_ERROR or "model_not_loaded"},
        )
    return {
        "status": "ready",
        "provider_id": "sam3d-body-self-hosted",
        "model_id": os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID),
        "model_revision": os.getenv("SAM3D_BODY_MODEL_REVISION"),
        "model_release_sha256": os.getenv("SAM3D_BODY_MODEL_RELEASE_SHA256"),
        "measurement_calibrated": False,
        "registry_persistence_enabled": False,
    }


@app.on_event("startup")
def load_model_on_startup() -> None:
    global _ESTIMATOR, _LOAD_ERROR
    configured, reason = _configured()
    if not configured:
        _LOAD_ERROR = reason
        logger.warning("SAM 3D Body worker remains not ready: %s", reason)
        return
    try:
        _ESTIMATOR = _load_estimator()
        _LOAD_ERROR = None
    except Exception as exc:
        _ESTIMATOR = None
        _LOAD_ERROR = type(exc).__name__
        logger.exception("SAM 3D Body model initialization failed")


@app.post("/internal/v1/reconstruct")
async def reconstruct(
    authorization: str | None = Header(default=None),
    source_asset_id: str = Form(...),
    consent_id: str = Form(...),
    single_person_confirmed: bool = Form(...),
    image: UploadFile = File(...),
) -> Response:
    _require_internal_auth(authorization)
    if not source_asset_id.strip() or len(source_asset_id) > 128:
        raise HTTPException(422, detail={"code": "INVALID_SOURCE_ASSET_ID"})
    if not consent_id.strip() or len(consent_id) > 128:
        raise HTTPException(422, detail={"code": "INVALID_CONSENT_ID"})
    if single_person_confirmed is not True:
        raise HTTPException(422, detail={"code": "SINGLE_PERSON_CONFIRMATION_REQUIRED"})
    configured, reason = _configured()
    if not configured or _ESTIMATOR is None:
        raise HTTPException(503, detail={"code": "TWIN_GENERATION_NOT_READY", "reason": reason if not configured else (_LOAD_ERROR or "model_not_loaded")})
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await image.close()
        raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_FORMAT"})
    raw = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED"})
    if not raw:
        raise HTTPException(422, detail={"code": "EMPTY_IMAGE"})
    pil_image = _image_from_bytes(raw)
    try:
        glb, vertex_count, face_count = await run_in_threadpool(_reconstruct_with_lock, pil_image)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "RECONSTRUCTION_INVALID", "message": str(exc)})
    except Exception:
        logger.exception("SAM 3D Body inference failed")
        raise HTTPException(502, detail={"code": "RECONSTRUCTION_FAILED"})

    model_revision = os.getenv("SAM3D_BODY_MODEL_REVISION", "")
    model_release_sha = os.getenv("SAM3D_BODY_MODEL_RELEASE_SHA256", "")
    job_id = str(uuid.uuid4())
    artifact_sha = hashlib.sha256(glb).hexdigest()
    return Response(
        content=glb,
        media_type="model/gltf-binary",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "X-Twin-Provider-ID": "sam3d-body-self-hosted",
            "X-Twin-Model-ID": os.getenv("SAM3D_BODY_MODEL_ID", DEFAULT_MODEL_ID),
            "X-Twin-Model-Revision": model_revision,
            "X-Twin-Model-Release-SHA256": model_release_sha,
            "X-Twin-Source-Commit": PINNED_SAM3D_BODY_SOURCE_COMMIT,
            "X-Twin-Artifact-SHA256": artifact_sha,
            "X-Twin-Job-ID": job_id,
            "X-Twin-Source-Asset-ID": source_asset_id,
            "X-Twin-Measurement-Status": "not_calibrated",
            "X-Twin-Registry-Eligible": "false",
            "X-Twin-Mesh-Vertices": str(vertex_count),
            "X-Twin-Mesh-Faces": str(face_count),
        },
    )

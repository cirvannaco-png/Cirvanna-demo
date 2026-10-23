"""Private model-backed visual search and pose-inference service.

This service stores neither submitted images nor generated twin assets. Marketplace
results are fetched live from Commerce, and only currently active/in-stock offers
are considered. Model outputs are ranked evidence, not calibrated probabilities.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import uuid
from pathlib import Path
from typing import Annotated, Any

import httpx
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from starlette import status
from urllib.parse import urlsplit

SERVICE = "cirvanna-vision-intelligence"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_PAGE_SIZE = 100
MAX_MARKETPLACE_CANDIDATES = 1000
MODEL_ID = os.getenv("CLIP_MODEL_ID", "openai/clip-vit-base-patch32")
SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp"}
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna Vision Intelligence", version="0.1.0")

_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_POSE_LANDMARKER = None
_TEXT_VECTOR_CACHE: dict[str, list[float]] = {}


def _token() -> str:
    return os.getenv("VISION_WORKER_TOKEN", "").strip()


def require_worker_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = _token()
    if len(expected.encode()) < 32:
        raise HTTPException(503, detail={"code": "VISION_AUTH_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"}, headers={"WWW-Authenticate": "Bearer"})


def _trusted_base(name: str, *, required: bool = True) -> str | None:
    raw = os.getenv(name, "").strip().rstrip("/")
    if not raw:
        if required:
            raise HTTPException(503, detail={"code": f"{name}_NOT_CONFIGURED"})
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise HTTPException(503, detail={"code": f"{name}_MUST_BE_TRUSTED_HTTPS"})
    return raw


def _model_configured() -> tuple[bool, str]:
    revision = os.getenv("CLIP_MODEL_REVISION", "").strip()
    if not SHA40.fullmatch(revision):
        return False, "pinned_clip_model_revision_required"
    if not MODEL_ID or "/" not in MODEL_ID:
        return False, "clip_model_id_invalid"
    return True, "configured"


def _pose_model_configured() -> tuple[bool, str]:
    model_path = os.getenv("POSE_LANDMARKER_MODEL_PATH", "").strip()
    expected = os.getenv("POSE_LANDMARKER_MODEL_SHA256", "").strip().lower()
    if not model_path or not SHA256.fullmatch(expected):
        return False, "pose_model_path_and_sha256_required"
    path = Path(model_path)
    if not path.is_file():
        return False, "pose_model_asset_missing"
    try:
        digest_builder = hashlib.sha256()
        with path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest_builder.update(chunk)
        digest = digest_builder.hexdigest()
    except OSError:
        return False, "pose_model_asset_unreadable"
    if not hmac.compare_digest(digest, expected):
        return False, "pose_model_sha256_mismatch"
    return True, "configured"


def _clip():
    global _CLIP_MODEL, _CLIP_PROCESSOR
    if _CLIP_MODEL is None or _CLIP_PROCESSOR is None:
        configured, reason = _model_configured()
        if not configured:
            raise HTTPException(503, detail={"code": "CLIP_MODEL_NOT_CONFIGURED", "reason": reason})
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            revision = os.environ["CLIP_MODEL_REVISION"].strip()
            model = CLIPModel.from_pretrained(MODEL_ID, revision=revision, trust_remote_code=False)
            processor = CLIPProcessor.from_pretrained(MODEL_ID, revision=revision, trust_remote_code=False)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
            model.eval()
            _CLIP_MODEL, _CLIP_PROCESSOR = (model, processor)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, detail={"code": "CLIP_MODEL_LOAD_FAILED"}) from exc
    return _CLIP_MODEL, _CLIP_PROCESSOR


_MODEL_LOAD_ERRORS: dict[str, str] = {}


def _warm_start_models() -> None:
    """Load only fully pinned, provisioned models; keep startup errors sanitized."""
    if _model_configured()[0]:
        try:
            _clip()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            _MODEL_LOAD_ERRORS["clip"] = str(detail.get("code", "CLIP_MODEL_LOAD_FAILED"))
    if _pose_model_configured()[0]:
        try:
            _pose()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            _MODEL_LOAD_ERRORS["pose"] = str(detail.get("code", "POSE_MODEL_LOAD_FAILED"))


app.add_event_handler("startup", _warm_start_models)


def _pose():
    global _POSE_LANDMARKER
    if _POSE_LANDMARKER is None:
        configured, reason = _pose_model_configured()
        if not configured:
            raise HTTPException(503, detail={"code": "POSE_MODEL_NOT_CONFIGURED", "reason": reason})
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            options = vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=os.environ["POSE_LANDMARKER_MODEL_PATH"]),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.6,
                min_pose_presence_confidence=0.6,
                min_tracking_confidence=0.6,
                output_segmentation_masks=False,
            )
            _POSE_LANDMARKER = vision.PoseLandmarker.create_from_options(options)
        except Exception as exc:
            raise HTTPException(503, detail={"code": "POSE_MODEL_LOAD_FAILED"}) from exc
    return _POSE_LANDMARKER


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
            if source.width < 128 or source.height < 128:
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


def evaluate_image_quality(image: Image.Image) -> dict[str, Any]:
    """Deterministic capture-quality checks; not an inference-accuracy score."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    dx = np.diff(gray, axis=1)
    dy = np.diff(gray, axis=0)
    sharpness = float((np.var(dx) + np.var(dy)) / 2.0) if dx.size and dy.size else 0.0
    clipped_fraction = float(np.mean((gray <= 3.0) | (gray >= 252.0)))
    failures: list[str] = []
    if brightness < 18.0:
        failures.append("image_too_dark")
    if brightness > 238.0:
        failures.append("image_too_bright")
    if contrast < 8.0:
        failures.append("low_contrast")
    if sharpness < 1.5:
        failures.append("image_may_be_blurry")
    if clipped_fraction > 0.55:
        failures.append("excessive_clipping")
    return {
        "passed": not failures,
        "width": image.width,
        "height": image.height,
        "brightness_mean": round(brightness, 3),
        "contrast_std": round(contrast, 3),
        "sharpness_proxy": round(sharpness, 3),
        "clipped_pixel_fraction": round(clipped_fraction, 4),
        "failure_codes": failures,
        "interpretation": "capture_quality_only_not_model_or_fit_confidence",
    }


def _unit_vector(vector: Any) -> list[float]:
    values = vector.detach().float().cpu().numpy().reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(values))
    if not np.isfinite(values).all() or not np.isfinite(norm) or norm <= 0:
        raise HTTPException(502, detail={"code": "INVALID_MODEL_EMBEDDING"})
    return (values / norm).astype(float).tolist()


def _image_embedding(image: Image.Image) -> list[float]:
    model, processor = _clip()
    try:
        import torch

        inputs = processor(images=image, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = model.get_image_features(**inputs)
        return _unit_vector(output)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, detail={"code": "IMAGE_EMBEDDING_FAILED"}) from exc


def _text_embedding(text: str) -> list[float]:
    clean = " ".join(text.split())[:1000]
    if not clean:
        raise HTTPException(422, detail={"code": "SEARCH_DESCRIPTION_REQUIRED"})
    cache_key = hashlib.sha256(clean.casefold().encode("utf-8")).hexdigest()
    cached = _TEXT_VECTOR_CACHE.get(cache_key)
    if cached is not None:
        return cached
    model, processor = _clip()
    try:
        import torch

        inputs = processor(text=[clean], return_tensors="pt", padding=True, truncation=True, max_length=77)
        device = next(model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = model.get_text_features(**inputs)
        embedding = _unit_vector(output)
        if len(_TEXT_VECTOR_CACHE) >= 10000:
            _TEXT_VECTOR_CACHE.clear()
        _TEXT_VECTOR_CACHE[cache_key] = embedding
        return embedding
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, detail={"code": "TEXT_EMBEDDING_FAILED"}) from exc


def _offer_description(offer: dict[str, Any], product: dict[str, Any] | None) -> str:
    product = product or {}
    attributes = product.get("attributes") or {}
    options = offer.get("options") or {}
    parts = [
        "Fashion or beauty marketplace product.",
        str(offer.get("product_name") or product.get("name") or ""),
        str(product.get("description") or ""),
        str(offer.get("category") or product.get("category") or ""),
        str(product.get("brand") or ""),
        str(offer.get("sku") or product.get("sku") or ""),
        json.dumps(attributes, ensure_ascii=True, sort_keys=True)[:1200] if isinstance(attributes, dict) else "",
        json.dumps(options, ensure_ascii=True, sort_keys=True)[:500] if isinstance(options, dict) else "",
    ]
    return " ".join(part for part in parts if part).strip()[:2000]


async def _get_json(
    client: httpx.AsyncClient, url: str, *, params: Any = None, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    try:
        response = await client.get(url, params=params, headers=headers or {}, follow_redirects=False)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "MARKETPLACE_SEARCH_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "MARKETPLACE_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "MARKETPLACE_SERVICE_UNAVAILABLE", "upstream_status": response.status_code})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "INVALID_MARKETPLACE_RESPONSE"}) from exc
    if not isinstance(result, dict):
        raise HTTPException(502, detail={"code": "INVALID_MARKETPLACE_RESPONSE"})
    return result


async def _live_offers() -> tuple[list[dict[str, Any]], bool]:
    """Load current purchasable offers; stop at a bounded catalog size."""
    commerce_base = _trusted_base("COMMERCE_API_URL")
    catalog_base = _trusted_base("CATALOG_API_URL")
    catalog_token = os.getenv("CATALOG_API_TOKEN", "").strip() or os.getenv("CATALOG_READ_TOKEN", "").strip()
    if not catalog_token:
        raise HTTPException(503, detail={"code": "CATALOG_READ_TOKEN_NOT_CONFIGURED"})
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False, follow_redirects=False
    ) as client:
        first = await _get_json(client, commerce_base + "/marketplace/offers", params={"offset": 0, "limit": MAX_PAGE_SIZE})
        items = first.get("items")
        total = first.get("total")
        if not isinstance(items, list) or not isinstance(total, int) or total < 0:
            raise HTTPException(502, detail={"code": "INVALID_MARKETPLACE_RESPONSE"})
        offers = [item for item in items if isinstance(item, dict)]
        bounded_total = min(total, MAX_MARKETPLACE_CANDIDATES)
        for offset in range(MAX_PAGE_SIZE, bounded_total, MAX_PAGE_SIZE):
            page = await _get_json(
                client, commerce_base + "/marketplace/offers",
                params={"offset": offset, "limit": min(MAX_PAGE_SIZE, bounded_total - offset)},
            )
            page_items = page.get("items")
            if not isinstance(page_items, list):
                raise HTTPException(502, detail={"code": "INVALID_MARKETPLACE_RESPONSE"})
            offers.extend(item for item in page_items if isinstance(item, dict))
        truncated = total > MAX_MARKETPLACE_CANDIDATES
        ids = sorted({str(item.get("catalog_product_id", "")).strip() for item in offers if item.get("catalog_product_id")})
        products: dict[str, dict[str, Any]] = {}
        for start in range(0, len(ids), MAX_PAGE_SIZE):
            batch = ids[start:start + MAX_PAGE_SIZE]
            try:
                result = await _get_json(
                    client,
                    catalog_base + "/products/batch",
                    params=[("ids", pid) for pid in batch],
                    headers={"Authorization": "Bearer " + catalog_token, "Accept": "application/json"},
                )
            except HTTPException:
                # Product descriptions are important for cross-modal matching.
                # Fail closed rather than silently downgrading to title-only retrieval.
                raise
            product_items = result.get("items")
            if not isinstance(product_items, list):
                raise HTTPException(502, detail={"code": "INVALID_CATALOG_BATCH_RESPONSE"})
            for product in product_items:
                if isinstance(product, dict) and product.get("product_id"):
                    products[str(product["product_id"])] = product
    joined: list[dict[str, Any]] = []
    for offer in offers:
        pid = str(offer.get("catalog_product_id", "")).strip()
        product = products.get(pid)
        if not pid or product is None or product.get("status") != "active":
            continue
        merged = dict(offer)
        merged["product"] = {
            "product_id": pid,
            "name": product.get("name"),
            "description": product.get("description"),
            "category": product.get("category"),
            "brand": product.get("brand"),
            "attributes": product.get("attributes") or {},
            "image_urls": product.get("image_urls") or [],
        }
        merged["search_text"] = _offer_description(merged, product)
        joined.append(merged)
    return joined, truncated


def _rank_offers(query_vector: list[float], offers: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not offers:
        return []
    vectors: dict[str, dict[str, Any]] = {}
    texts: list[str] = []
    keys: list[str] = []
    for offer in offers:
        text = str(offer.get("search_text", ""))
        cache_key = hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
        if cache_key not in _TEXT_VECTOR_CACHE:
            texts.append(text[:1000])
            keys.append(cache_key)
    if texts:
        model, processor = _clip()
        try:
            import torch

            for start in range(0, len(texts), 32):
                chunk = texts[start:start + 32]
                inputs = processor(text=chunk, return_tensors="pt", padding=True, truncation=True, max_length=77)
                device = next(model.parameters()).device
                inputs = {key: value.to(device) for key, value in inputs.items()}
                with torch.inference_mode():
                    output = model.get_text_features(**inputs)
                matrix = output.detach().float().cpu().numpy()
                norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                if not np.isfinite(matrix).all() or np.any(norms <= 0):
                    raise ValueError("invalid text feature matrix")
                matrix = matrix / norms
                for key, vector in zip(keys[start:start + 32], matrix):
                    _TEXT_VECTOR_CACHE[key] = vector.astype(float).tolist()
            if len(_TEXT_VECTOR_CACHE) > 10000:
                # Keep cache bounded; active product listing is re-read on every query.
                for key in list(_TEXT_VECTOR_CACHE)[:5000]:
                    _TEXT_VECTOR_CACHE.pop(key, None)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, detail={"code": "MARKETPLACE_EMBEDDING_FAILED"}) from exc
    for offer in offers:
        key = hashlib.sha256(str(offer.get("search_text", "")).casefold().encode("utf-8")).hexdigest()
        vector = _TEXT_VECTOR_CACHE.get(key)
        if vector is not None:
            score = float(np.dot(np.asarray(query_vector, dtype=np.float32), np.asarray(vector, dtype=np.float32)))
            result = dict(offer)
            result.pop("search_text", None)
            result["match_score"] = round(score, 6)
            result["match_score_type"] = "cosine_similarity_not_probability"
            vectors[str(offer.get("variant_id", ""))] = {"score": score, "result": result}
    ordered = sorted(vectors.values(), key=lambda item: item["score"], reverse=True)
    return [item["result"] for item in ordered[:limit]]


class TextSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=25)

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split()).strip()


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, Any]:
    clip_configured, clip_reason = _model_configured()
    pose_configured, pose_reason = _pose_model_configured()
    token_configured = len(_token().encode()) >= 32
    commerce_configured = bool(os.getenv("COMMERCE_API_URL", "").strip())
    catalog_configured = bool(os.getenv("CATALOG_API_URL", "").strip()) and bool(
        os.getenv("CATALOG_API_TOKEN", "").strip() or os.getenv("CATALOG_READ_TOKEN", "").strip()
    )
    models_loaded = _CLIP_MODEL is not None and _CLIP_PROCESSOR is not None and _POSE_LANDMARKER is not None
    configured = clip_configured and pose_configured and token_configured and commerce_configured and catalog_configured
    ready = configured and models_loaded
    result = {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE,
        "ready": ready,
        "configuration_valid": configured,
        "models_loaded": models_loaded,
        "clip_model_configured": clip_configured,
        "clip_model_reason": clip_reason,
        "clip_model_id": MODEL_ID,
        "clip_model_revision": os.getenv("CLIP_MODEL_REVISION", "") if clip_configured else None,
        "clip_model_loaded": _CLIP_MODEL is not None and _CLIP_PROCESSOR is not None,
        "clip_model_startup_error": _MODEL_LOAD_ERRORS.get("clip"),
        "pose_model_configured": pose_configured,
        "pose_model_reason": pose_reason,
        "pose_model_loaded": _POSE_LANDMARKER is not None,
        "pose_model_startup_error": _MODEL_LOAD_ERRORS.get("pose"),
        "marketplace_services_configured": commerce_configured and catalog_configured,
        "worker_auth_configured": token_configured,
        "input_persistence": False,
        "product_image_fetching": False,
        "results_are_live_active_offers": True,
        "similarity_scores_calibrated": False,
        "full_surface_mesh": False,
    }
    if not ready:
        raise HTTPException(503, detail=result)
    return result


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, Any]:
    clip_configured, _ = _model_configured()
    pose_configured, _ = _pose_model_configured()
    commerce_configured = bool(os.getenv("COMMERCE_API_URL", "").strip())
    catalog_configured = bool(os.getenv("CATALOG_API_URL", "").strip()) and bool(
        os.getenv("CATALOG_API_TOKEN", "").strip() or os.getenv("CATALOG_READ_TOKEN", "").strip()
    )
    return {
        "service": SERVICE,
        "model_backed_image_search": clip_configured and commerce_configured and catalog_configured and _CLIP_MODEL is not None,
        "description_search": clip_configured and commerce_configured and catalog_configured and _CLIP_MODEL is not None,
        "pose_3d_landmark_inference": pose_configured and _POSE_LANDMARKER is not None,
        "full_surface_mesh": False,
        "fit_grade_anthropometry": False,
        "input_image_persistence": False,
        "product_image_fetching": False,
        "similarity_scores_calibrated": False,
        "model_revision_pinned": clip_configured,
    }


@app.post("/v1/search/text", dependencies=[Depends(require_worker_auth)], tags=["marketplace"])
async def search_by_description(payload: TextSearchRequest) -> dict[str, Any]:
    query = payload.normalized_query
    offers, truncated = await _live_offers()
    if payload.category:
        category = payload.category.strip().casefold()
        offers = [
            item for item in offers
            if str(item.get("category", "")).casefold() == category
            or str((item.get("product") or {}).get("category", "")).casefold() == category
        ]
    query_vector = _text_embedding("A marketplace product matching this description: " + query)
    results = _rank_offers(query_vector, offers, payload.limit)
    return {
        "status": "complete",
        "query": query,
        "candidate_count": len(offers),
        "results": results,
        "catalog_truncated": truncated,
        "model": {"id": MODEL_ID, "revision": os.getenv("CLIP_MODEL_REVISION")},
        "scores_are_probabilities": False,
    }


@app.post("/v1/click-it/scan", dependencies=[Depends(require_worker_auth)], tags=["click-it"])
async def click_it_scan(
    consent_image_processing: Annotated[bool, Form()],
    consent_click_it: Annotated[bool, Form()],
    image: Annotated[UploadFile, File()],
    category: Annotated[str | None, Form()] = None,
    limit: Annotated[int, Form(ge=1, le=25)] = 10,
) -> dict[str, Any]:
    if not consent_image_processing or not consent_click_it:
        await image.close()
        raise HTTPException(403, detail={"code": "EXPLICIT_CLICK_IT_CONSENT_REQUIRED"})
    content_type = image.content_type or ""
    try:
        data = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await image.close()
    decoded = _decode_image(data, content_type)
    quality = evaluate_image_quality(decoded)
    if not quality["passed"]:
        raise HTTPException(
            422,
            detail={
                "code": "IMAGE_QUALITY_REJECTED",
                "quality": quality,
                "message": "Retake the photo with better lighting, focus, contrast, and the product clearly in frame.",
            },
        )
    query_vector = _image_embedding(decoded)
    offers, truncated = await _live_offers()
    if category and category.strip():
        selected = category.strip().casefold()
        offers = [
            item for item in offers
            if str(item.get("category", "")).casefold() == selected
            or str((item.get("product") or {}).get("category", "")).casefold() == selected
        ]
    results = _rank_offers(query_vector, offers, limit)
    return {
        "status": "complete",
        "scan_id": str(uuid.uuid4()),
        "search_mode": "image_to_catalog_text_similarity",
        "image_quality": quality,
        "candidate_count": len(offers),
        "results": results,
        "catalog_truncated": truncated,
        "model": {"id": MODEL_ID, "revision": os.getenv("CLIP_MODEL_REVISION")},
        "scores_are_probabilities": False,
        "warning": "Scores rank the live catalog but are not calibrated match probabilities; visually verify the result before buying.",
        "image_persisted": False,
    }


@app.post("/v1/twin/infer", dependencies=[Depends(require_worker_auth)], tags=["virtual-twin"])
async def infer_twin_pose(
    consent_image_processing: Annotated[bool, Form()],
    consent_body_measurements: Annotated[bool, Form()],
    height_cm: Annotated[float, Form(gt=80, le=260)],
    image: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    if not consent_image_processing or not consent_body_measurements:
        await image.close()
        raise HTTPException(403, detail={"code": "EXPLICIT_TWIN_CONSENT_REQUIRED"})
    content_type = image.content_type or ""
    try:
        data = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await image.close()
    decoded = _decode_image(data, content_type)
    quality = evaluate_image_quality(decoded)
    if not quality["passed"]:
        raise HTTPException(
            422,
            detail={"code": "IMAGE_QUALITY_REJECTED", "quality": quality,
                    "message": "Retake a clear, well-lit full-body image with head and feet visible."},
        )
    try:
        import mediapipe as mp

        detector = _pose()
        rgb = np.asarray(decoded, dtype=np.uint8)
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, detail={"code": "POSE_INFERENCE_FAILED"}) from exc
    normalized_groups = getattr(result, "pose_landmarks", None) or []
    world_groups = getattr(result, "pose_world_landmarks", None) or []
    if not normalized_groups or not world_groups:
        raise HTTPException(422, detail={"code": "NO_BODY_POSE_DETECTED", "message": "Use one clear, full-body image with the subject facing the camera."})
    normalized = normalized_groups[0]
    world = world_groups[0]
    critical = [11, 12, 23, 24, 27, 28]
    visibilities = [float(getattr(normalized[index], "visibility", 0.0) or 0.0) for index in critical]
    mean_visibility = float(np.mean([float(getattr(item, "visibility", 0.0) or 0.0) for item in normalized]))
    if len(normalized) < 33 or len(world) < 33 or min(visibilities) < 0.45:
        raise HTTPException(422, detail={"code": "BODY_LANDMARKS_INCOMPLETE", "visibility": round(mean_visibility, 4)})
    names = [
        "nose","left_eye_inner","left_eye","left_eye_outer","right_eye_inner","right_eye","right_eye_outer",
        "left_ear","right_ear","mouth_left","mouth_right","left_shoulder","right_shoulder","left_elbow",
        "right_elbow","left_wrist","right_wrist","left_pinky","right_pinky","left_index","right_index",
        "left_thumb","right_thumb","left_hip","right_hip","left_knee","right_knee","left_ankle",
        "right_ankle","left_heel","right_heel","left_foot_index","right_foot_index",
    ]
    landmarks = []
    for index, name in enumerate(names):
        point = normalized[index]
        metric = world[index]
        landmarks.append({
            "name": name,
            "image": {
                "x": round(float(point.x), 6), "y": round(float(point.y), 6), "z": round(float(point.z), 6),
                "visibility": round(float(getattr(point, "visibility", 0.0) or 0.0), 5),
            },
            "world": {
                "x_m_approx": round(float(metric.x), 6), "y_m_approx": round(float(metric.y), 6),
                "z_m_approx": round(float(metric.z), 6),
            },
        })
    return {
        "status": "partial_twin_inference",
        "representation_type": "3d_pose_skeleton",
        "inference_id": str(uuid.uuid4()),
        "model": {"family": "MediaPipe Pose Landmarker", "model_asset_sha256": os.getenv("POSE_LANDMARKER_MODEL_SHA256", "").lower()},
        "input_quality": quality,
        "pose_quality": {
            "mean_landmark_visibility": round(mean_visibility, 5),
            "critical_landmark_visibility": {names[index]: round(visibilities[pos], 5) for pos, index in enumerate(critical)},
            "status": "landmarks_detected_not_calibrated_for_measurement",
        },
        "declared_height_cm": height_cm,
        "landmarks": landmarks,
        "surface_mesh_available": False,
        "fit_grade_measurements_available": False,
        "image_persisted": False,
        "disclaimer": "This is a model-inferred 3D pose skeleton, not a body-surface mesh or calibrated anthropometric measurement. Do not use for sizing or purchase approval until validated against ground truth.",
    }


@app.post("/v1/ops/reset-text-cache", dependencies=[Depends(require_worker_auth)], include_in_schema=False)
def reset_text_cache() -> dict[str, bool]:
    _TEXT_VECTOR_CACHE.clear()
    return {"cleared": True}

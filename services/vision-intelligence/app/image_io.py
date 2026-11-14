"""Shared in-memory image decoding and deterministic quality checks."""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def decode_image(
    data: bytes,
    content_type: str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    max_pixels: int = 25_000_000,
    min_dimension: int = 128,
) -> Image.Image:
    """Decode a bounded JPEG/PNG/WebP upload into a metadata-free RGB image."""
    if content_type not in SUPPORTED_MIME:
        raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_TYPE"})
    if not data:
        raise HTTPException(400, detail={"code": "EMPTY_IMAGE"})
    if len(data) > max_bytes:
        raise HTTPException(413, detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": max_bytes})
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != MIME_TO_FORMAT[content_type]:
                raise HTTPException(415, detail={"code": "IMAGE_MIME_MISMATCH"})
            if source.width < min_dimension or source.height < min_dimension:
                raise HTTPException(422, detail={"code": "IMAGE_DIMENSIONS_TOO_SMALL"})
            if source.width * source.height > max_pixels:
                raise HTTPException(413, detail={"code": "IMAGE_PIXEL_LIMIT_EXCEEDED"})
            source.load()
            image = source.convert("RGB")
            image.info.clear()
            return image
    except HTTPException:
        raise
    except Image.DecompressionBombError as exc:
        raise HTTPException(
            413,
            detail={"code": "IMAGE_PIXEL_LIMIT_EXCEEDED", "maximum_pixels": max_pixels},
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "INVALID_IMAGE_DATA"}) from exc


def evaluate_image_quality(image: Image.Image) -> dict[str, Any]:
    """Report basic exposure/contrast/blur diagnostics, not model accuracy."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    center = gray[1:-1, 1:-1]
    laplacian = (
        gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
        - 4.0 * center
    )
    sharpness = float(np.var(laplacian)) if laplacian.size else 0.0
    clipped_fraction = float(np.mean((gray <= 3.0) | (gray >= 252.0)))
    failures: list[str] = []
    if brightness < 18.0:
        failures.append("image_too_dark")
    if brightness > 238.0:
        failures.append("image_too_bright")
    if contrast < 8.0:
        failures.append("low_contrast")
    if sharpness < 20.0:
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

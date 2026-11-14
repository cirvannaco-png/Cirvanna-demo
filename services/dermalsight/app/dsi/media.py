"""Bounded in-memory media handling for DermalSight and DSI."""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


async def read_and_decode_image(
    upload: UploadFile,
    *,
    max_bytes: int,
    max_pixels: int,
    allowed_mime_types: set[str],
    mime_to_format: dict[str, str],
) -> np.ndarray:
    if upload.content_type not in allowed_mime_types:
        await upload.close()
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_IMAGE_TYPE", "allowed": sorted(allowed_mime_types)},
        )
    try:
        content = await upload.read(max_bytes + 1)
    finally:
        await upload.close()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"code": "IMAGE_SIZE_LIMIT_EXCEEDED", "maximum_bytes": max_bytes},
        )
    if not content:
        raise HTTPException(status_code=400, detail={"code": "EMPTY_IMAGE"})
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format != mime_to_format[upload.content_type]:
                raise HTTPException(status_code=415, detail={"code": "IMAGE_MIME_MISMATCH"})
            if source.width <= 0 or source.height <= 0 or source.width * source.height > max_pixels:
                raise HTTPException(
                    status_code=413,
                    detail={"code": "IMAGE_PIXEL_LIMIT_EXCEEDED", "maximum_pixels": max_pixels},
                )
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.load()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IMAGE"}) from exc
    return np.asarray(image, dtype=np.uint8)

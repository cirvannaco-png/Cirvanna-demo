"""Local compatibility shim for FASHN VTON's parser interface.

The production worker is deliberately restricted to segmentation-free person
images and flat-lay garment images. In that supported mode FASHN's preprocessing
functions return the original images unchanged, so parser labels are not used.
This shim prevents installation or loading of the separately licensed
fashn-human-parser package. Do not enable model-worn garment mode with this shim.
"""
from __future__ import annotations

import numpy as np

CATEGORY_TO_BODY_COVERAGE = {
    "tops": "upper",
    "bottoms": "lower",
    "one-pieces": "full",
}
BODY_COVERAGE_TO_LABELS = {
    "upper": ["tops"],
    "lower": ["bottoms"],
    "full": ["one-pieces"],
}
LABELS_TO_IDS = {"tops": 1, "bottoms": 2, "one-pieces": 3}
IDENTITY_LABELS: tuple[str, ...] = ()


class FashnHumanParser:
    """No-op parser required by the upstream interface in maskless flat-lay mode."""

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def predict(self, image: np.ndarray) -> np.ndarray:
        if not isinstance(image, np.ndarray) or image.ndim != 3:
            raise ValueError("Expected an HxWxC image array.")
        return np.zeros(image.shape[:2], dtype=np.uint8)

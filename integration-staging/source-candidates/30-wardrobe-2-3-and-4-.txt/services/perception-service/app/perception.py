"""CLIP-based zero-shot garment analysis (singleton model loader)."""
from __future__ import annotations

import logging
import threading
from io import BytesIO
from typing import Any

import httpx
import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from common.domain import ColorVector

from .config import CLIP_DEVICE, CLIP_MODEL

logger = logging.getLogger(__name__)

SIL_CLASSES = ["fitted", "relaxed", "oversized", "structured", "fluid"]
TEX_CLASSES = ["smooth", "coarse", "knit", "reflective", "matte"]


class CLIPPerception:
    _instance: "CLIPPerception | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "CLIPPerception":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        device = CLIP_DEVICE
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        logger.info(f"Loading CLIP model {CLIP_MODEL} on {device}")
        self.model = CLIPModel.from_pretrained(CLIP_MODEL).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(CLIP_MODEL)
        self._sil_text = self.processor(
            text=[f"a {c} clothing item" for c in SIL_CLASSES],
            return_tensors="pt", padding=True,
        )
        self._tex_text = self.processor(
            text=[f"{c} fabric texture" for c in TEX_CLASSES],
            return_tensors="pt", padding=True,
        )
        logger.info("CLIP model ready")

    async def analyze(
        self, image_url: str, category_hint: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any], list[float]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(image_url)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")

        inputs = self.processor(images=img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            emb = self.model.get_image_features(**inputs).cpu().numpy().flatten()

        e_t = torch.tensor(emb, device=self.device)
        with torch.no_grad():
            sil_f = self.model.get_text_features(**{k: v.to(self.device) for k, v in self._sil_text.items()})
            tex_f = self.model.get_text_features(**{k: v.to(self.device) for k, v in self._tex_text.items()})
            sil_sim = (sil_f @ e_t).softmax(dim=0)
            tex_sim = (tex_f @ e_t).softmax(dim=0)

        sil = SIL_CLASSES[int(sil_sim.argmax().item())]
        tex = TEX_CLASSES[int(tex_sim.argmax().item())]

        arr = np.asarray(img)
        avg = arr.mean(axis=(0, 1)).astype(int)
        cv = ColorVector.from_rgb(int(avg[0]), int(avg[1]), int(avg[2]))
        variance = float(np.var(arr, axis=(0, 1)).mean() / 255.0)

        gray = np.asarray(img.convert("L"))
        mag = np.log(np.abs(np.fft.fftshift(np.fft.fft2(gray))) + 1)
        pattern = float(np.mean(mag > 10)) if np.any(mag > 10) else 0.0

        geometry = {
            "silhouette_class": sil,
            "length_profile": "hip",
            "volume_distribution": [0.33, 0.34, 0.33],
            "stretch_behavior": "semi_flexible",
        }
        surface = {
            "dominant_color": cv.to_dict(),
            "color_variance": variance,
            "texture_class": tex,
            "pattern_density": pattern,
            "lighting_risk": 0.3,
        }
        return geometry, surface, emb.tolist()

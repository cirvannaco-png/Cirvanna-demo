"""Verified ONNX model adapter for non-diagnostic cosmetic skin attributes.

A model is never considered available unless its manifest is valid, the local
artifact hash matches, and the runtime exposes the declared input/output names.
No heuristic substitute is used when the model is missing.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image


class ModelConfigurationError(RuntimeError):
    """Raised when the model artifact or manifest is missing or invalid."""


_ATTRIBUTE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_HEX_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class ONNXSkinModel:
    """Loads and executes one explicitly versioned ONNX attribute model.

    Manifest schema (version 1)::

        {
          "schema_version": 1,
          "model_version": "1.0.0",
          "task": "cosmetic_skin_attributes",
          "model_sha256": "<64 lowercase hex chars>",
          "input": {
            "name": "input", "width": 224, "height": 224,
            "layout": "NCHW", "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225]
          },
          "output": {
            "name": "scores", "activation": "sigmoid",
            "attributes": ["texture_variation", "visible_color_variation"]
          }
        }

    Scores are numeric model outputs in [0, 1], not calibrated probabilities,
    diagnoses, or evidence of clinical performance.
    """

    def __init__(
        self,
        model_path: str | Path,
        manifest_path: str | Path,
        *,
        session_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.manifest_path = Path(manifest_path)
        if not self.model_path.is_file() or not self.manifest_path.is_file():
            raise ModelConfigurationError("Model artifact or manifest is missing.")

        try:
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ModelConfigurationError("Model manifest is not valid UTF-8 JSON.") from exc
        self._validate_manifest(self.manifest)

        hasher = hashlib.sha256()
        with self.model_path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != self.manifest["model_sha256"]:
            raise ModelConfigurationError("Model artifact SHA-256 does not match the manifest.")

        if session_factory is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise ModelConfigurationError(
                    "onnxruntime is not installed; install the service requirements."
                ) from exc
            session_factory = lambda path: ort.InferenceSession(
                path, providers=["CPUExecutionProvider"]
            )

        try:
            self.session = session_factory(str(self.model_path))
            input_names = {item.name for item in self.session.get_inputs()}
            output_names = {item.name for item in self.session.get_outputs()}
        except Exception as exc:
            raise ModelConfigurationError("ONNX model could not be loaded by the runtime.") from exc

        if self.manifest["input"]["name"] not in input_names:
            raise ModelConfigurationError("Manifest input name is absent from the ONNX model.")
        if self.manifest["output"]["name"] not in output_names:
            raise ModelConfigurationError("Manifest output name is absent from the ONNX model.")

    @staticmethod
    def _validate_manifest(manifest: Any) -> None:
        if not isinstance(manifest, dict):
            raise ModelConfigurationError("Model manifest must be a JSON object.")
        if manifest.get("schema_version") != 1:
            raise ModelConfigurationError("Unsupported model manifest schema version.")
        version = manifest.get("model_version")
        if not isinstance(version, str) or not version.strip() or len(version) > 64:
            raise ModelConfigurationError("Manifest model_version is required.")
        if manifest.get("task") != "cosmetic_skin_attributes":
            raise ModelConfigurationError("Only cosmetic_skin_attributes models are supported.")
        digest = manifest.get("model_sha256")
        if not isinstance(digest, str) or not _HEX_SHA256_RE.fullmatch(digest):
            raise ModelConfigurationError("Manifest must contain a lowercase SHA-256 digest.")

        input_spec = manifest.get("input")
        if not isinstance(input_spec, dict):
            raise ModelConfigurationError("Manifest input specification is required.")
        if not isinstance(input_spec.get("name"), str) or not input_spec["name"]:
            raise ModelConfigurationError("Manifest input tensor name is required.")
        if input_spec.get("layout") != "NCHW":
            raise ModelConfigurationError("Only NCHW RGB model inputs are supported.")
        for key in ("width", "height"):
            value = input_spec.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 32 <= value <= 1024:
                raise ModelConfigurationError(f"Input {key} must be an integer between 32 and 1024.")
        for key in ("mean", "std"):
            values = input_spec.get(key)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(not isinstance(v, (int, float)) or not np.isfinite(v) for v in values)
            ):
                raise ModelConfigurationError(f"Input {key} must contain three finite numbers.")
        if any(float(value) <= 0 for value in input_spec["std"]):
            raise ModelConfigurationError("Input standard deviations must be positive.")

        output_spec = manifest.get("output")
        if not isinstance(output_spec, dict):
            raise ModelConfigurationError("Manifest output specification is required.")
        if not isinstance(output_spec.get("name"), str) or not output_spec["name"]:
            raise ModelConfigurationError("Manifest output tensor name is required.")
        if output_spec.get("activation") != "sigmoid":
            raise ModelConfigurationError("Only sigmoid multilabel attribute models are supported.")
        attributes = output_spec.get("attributes")
        if (
            not isinstance(attributes, list)
            or not attributes
            or len(attributes) > 128
            or any(not isinstance(name, str) or not _ATTRIBUTE_RE.fullmatch(name) for name in attributes)
            or len(set(attributes)) != len(attributes)
        ):
            raise ModelConfigurationError("Output attributes must be unique, lowercase identifier strings.")

    @property
    def model_version(self) -> str:
        return self.manifest["model_version"]

    def _preprocess(self, rgb_image: np.ndarray) -> np.ndarray:
        if not isinstance(rgb_image, np.ndarray) or rgb_image.dtype != np.uint8:
            raise ValueError("Image must be a uint8 RGB NumPy array.")
        if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.shape[0] == 0 or rgb_image.shape[1] == 0:
            raise ValueError("Image must have shape (height, width, 3).")
        spec = self.manifest["input"]
        image = Image.fromarray(rgb_image, mode="RGB")
        image = image.resize((spec["width"], spec["height"]), Image.Resampling.BILINEAR)
        tensor = np.asarray(image, dtype=np.float32) / np.float32(255.0)
        mean = np.asarray(spec["mean"], dtype=np.float32).reshape(1, 1, 3)
        std = np.asarray(spec["std"], dtype=np.float32).reshape(1, 1, 3)
        tensor = (tensor - mean) / std
        return np.transpose(tensor, (2, 0, 1))[None, ...].astype(np.float32, copy=False)

    def predict(self, rgb_image: np.ndarray) -> dict[str, Any]:
        tensor = self._preprocess(rgb_image)
        try:
            raw = self.session.run(
                [self.manifest["output"]["name"]],
                {self.manifest["input"]["name"]: tensor},
            )[0]
        except Exception as exc:
            raise RuntimeError("Model inference failed.") from exc

        scores = np.asarray(raw, dtype=np.float64)
        attributes = self.manifest["output"]["attributes"]
        if scores.shape == (1, len(attributes)):
            scores = scores[0]
        if scores.shape != (len(attributes),) or not np.isfinite(scores).all():
            raise RuntimeError("Model output shape or values do not match its manifest.")
        scores = 1.0 / (1.0 + np.exp(-np.clip(scores, -60.0, 60.0)))
        return {
            "model_version": self.model_version,
            "score_semantics": "uncalibrated_model_score_not_a_probability_or_diagnosis",
            "attributes": [
                {"name": name, "score": round(float(score), 6)}
                for name, score in zip(attributes, scores, strict=True)
            ],
        }

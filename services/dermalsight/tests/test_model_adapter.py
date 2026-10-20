from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.model_adapter import ModelConfigurationError, ONNXSkinModel


class NamedTensor:
    def __init__(self, name: str):
        self.name = name


class FakeSession:
    def __init__(self, output: np.ndarray | None = None):
        self.output = np.asarray([[0.0, 2.0]], dtype=np.float32) if output is None else output
        self.last_feed = None

    def get_inputs(self):
        return [NamedTensor("input")]

    def get_outputs(self):
        return [NamedTensor("scores")]

    def run(self, names, feed):
        assert names == ["scores"]
        self.last_feed = feed
        return [self.output]


def build_model(tmp_path: Path, session: FakeSession | None = None):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"fake model for isolated adapter contract test")
    manifest = {
        "schema_version": 1,
        "model_version": "test-1",
        "task": "cosmetic_skin_attributes",
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "input": {
            "name": "input", "width": 64, "height": 64, "layout": "NCHW",
            "mean": [0.5, 0.5, 0.5], "std": [0.25, 0.25, 0.25]
        },
        "output": {
            "name": "scores", "activation": "sigmoid",
            "attributes": ["texture_variation", "visible_color_variation"]
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    factory = lambda _path: session or FakeSession()
    return model_path, manifest_path, factory


def test_model_adapter_preprocesses_rgb_and_returns_sigmoid_scores(tmp_path):
    session = FakeSession()
    model_path, manifest_path, factory = build_model(tmp_path, session)
    adapter = ONNXSkinModel(model_path, manifest_path, session_factory=factory)
    result = adapter.predict(np.full((10, 12, 3), 128, dtype=np.uint8))
    assert result["model_version"] == "test-1"
    assert result["score_semantics"] == "uncalibrated_model_score_not_a_probability_or_diagnosis"
    assert result["attributes"][0]["score"] == 0.5
    assert result["attributes"][1]["score"] == pytest.approx(0.880797, abs=1e-5)
    tensor = session.last_feed["input"]
    assert tensor.shape == (1, 3, 64, 64)
    assert tensor.dtype == np.float32


def test_model_hash_mismatch_fails_closed(tmp_path):
    model_path, manifest_path, factory = build_model(tmp_path)
    model_path.write_bytes(b"tampered model")
    with pytest.raises(ModelConfigurationError, match="SHA-256"):
        ONNXSkinModel(model_path, manifest_path, session_factory=factory)


def test_model_refuses_wrong_task(tmp_path):
    model_path, manifest_path, factory = build_model(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["task"] = "diagnosis"
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(ModelConfigurationError, match="Only cosmetic_skin_attributes"):
        ONNXSkinModel(model_path, manifest_path, session_factory=factory)


def test_model_refuses_output_shape_mismatch(tmp_path):
    model_path, manifest_path, factory = build_model(
        tmp_path, FakeSession(np.array([[0.2]], dtype=np.float32))
    )
    adapter = ONNXSkinModel(model_path, manifest_path, session_factory=factory)
    with pytest.raises(RuntimeError, match="output shape"):
        adapter.predict(np.full((12, 10, 3), 128, dtype=np.uint8))

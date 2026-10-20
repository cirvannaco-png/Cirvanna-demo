from __future__ import annotations

import hashlib
import hmac
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as dermalsight


def test_http_to_onnx_runtime_with_signed_release_gate(tmp_path, monkeypatch):
    """Exercise real HTTP -> consent/auth -> image decode -> ONNX inference.

    The test model and report are synthetic contract fixtures, not evidence of
    skin-analysis accuracy or suitability for production.
    """
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper, numpy_helper

    input_info = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 32, 32])
    output_info = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 2])
    graph = helper.make_graph(
        [
            helper.make_node("GlobalAveragePool", ["input"], ["pooled"]),
            helper.make_node("Flatten", ["pooled"], ["flat"], axis=1),
            helper.make_node("Gemm", ["flat", "weight", "bias"], ["scores"]),
        ],
        "dermalsight-e2e-test-only",
        [input_info],
        [output_info],
        initializer=[
            numpy_helper.from_array(np.asarray([[1.0, -1.0], [0.5, 0.5], [-0.5, 1.0]], dtype=np.float32), name="weight"),
            numpy_helper.from_array(np.asarray([0.0, 0.25], dtype=np.float32), name="bias"),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 13)])
    model.ir_version = 9
    onnx.checker.check_model(model)
    model_path = tmp_path / "synthetic-test-only.onnx"
    onnx.save(model, model_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    version = "synthetic-e2e-only"

    manifest = {
        "schema_version": 1,
        "model_version": version,
        "task": "cosmetic_skin_attributes",
        "model_sha256": digest,
        "input": {"name": "input", "width": 32, "height": 32, "layout": "NCHW", "mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5]},
        "output": {"name": "scores", "activation": "sigmoid", "attributes": ["texture_variation", "visible_color_variation"]},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    signing_key = "test-only-validation-signing-key-at-least-32-bytes"
    group_metrics = {"sample_count": 2, "metrics": {"macro_f1": 0.82}}
    report = {
        "schema_version": 1,
        "report_id": "synthetic-e2e-test-only",
        "decision": "approved",
        "model_version": version,
        "model_sha256": digest,
        "dataset_version": "synthetic-fixture-only",
        "evaluation_sample_count": 6,
        "overall_metrics": {"macro_f1": 0.82},
        "skin_tone_subgroups": {
            "light": group_metrics,
            "medium": group_metrics,
            "deep": group_metrics,
        },
        "release_gates": {
            "license_and_rights_review": True,
            "overall_quality_threshold": True,
            "skin_tone_subgroup_review": True,
            "lighting_and_device_review": True,
            "privacy_and_security_review": True,
            "user_claims_review": True,
        },
    }
    signed_payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    report["signature"] = hmac.new(signing_key.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    report_path = tmp_path / "validation.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "integration-test-token")
    monkeypatch.setenv("DERMALSIGHT_MODEL_PATH", str(model_path))
    monkeypatch.setenv("DERMALSIGHT_MODEL_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("DERMALSIGHT_VALIDATION_REPORT_PATH", str(report_path))
    monkeypatch.setenv("DERMALSIGHT_VALIDATION_SIGNING_KEY", signing_key)
    dermalsight._load_model.cache_clear()

    image_buffer = io.BytesIO()
    Image.new("RGB", (40, 40), color=(128, 128, 128)).save(image_buffer, format="PNG")
    response = TestClient(dermalsight.app).post(
        "/api/v1/analyze",
        headers={"Authorization": "Bearer integration-test-token"},
        data={"consent": "true"},
        files={"image": ("capture.png", image_buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["model_version"] == version
    assert len(payload["attributes"]) == 2
    assert all(0.0 < value["score"] < 1.0 for value in payload["attributes"])
    assert "not a medical diagnosis" in payload["disclaimer"]

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from app.model_adapter import ONNXSkinModel


def test_actual_onnxruntime_inference_on_synthetic_contract_model(tmp_path):
    """Prove real ONNX Runtime wiring; this synthetic graph is not a trained skin model."""
    onnx = pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper, numpy_helper

    input_info = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 32, 32])
    output_info = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 2])
    weights = np.asarray([[1.0, -1.0], [0.5, 0.5], [-0.5, 1.0]], dtype=np.float32)
    bias = np.asarray([0.0, 0.25], dtype=np.float32)
    graph = helper.make_graph(
        [
            helper.make_node("GlobalAveragePool", ["input"], ["pooled"]),
            helper.make_node("Flatten", ["pooled"], ["flat"], axis=1),
            helper.make_node("Gemm", ["flat", "weight", "bias"], ["scores"]),
        ],
        "dermalsight-onnx-contract-smoke-test",
        [input_info],
        [output_info],
        initializer=[
            numpy_helper.from_array(weights, name="weight"),
            numpy_helper.from_array(bias, name="bias"),
        ],
    )
    model = helper.make_model(
        graph,
        producer_name="cirvanna-dermalsight-contract-test",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    model.ir_version = 9
    onnx.checker.check_model(model)
    model_path = tmp_path / "synthetic-contract.onnx"
    onnx.save(model, model_path)

    manifest = {
        "schema_version": 1,
        "model_version": "synthetic-smoke-only",
        "task": "cosmetic_skin_attributes",
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "input": {
            "name": "input",
            "width": 32,
            "height": 32,
            "layout": "NCHW",
            "mean": [0.5, 0.5, 0.5],
            "std": [0.5, 0.5, 0.5],
        },
        "output": {
            "name": "scores",
            "activation": "sigmoid",
            "attributes": ["texture_variation", "visible_color_variation"],
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    adapter = ONNXSkinModel(model_path, manifest_path)
    result = adapter.predict(np.full((40, 40, 3), 128, dtype=np.uint8))

    assert "CPUExecutionProvider" in adapter.session.get_providers()
    assert result["model_version"] == "synthetic-smoke-only"
    assert len(result["attributes"]) == 2
    assert all(0.0 < item["score"] < 1.0 for item in result["attributes"])

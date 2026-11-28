#!/usr/bin/env python3
"""Run a frozen Cirvanna Look It detector on the approved held-out test split."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.model_training.look_it.validate_dataset import validate_dataset, safe_media_path
from tools.model_training.provenance import require_clean_source_revision
from tools.model_training.look_it.train_detector import build_model
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

MODEL_ID = "cirvanna-lookit-fasterrcnn-v0"
ARCHITECTURE = "torchvision-fasterrcnn-resnet50-fpn"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_box(box: Any, width: int, height: int) -> list[float] | None:
    values = [float(value) for value in box]
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ValueError("detector boxes must contain four finite coordinates")
    x1, y1, x2, y2 = values
    x1 = min(max(x1, 0.0), float(width))
    x2 = min(max(x2, 0.0), float(width))
    y1 = min(max(y1, 0.0), float(height))
    y2 = min(max(y2, 0.0), float(height))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1 / width, y1 / height, x2 / width, y2 / height]


def build_prediction_record(
    row: dict[str, Any],
    boxes: list[Any],
    labels: list[Any],
    scores: list[Any],
    categories: list[str],
    score_threshold: float,
) -> dict[str, Any]:
    width, height = int(row["width"]), int(row["height"])
    if len(boxes) != len(labels) or len(boxes) != len(scores):
        raise ValueError("detector boxes, labels and scores must have matching lengths")
    predictions = []
    for index, (box, label, score) in enumerate(zip(boxes, labels, scores)):
        label = int(label)
        score = float(score)
        if not math.isfinite(score):
            raise ValueError("detector confidence scores must be finite")
        if label <= 0 or label >= len(categories):
            continue
        if score < score_threshold:
            continue
        normalized = normalize_box(box, width, height)
        if normalized is None:
            continue
        predictions.append({
            "component_id": f"pred-{index}",
            "category": categories[label],
            "bbox": normalized,
            "confidence": score,
        })
    predictions.sort(key=lambda item: (-item["confidence"], item["component_id"]))
    predictions = predictions[:12]
    ground_truth = []
    for index, component in enumerate(row["components"]):
        item = {
            "component_id": f"gt-{index}",
            "category": str(component["category"]).casefold(),
            "bbox": [float(value) for value in component["bbox"]],
        }
        if isinstance(component.get("product_id"), str) and component["product_id"].strip():
            item["product_id"] = component["product_id"]
        ground_truth.append(item)
    return {
        "sample_id": row["sample_id"],
        "cluster_id": row["cluster_id"],
        "split": "test",
        "subgroups": row["subgroups"],
        "ground_truth_components": ground_truth,
        "predicted_components": predictions,
    }


def run(args) -> dict[str, Any]:
    source_revision = require_clean_source_revision(ROOT)
    dataset = validate_dataset(args.manifest, args.annotations, args.media_root, args.rights_manifest)
    training = json.loads(args.training_report.read_text(encoding="utf-8"))
    if training.get("model_id") != MODEL_ID or training.get("architecture") != ARCHITECTURE:
        raise ValueError("training report does not describe the Cirvanna Look It detector")
    if training.get("source_revision") != source_revision:
        raise ValueError("evaluation checkout must match the exact training source revision")
    if training.get("checkpoint_sha256") != digest(args.checkpoint):
        raise ValueError("detector checkpoint digest does not match the training report")
    trained_dataset = training.get("dataset", {})
    if trained_dataset.get("dataset_manifest_sha256") != digest(args.manifest):
        raise ValueError("training report dataset manifest digest mismatch")
    for key in ("annotations_sha256", "split_manifest_sha256", "rights_manifest_sha256"):
        if trained_dataset.get(key) != dataset.get(key):
            raise ValueError(f"training report dataset provenance mismatch: {key}")
    rows = [
        json.loads(line)
        for line in args.annotations.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    test_rows = [row for row in rows if row["split"] == "test"]
    held_out = training.get("held_out_test", {})
    count = held_out.get("sample_count")
    if (
        held_out.get("status") != "reserved_for_independent_evaluation"
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or count != len(test_rows)
    ):
        raise ValueError("training report does not bind the exact frozen held-out test split")

    try:
        import torch
        from PIL import Image
        from torchvision.transforms.functional import pil_to_tensor
    except ImportError as exc:
        raise RuntimeError("PyTorch, TorchVision and Pillow are required in the approved Look It inference image") from exc

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable; no implicit CPU fallback")
    if not 0.1 <= args.max_gpu_memory_fraction <= 0.95:
        raise ValueError("max GPU memory fraction must be between 0.1 and 0.95")
    device = torch.device(args.device)
    if args.device == "cuda":
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction, device=0)

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    categories = ["background", *dataset["categories"]]
    if not isinstance(checkpoint, dict) or checkpoint.get("categories") != categories:
        raise ValueError("checkpoint category taxonomy does not match the approved dataset")
    if training.get("categories") != categories:
        raise ValueError("training report category taxonomy does not match the approved dataset")
    model = build_model(len(categories))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.to(device).eval()

    output_records = []
    prediction_count = 0
    with torch.inference_mode():
        for row in test_rows:
            image_path = safe_media_path(args.media_root, row["image_path"])
            with Image.open(image_path) as image:
                tensor = pil_to_tensor(image.convert("RGB")).float().div_(255.0)
            if tensor.shape[1] != row["height"] or tensor.shape[2] != row["width"]:
                raise ValueError("held-out image dimensions changed after dataset validation")
            output = model([tensor.to(device)])[0]
            boxes = output["boxes"].detach().float().cpu().tolist()
            labels = output["labels"].detach().long().cpu().tolist()
            scores = output["scores"].detach().float().cpu().tolist()
            record = build_prediction_record(
                row, boxes, labels, scores, categories, args.score_threshold
            )
            record.update({
                "model_id": MODEL_ID,
                "model_checkpoint_sha256": digest(args.checkpoint),
                "training_report_sha256": digest(args.training_report),
                "source_revision": source_revision,
            })
            prediction_count += len(record["predicted_components"])
            output_records.append(record)
            tensor.zero_()
            del output

    return {
        "source_revision": source_revision,
        "checkpoint_sha256": digest(args.checkpoint),
        "training_report_sha256": digest(args.training_report),
        "dataset_manifest_sha256": digest(args.manifest),
        "held_out_sample_count": len(test_rows),
        "prediction_count": prediction_count,
        "records": output_records,
        "status": "held_out_predictions_not_qualified",
        "limitations": [
            "The detector predicts bounding boxes, not pixel masks or garment segmentation.",
            "Predictions require separate blinded evaluation against independently labelled test annotations.",
            "The detector does not retrieve marketplace products or authorize image display.",
            "No production Look It provider is enabled by this evaluation output.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--training-report", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--rights-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--max-gpu-memory-fraction", type=float, default=0.7)
    parser.add_argument("--score-threshold", type=float, default=0.25)
    args = parser.parse_args()
    if not 0.0 <= args.score_threshold <= 1.0:
        raise ValueError("score threshold must be between 0 and 1")
    report = run(args)
    lines = [json.dumps(row, sort_keys=True) for row in report.pop("records")]
    write_private_text(args.output, "\n".join(lines) + "\n")
    print(json.dumps({
        "status": report["status"],
        "held_out_sample_count": report["held_out_sample_count"],
        "prediction_count": report["prediction_count"],
        "output": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Independent held-out evaluation of Cirvanna's own Virtual Try-On model."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.model_training.virtual_try_on.validate_dataset import validate_dataset, safe_path
from tools.model_training.virtual_try_on.model import build_model
from tools.model_training.provenance import require_clean_source_revision
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

MODEL_ID = "cirvanna-tryon-warp-refine-v0"
ARCHITECTURE = "custom-unet-flow-warp-alpha-residual"
METRIC_KEYS = (
    "image_mae",
    "psnr_db",
    "ssim_global",
    "garment_region_mae",
    "alpha_mask_iou",
    "warped_garment_mask_iou",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_image_metrics(
    prediction: np.ndarray,
    target: np.ndarray,
    target_mask: np.ndarray,
    alpha: np.ndarray,
    warped_mask: np.ndarray,
) -> dict[str, float]:
    prediction = np.asarray(prediction, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    target_mask = np.asarray(target_mask, dtype=np.float64)
    alpha = np.asarray(alpha, dtype=np.float64)
    warped_mask = np.asarray(warped_mask, dtype=np.float64)
    if prediction.shape != target.shape or prediction.ndim != 3 or prediction.shape[2] != 3:
        raise ValueError("prediction and target must have identical HxWx3 shapes")
    expected = prediction.shape[:2]
    if any(value.shape != expected for value in (target_mask, alpha, warped_mask)):
        raise ValueError("target mask, alpha and warped mask must match image dimensions")
    if any(not np.isfinite(value).all() for value in (prediction, target, target_mask, alpha, warped_mask)):
        raise ValueError("image and mask arrays must contain only finite values")
    if any(np.min(value) < 0 or np.max(value) > 1 for value in (prediction, target, target_mask, alpha, warped_mask)):
        raise ValueError("image and mask arrays must be normalized to [0,1]")

    difference = prediction - target
    mae = float(np.abs(difference).mean())
    mse = float(np.mean(difference ** 2))
    psnr = 100.0 if mse <= 1e-10 else min(100.0, 10.0 * math.log10(1.0 / mse))

    mu_x = float(prediction.mean())
    mu_y = float(target.mean())
    variance_x = float(prediction.var())
    variance_y = float(target.var())
    covariance = float(np.mean((prediction - mu_x) * (target - mu_y)))
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    denominator = (mu_x ** 2 + mu_y ** 2 + c1) * (variance_x + variance_y + c2)
    ssim = ((2 * mu_x * mu_y + c1) * (2 * covariance + c2)) / denominator if denominator else 1.0

    mask = np.clip(target_mask, 0, 1)
    garment_mae = float((np.abs(difference) * mask[:, :, None]).sum() / max(float(mask.sum()) * 3.0, 1.0))

    def iou(first: np.ndarray, second: np.ndarray) -> float:
        a, b = first >= 0.5, second >= 0.5
        union = int(np.logical_or(a, b).sum())
        intersection = int(np.logical_and(a, b).sum())
        return intersection / union if union else 1.0

    return {
        "image_mae": mae,
        "psnr_db": psnr,
        "ssim_global": float(np.clip(ssim, -1.0, 1.0)),
        "garment_region_mae": garment_mae,
        "alpha_mask_iou": iou(alpha, target_mask),
        "warped_garment_mask_iou": iou(warped_mask, target_mask),
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot aggregate an empty held-out metric set")
    return {key: float(np.mean([row[key] for row in rows])) for key in METRIC_KEYS}


def run(args) -> dict[str, Any]:
    source_revision = require_clean_source_revision(ROOT)
    dataset = validate_dataset(
        args.manifest,
        args.annotations,
        args.media_root,
        args.person_rights_manifest,
        args.garment_rights_manifest,
    )
    manifest_sha = digest(args.manifest)
    training = json.loads(args.training_report.read_text(encoding="utf-8"))
    if training.get("model_id") != MODEL_ID or training.get("architecture") != ARCHITECTURE:
        raise ValueError("training report does not describe the Cirvanna Virtual Try-On candidate")
    if training.get("source_revision") != source_revision:
        raise ValueError("evaluation checkout must match the exact model training source revision")
    if training.get("checkpoint_sha256") != digest(args.checkpoint):
        raise ValueError("checkpoint digest does not match training report")
    trained_dataset = training.get("dataset", {})
    if trained_dataset.get("dataset_manifest_sha256") != manifest_sha:
        raise ValueError("training report dataset manifest digest mismatch")
    for key in (
        "annotations_sha256",
        "split_manifest_sha256",
        "person_rights_manifest_sha256",
        "garment_rights_manifest_sha256",
    ):
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
        raise ValueError("training report does not bind the frozen held-out test split")

    try:
        import torch
        import torch.nn.functional as F
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise RuntimeError("PyTorch is required in the approved Try-On evaluation runtime") from exc
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable; no implicit CPU fallback")
    if not 0.1 <= args.max_gpu_memory_fraction <= 0.8:
        raise ValueError("evaluation GPU memory fraction must be between 0.1 and 0.8")
    device = torch.device(args.device)
    if args.device == "cuda":
        torch.cuda.set_per_process_memory_fraction(args.max_gpu_memory_fraction, device=0)
        torch.cuda.reset_peak_memory_stats(device)

    class HeldOutDataset(Dataset):
        def __init__(self):
            self.rows = test_rows

        def __len__(self):
            return len(self.rows)

        def _image(self, row, role: str, mask: bool = False):
            media = row["media"][role]
            path = safe_path(args.media_root, media["path"])
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != media["sha256"]:
                raise ValueError(f"held-out {role} changed after dataset validation")
            with Image.open(io.BytesIO(raw)) as image:
                image = image.convert("L" if mask else "RGB")
                image = image.resize(
                    (256, 256),
                    Image.Resampling.NEAREST if mask else Image.Resampling.BICUBIC,
                )
                array = np.asarray(image, dtype=np.float32).copy()
            if mask:
                return torch.from_numpy(array).unsqueeze(0) / 255.0
            return torch.from_numpy(array).permute(2, 0, 1) / 127.5 - 1.0

        def __getitem__(self, index):
            row = self.rows[index]
            pose_media = row["media"]["pose_heatmap"]
            pose_path = safe_path(args.media_root, pose_media["path"])
            pose_bytes = pose_path.read_bytes()
            if hashlib.sha256(pose_bytes).hexdigest() != pose_media["sha256"]:
                raise ValueError("held-out pose heatmap changed after dataset validation")
            with np.load(io.BytesIO(pose_bytes), allow_pickle=False) as archive:
                pose_array = np.asarray(archive["heatmaps"], dtype=np.float32).copy()
            pose = torch.from_numpy(pose_array).unsqueeze(0)
            pose = F.interpolate(pose, size=(256, 256), mode="bilinear", align_corners=False).squeeze(0)
            return {
                "person": self._image(row, "person_image"),
                "garment": self._image(row, "garment_image"),
                "person_mask": self._image(row, "person_mask", True),
                "garment_mask": self._image(row, "garment_mask", True),
                "pose": pose,
                "target": self._image(row, "target_image"),
                "target_mask": self._image(row, "target_garment_mask", True),
                "sample_index": index,
            }

    base_channels = training.get("training", {}).get("base_channels")
    if isinstance(base_channels, bool) or not isinstance(base_channels, int) or not 8 <= base_channels <= 64:
        raise ValueError("training report base_channels is invalid")
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
        raise ValueError("checkpoint must contain a safe model state dictionary")
    if checkpoint.get("base_channels") != base_channels:
        raise ValueError("checkpoint base channel count differs from training report")
    if checkpoint.get("architecture") != "cvi-garment-conditioned-warp-refine-unet-v0":
        raise ValueError("checkpoint architecture metadata is not approved")
    model = build_model(base_channels).to(device)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    loader = DataLoader(HeldOutDataset(), batch_size=args.batch_size, shuffle=False, num_workers=0)
    sample_metrics: list[dict[str, Any]] = []
    subgroup_metrics: dict[str, list[dict[str, float]]] = defaultdict(list)
    cluster_ids = set()
    garment_families = set()
    with torch.inference_mode():
        for batch in loader:
            values = {key: value.to(device) for key, value in batch.items() if key != "sample_index"}
            if args.device == "cuda":
                torch.cuda.synchronize(device)
            started = time.perf_counter()
            outputs = model(
                values["person"],
                values["garment"],
                values["person_mask"],
                values["garment_mask"],
                values["pose"],
            )
            if args.device == "cuda":
                torch.cuda.synchronize(device)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            prediction = ((outputs["image"] + 1.0) / 2.0).clamp(0, 1).detach().cpu().numpy()
            target = ((values["target"] + 1.0) / 2.0).clamp(0, 1).detach().cpu().numpy()
            target_mask = values["target_mask"].detach().cpu().numpy()
            alpha = outputs["alpha"].detach().cpu().numpy()
            warped_mask = outputs["warped_garment_mask"].detach().cpu().numpy()
            for index, row_index in enumerate(batch["sample_index"].tolist()):
                row = test_rows[row_index]
                metrics = compute_image_metrics(
                    prediction[index].transpose(1, 2, 0),
                    target[index].transpose(1, 2, 0),
                    target_mask[index, 0],
                    alpha[index, 0],
                    warped_mask[index, 0],
                )
                metrics["inference_latency_ms"] = elapsed_ms / len(batch["sample_index"])
                sample_metrics.append({"sample_id": row["sample_id"], **metrics})
                cluster_ids.add(row["subject_cluster_id"])
                garment_families.add(row["garment_family_id"])
                for key, value in row["subgroups"].items():
                    subgroup_metrics[f"{key}={value}"].append(metrics)
            for value in outputs.values():
                value.zero_()

    overall_rows = [{key: row[key] for key in METRIC_KEYS} for row in sample_metrics]
    overall = aggregate(overall_rows)
    subgroup_report = {
        key: {"sample_count": len(values), "metrics": aggregate(values)}
        for key, values in sorted(subgroup_metrics.items())
    }
    latency = [row["inference_latency_ms"] for row in sample_metrics]
    return {
        "schema_version": "1.0",
        "task": "virtual_try_on_independent_held_out_evaluation",
        "model_id": MODEL_ID,
        "architecture": ARCHITECTURE,
        "source_revision": source_revision,
        "checkpoint_sha256": digest(args.checkpoint),
        "training_report_sha256": digest(args.training_report),
        "dataset_manifest_sha256": manifest_sha,
        "annotations_sha256": dataset["annotations_sha256"],
        "split_manifest_sha256": dataset["split_manifest_sha256"],
        "person_rights_manifest_sha256": dataset["person_rights_manifest_sha256"],
        "garment_rights_manifest_sha256": dataset["garment_rights_manifest_sha256"],
        "sample_count": len(test_rows),
        "subject_cluster_count": len(cluster_ids),
        "garment_family_count": len(garment_families),
        "metrics_macro_sample_mean": overall,
        "latency_ms": {
            "mean": float(np.mean(latency)),
            "p50": float(np.percentile(latency, 50)),
            "p95": float(np.percentile(latency, 95)),
        },
        "subgroups": subgroup_report,
        "runtime": {
            "device": args.device,
            "torch_version": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
            "gpu_total_memory_bytes": torch.cuda.get_device_properties(0).total_memory if args.device == "cuda" else None,
            "peak_gpu_memory_allocated_bytes": torch.cuda.max_memory_allocated(device) if args.device == "cuda" else None,
            "peak_gpu_memory_reserved_bytes": torch.cuda.max_memory_reserved(device) if args.device == "cuda" else None,
        },
        "per_sample": sample_metrics,
        "status": "independent_held_out_evaluation_not_qualified",
        "limitations": [
            "The evaluator uses pixel, garment-region and mask metrics; it does not certify garment identity, logo/pattern preservation, realistic drape, occlusion or human preference.",
            "Global SSIM is a simple full-frame statistic, not a perceptual garment-quality metric.",
            "Subgroup summaries do not yet include cluster-bootstrap confidence intervals or minimum sample-count qualification.",
            "A held-out image-quality score is not anatomical validation or a privacy/deletion assessment.",
            "No user-facing Try-On route or signed model qualification is enabled by this report.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--training-report", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--person-rights-manifest", required=True, type=Path)
    parser.add_argument("--garment-rights-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-gpu-memory-fraction", type=float, default=0.7)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")
    report = run(args)
    write_private_text(args.output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": report["status"],
        "sample_count": report["sample_count"],
        "metrics": report["metrics_macro_sample_mean"],
        "output": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

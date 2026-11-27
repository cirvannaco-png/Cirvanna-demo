#!/usr/bin/env python3
"""Rights-gated, offline evaluation of Look It outfit-component localization."""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest
from tools.model_evaluation.fashion_retrieval.private_artifacts import write_private_text

SCHEMA_VERSION = "1.0"
IOU_THRESHOLD = 0.5

def _box(value: Any, field: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{field} must be [x1,y1,x2,y2]")
    coords = tuple(float(v) for v in value)
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in coords):
        raise ValueError(f"{field} coordinates must be finite and normalized to [0,1]")
    x1, y1, x2, y2 = coords
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"{field} must have positive area")
    return coords

def _components(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError(f"{field} must be a list of at most 12 components")
    result, ids = [], set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        component_id, category = item.get("component_id"), item.get("category")
        if not isinstance(component_id, str) or not component_id.strip() or component_id in ids:
            raise ValueError(f"{field}[{index}] has missing or duplicate component_id")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"{field}[{index}] category is required")
        ids.add(component_id)
        result.append({"component_id": component_id, "category": category.strip().casefold(), "bbox": _box(item.get("bbox"), f"{field}[{index}].bbox")})
    return result

def validate_record(row: Any, line: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"line {line}: record must be an object")
    for key in ("sample_id", "cluster_id", "split"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"line {line}: {key} is required")
    if not isinstance(row.get("subgroups"), dict) or not row["subgroups"]:
        raise ValueError(f"line {line}: non-empty subgroups are required")
    return {**row, "ground_truth_components": _components(row.get("ground_truth_components"), "ground_truth_components"), "predicted_components": _components(row.get("predicted_components"), "predicted_components")}

def box_iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2-x1) * max(0.0, y2-y1)
    area_a, area_b = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0

def match_components(gt: list[dict[str, Any]], pred: list[dict[str, Any]], threshold: float) -> list[tuple[int, int, float]]:
    pairs = []
    for gi, g in enumerate(gt):
        for pi, p in enumerate(pred):
            if g["category"] == p["category"]:
                overlap = box_iou(g["bbox"], p["bbox"])
                if overlap >= threshold:
                    pairs.append((overlap, gi, pi))
    pairs.sort(reverse=True)
    used_gt, used_pred, matches = set(), set(), []
    for overlap, gi, pi in pairs:
        if gi not in used_gt and pi not in used_pred:
            used_gt.add(gi); used_pred.add(pi); matches.append((gi, pi, overlap))
    return matches

def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp/(tp+fp) if tp+fp else 0.0
    recall = tp/(tp+fn) if tp+fn else 0.0
    f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision,6), "recall": round(recall,6), "f1": round(f1,6)}

def evaluate(records: list[dict[str, Any]], threshold: float = IOU_THRESHOLD) -> dict[str, Any]:
    if not 0 < threshold <= 1: raise ValueError("IoU threshold must be in (0,1]")
    if not records: raise ValueError("evaluation dataset is empty")
    if len({row["sample_id"] for row in records}) != len(records): raise ValueError("sample_id values must be unique")
    totals = defaultdict(lambda: [0,0,0])
    subgroup_totals: dict[str, list[int]] = defaultdict(lambda: [0,0,0])
    exact_count, matched_ious = 0, []
    for row in records:
        gt, pred = row["ground_truth_components"], row["predicted_components"]
        matches = match_components(gt, pred, threshold)
        tp, fp, fn = len(matches), len(pred)-len(matches), len(gt)-len(matches)
        totals["all"][0] += tp; totals["all"][1] += fp; totals["all"][2] += fn
        exact_count += int(len(gt) == len(pred))
        matched_ious.extend(m[2] for m in matches)
        categories = {x["category"] for x in gt + pred}
        used_gt, used_pred = {m[0] for m in matches}, {m[1] for m in matches}
        for category in categories:
            cat_tp = sum(gt[gi]["category"] == category for gi, _, _ in matches)
            cat_fp = sum(p["category"] == category for i,p in enumerate(pred) if i not in used_pred)
            cat_fn = sum(g["category"] == category for i,g in enumerate(gt) if i not in used_gt)
            totals[category][0] += cat_tp; totals[category][1] += cat_fp; totals[category][2] += cat_fn
        for key, value in row["subgroups"].items():
            label = f"{key}={value}"
            subgroup_totals[label][0] += tp; subgroup_totals[label][1] += fp; subgroup_totals[label][2] += fn
    class_metrics = {key: _prf(*value) for key,value in sorted(totals.items()) if key != "all"}
    overall = _prf(*totals["all"])
    macro_f1 = sum(v["f1"] for v in class_metrics.values())/len(class_metrics) if class_metrics else 0.0
    return {
        "schema_version": SCHEMA_VERSION, "task": "look_it_component_localization_bbox",
        "iou_threshold": threshold, "sample_count": len(records),
        "independent_cluster_count": len({r["cluster_id"] for r in records}),
        "overall": overall, "macro_f1": round(macro_f1,6),
        "exact_component_count_accuracy": round(exact_count/len(records),6),
        "mean_matched_iou": round(sum(matched_ious)/len(matched_ious),6) if matched_ious else None,
        "per_category": class_metrics,
        "subgroups": {key: _prf(*value) for key,value in sorted(subgroup_totals.items())},
        "limitations": ["Bounding-box localization does not measure pixel-accurate garment segmentation.", "This evaluator does not score product retrieval or image-generation quality.", "A score is scoped to the exact supplied labels, predictions, split and IoU threshold."]
    }

def load_records(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    for line, text in enumerate(raw.decode("utf-8").splitlines(), 1):
        if text.strip():
            try: records.append(validate_record(json.loads(text), line))
            except json.JSONDecodeError as exc: raise ValueError(f"line {line}: invalid JSON") from exc
    return records, digest

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--rights-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--iou-threshold", type=float, default=IOU_THRESHOLD)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    rights = load_and_validate_data_rights_manifest(args.rights_manifest, expected_scope="look_it_decomposition_evaluation")
    records, dataset_sha = load_records(args.input)
    result = evaluate(records, args.iou_threshold)
    result.update({"dataset_sha256": dataset_sha, "rights_manifest_sha256": rights["manifest_sha256"], "rights_evidence_sha256": rights["evidence_sha256"]})
    splits = sorted({r["split"] for r in records})
    if len(splits) != 1: raise ValueError("evaluate exactly one frozen split per run")
    result["split"] = splits[0]
    write_private_text(args.output, json.dumps(result, indent=2, sort_keys=True) + "\n", overwrite=args.overwrite)
    print(json.dumps({"status":"complete","sample_count":result["sample_count"],"dataset_sha256":dataset_sha,"output":str(args.output)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate a rights-cleared, leakage-aware Look It detector dataset."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from typing import Any
from PIL import Image
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.model_evaluation.fashion_retrieval.data_rights import load_and_validate_data_rights_manifest

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
REQUIRED_SPLITS = {"train", "validation", "test"}

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def safe_media_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative.strip() or "\\" in relative:
        raise ValueError("image_path must be a non-empty POSIX relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("image_path traversal is forbidden")
    resolved_root = root.resolve()
    lexical = resolved_root
    for part in candidate.parts:
        lexical = lexical / part
        if lexical.is_symlink():
            raise ValueError("symlink media paths are forbidden")
    resolved = lexical.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ValueError("image_path must resolve to a regular file inside media root")
    if resolved.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds the dataset byte limit")
    return resolved

def validate_sample(row: Any, line: int, categories: set[str]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"line {line}: sample must be an object")
    for key in ("sample_id", "cluster_id", "split", "image_sha256"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"line {line}: {key} is required")
    if row["split"] not in REQUIRED_SPLITS:
        raise ValueError(f"line {line}: split must be train, validation or test")
    if not SHA256.fullmatch(row["image_sha256"]):
        raise ValueError(f"line {line}: image_sha256 must be lowercase SHA-256")
    width, height = row.get("width"), row.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 128:
        raise ValueError(f"line {line}: valid image dimensions of at least 128px are required")
    components = row.get("components")
    if not isinstance(components, list) or len(components) > 12:
        raise ValueError(f"line {line}: components must be a list of at most 12")
    for index, component in enumerate(components):
        if not isinstance(component, dict) or component.get("category") not in categories:
            raise ValueError(f"line {line}: component {index} has an unknown category")
        bbox = component.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"line {line}: component {index} bbox must have four normalized coordinates")
        try:
            x1, y1, x2, y2 = (float(value) for value in bbox)
        except (TypeError, ValueError):
            raise ValueError(f"line {line}: component {index} bbox is invalid")
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError(f"line {line}: component {index} bbox must be normalized and have positive area")
    return row

def split_manifest_digest(samples: list[dict[str, Any]]) -> str:
    rows = sorted(({"sample_id": row["sample_id"], "cluster_id": row["cluster_id"], "split": row["split"]} for row in samples), key=lambda row: row["sample_id"])
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()

def validate_dataset(manifest_path: Path, annotations_path: Path, media_root: Path, rights_path: Path) -> dict[str, Any]:
    rights = load_and_validate_data_rights_manifest(rights_path, expected_scope="look_it_decomposition_evaluation")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("dataset manifest schema_version must be 1.0")
    categories = manifest.get("categories")
    if not isinstance(categories, list) or not categories or len(set(categories)) != len(categories) or "background" in categories:
        raise ValueError("categories must be a unique non-empty list without background")
    if any(not isinstance(category, str) or not category.strip() for category in categories):
        raise ValueError("category names must be non-empty strings")
    raw = annotations_path.read_bytes()
    annotation_digest = hashlib.sha256(raw).hexdigest()
    if manifest.get("annotations_sha256") != annotation_digest:
        raise ValueError("annotation file digest mismatch")
    if manifest.get("rights_manifest_sha256") != rights["manifest_sha256"]:
        raise ValueError("dataset rights manifest digest mismatch")
    samples = []
    for line, value in enumerate(raw.decode("utf-8").splitlines(), 1):
        if value.strip():
            samples.append(validate_sample(json.loads(value), line, set(categories)))
    if not samples or manifest.get("sample_count") != len(samples):
        raise ValueError("dataset sample_count mismatch or dataset empty")
    if len({row["sample_id"] for row in samples}) != len(samples):
        raise ValueError("sample_id values must be unique")
    if {row["split"] for row in samples} != REQUIRED_SPLITS:
        raise ValueError("dataset must contain train, validation and test splits")
    clusters: dict[str, set[str]] = {}
    image_digests: dict[str, set[str]] = {}
    for row in samples:
        clusters.setdefault(row["cluster_id"], set()).add(row["split"])
        image_digests.setdefault(row["image_sha256"], set()).add(row["split"])
        image_path = safe_media_path(media_root, row.get("image_path"))
        if sha256_file(image_path) != row["image_sha256"]:
            raise ValueError(f"image digest mismatch for sample {row['sample_id']}")
        with Image.open(image_path) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError(f"image exceeds the dataset pixel limit for sample {row['sample_id']}")
            image.verify()
            if image.size != (row["width"], row["height"]):
                raise ValueError(f"image dimensions mismatch for sample {row['sample_id']}")
    if any(len(splits) != 1 for splits in clusters.values()):
        raise ValueError("subject/source clusters leak across dataset splits")
    if any(len(splits) != 1 for splits in image_digests.values()):
        raise ValueError("identical image bytes leak across dataset splits")
    split_digest = split_manifest_digest(samples)
    if manifest.get("split_manifest_sha256") != split_digest:
        raise ValueError("split manifest digest mismatch")
    return {
        "dataset_id": manifest.get("dataset_id"),
        "sample_count": len(samples),
        "split_counts": {split: sum(row["split"] == split for row in samples) for split in sorted(REQUIRED_SPLITS)},
        "cluster_count": len(clusters),
        "categories": categories,
        "annotations_sha256": annotation_digest,
        "split_manifest_sha256": split_digest,
        "rights_manifest_sha256": rights["manifest_sha256"],
        "rights_evidence_sha256": rights["evidence_sha256"],
        "status": "validated_for_training_input_only",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--rights-manifest", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_dataset(args.manifest, args.annotations, args.media_root, args.rights_manifest), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

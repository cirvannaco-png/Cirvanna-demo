#!/usr/bin/env python3
"""Validate a rights-cleared, product-family-disjoint Click It image corpus."""
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
    for key in ("sample_id", "product_id", "product_family_id", "split", "image_sha256", "image_path", "category"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"line {line}: {key} is required")
    if row["split"] not in REQUIRED_SPLITS:
        raise ValueError(f"line {line}: split must be train, validation or test")
    if not SHA256.fullmatch(row["image_sha256"]):
        raise ValueError(f"line {line}: image_sha256 must be lowercase SHA-256")
    if row["category"] not in categories:
        raise ValueError(f"line {line}: category is not in the approved taxonomy")
    width, height = row.get("width"), row.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 128:
        raise ValueError(f"line {line}: valid image dimensions of at least 128px are required")
    return row

def split_manifest_digest(samples: list[dict[str, Any]]) -> str:
    rows = sorted(({"sample_id":r["sample_id"],"product_id":r["product_id"],"product_family_id":r["product_family_id"],"split":r["split"]} for r in samples), key=lambda r:r["sample_id"])
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def validate_dataset(manifest_path: Path, annotations_path: Path, media_root: Path, rights_path: Path, min_views_per_product: int = 2) -> dict[str, Any]:
    if min_views_per_product < 2:
        raise ValueError("min_views_per_product must be at least 2")
    rights = load_and_validate_data_rights_manifest(rights_path, expected_scope="click_it_retrieval_evaluation")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest,dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("dataset manifest schema_version must be 1.0")
    categories = manifest.get("categories")
    if not isinstance(categories,list) or not categories or len(set(categories)) != len(categories) or any(not isinstance(c,str) or not c.strip() for c in categories):
        raise ValueError("categories must be a unique non-empty list")
    raw = annotations_path.read_bytes()
    annotations_digest = hashlib.sha256(raw).hexdigest()
    if manifest.get("annotations_sha256") != annotations_digest:
        raise ValueError("annotation file digest mismatch")
    if manifest.get("rights_manifest_sha256") != rights["manifest_sha256"]:
        raise ValueError("dataset rights manifest digest mismatch")
    samples=[]
    for line,value in enumerate(raw.decode("utf-8").splitlines(),1):
        if value.strip():
            samples.append(validate_sample(json.loads(value),line,set(categories)))
    if not samples or manifest.get("sample_count") != len(samples):
        raise ValueError("dataset sample_count mismatch or dataset empty")
    if len({r["sample_id"] for r in samples}) != len(samples):
        raise ValueError("sample_id values must be unique")
    if {r["split"] for r in samples} != REQUIRED_SPLITS:
        raise ValueError("dataset must contain train, validation and test splits")
    families: dict[str,set[str]]={}
    product_families: dict[str,set[str]]={}
    product_splits: dict[str,set[str]]={}
    image_digests: dict[str,set[str]]={}
    image_digest_counts: dict[str,int]={}
    product_counts: dict[tuple[str,str],int]={}
    for row in samples:
        families.setdefault(row["product_family_id"],set()).add(row["split"])
        product_families.setdefault(row["product_id"],set()).add(row["product_family_id"])
        product_splits.setdefault(row["product_id"],set()).add(row["split"])
        image_digests.setdefault(row["image_sha256"],set()).add(row["split"])
        image_digest_counts[row["image_sha256"]]=image_digest_counts.get(row["image_sha256"],0)+1
        key=(row["split"],row["product_id"])
        product_counts[key]=product_counts.get(key,0)+1
        image_path=safe_media_path(media_root,row["image_path"])
        if sha256_file(image_path) != row["image_sha256"]:
            raise ValueError(f"image digest mismatch for sample {row['sample_id']}")
        with Image.open(image_path) as image:
            if image.width*image.height > MAX_IMAGE_PIXELS:
                raise ValueError(f"image exceeds pixel limit for sample {row['sample_id']}")
            image.verify()
            if image.size != (row["width"],row["height"]):
                raise ValueError(f"image dimensions mismatch for sample {row['sample_id']}")
    if any(len(v)!=1 for v in families.values()):
        raise ValueError("product-family clusters leak across dataset splits")
    if any(len(v)!=1 for v in product_families.values()) or any(len(v)!=1 for v in product_splits.values()):
        raise ValueError("product IDs must map to exactly one family and one split")
    if any(len(v)!=1 for v in image_digests.values()):
        raise ValueError("identical image bytes leak across dataset splits")
    if any(count > 1 for count in image_digest_counts.values()):
        raise ValueError("duplicate image bytes must be deduplicated before training")
    if any(count < min_views_per_product for count in product_counts.values()):
        raise ValueError("each product in each split must have enough distinct views")
    split_digest=split_manifest_digest(samples)
    if manifest.get("split_manifest_sha256") != split_digest:
        raise ValueError("split manifest digest mismatch")
    return {
        "dataset_id":manifest.get("dataset_id"),"sample_count":len(samples),
        "split_counts":{s:sum(r["split"]==s for r in samples) for s in sorted(REQUIRED_SPLITS)},
        "product_count_by_split":{s:len({r["product_id"] for r in samples if r["split"]==s}) for s in sorted(REQUIRED_SPLITS)},
        "product_family_count":len(families),"categories":categories,
        "annotations_sha256":annotations_digest,"split_manifest_sha256":split_digest,
        "rights_manifest_sha256":rights["manifest_sha256"],"rights_evidence_sha256":rights["evidence_sha256"],
        "status":"validated_for_training_input_only",
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--annotations",required=True,type=Path)
    parser.add_argument("--media-root",required=True,type=Path)
    parser.add_argument("--rights-manifest",required=True,type=Path)
    parser.add_argument("--min-views-per-product",type=int,default=2)
    args=parser.parse_args()
    print(json.dumps(validate_dataset(args.manifest,args.annotations,args.media_root,args.rights_manifest,args.min_views_per_product),indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

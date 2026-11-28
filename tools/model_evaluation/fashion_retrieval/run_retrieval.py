#!/usr/bin/env python3
"""Generate matched fashion retrieval rankings from immutable Hugging Face snapshots.

The runner never uploads source images. Input media is read from a caller-supplied
local root. The output contains opaque candidate IDs, rankings, scores, and qrels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .private_artifacts import ensure_private_targets_available, write_private_text
except ImportError:  # Support direct execution as documented in the CLI examples.
    from private_artifacts import ensure_private_targets_available, write_private_text

BASELINE_REVISION = "afacf5e5851d5979ab030e228eab60e2c95a912c"
TEXT_QUERY_PREFIX = "A marketplace product matching this description: "
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MODEL_SPECS = {
    "cirvanna-fashion-clip": {
        "repo_id": "patrickjohncyh/fashion-clip",
        "loader": "transformers_clip",
        "default_revision": BASELINE_REVISION,
        "allow_patterns": ["README.md", "model.safetensors", "config.json", "preprocessor_config.json",
                           "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
                           "vocab.json", "merges.txt"],
    },
    "marqo-fashionclip": {
        "repo_id": "Marqo/marqo-fashionCLIP",
        "loader": "open_clip",
        "default_revision": "44f4c655124ed71e90cbf528d82f508d69d8a81b",
        "allow_patterns": ["README.md", "open_clip_config.json", "open_clip_model.safetensors",
                           "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
                           "special_tokens_map.json", "vocab.json", "merges.txt"],
    },
    "marqo-fashionsiglip": {
        "repo_id": "Marqo/marqo-fashionSigLIP",
        "loader": "open_clip",
        "default_revision": "c56244cc94f92419e8369fa71efdaf403b124ce8",
        "allow_patterns": ["README.md", "open_clip_config.json", "open_clip_model.safetensors",
                           "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
                           "special_tokens_map.json", "spiece.model", "config.json"],
    },
    "zooclaw-fashionsiglip2": {
        "repo_id": "srpone/zooclaw-fashionsiglip2",
        "loader": "transformers_auto",
        "default_revision": None,
        "allow_patterns": ["README.md", "LICENSE", "NOTICE", "model.safetensors", "config.json",
                           "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json",
                           "tokenizer.model", "tokenizer_config.json"],
    },
}


def chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    for start in range(0, len(values), size):
        yield values[start:start + size]


def candidate_text_for_embedding(search_text: str) -> str:
    """Match _rank_offers(): use the exact Vision search_text prefix up to 1,000 chars."""
    if not isinstance(search_text, str):
        raise ValueError("candidate search_text must be a string")
    return search_text[:1000]


def build_text_query(query: str) -> str:
    """Match TextSearchRequest.normalized_query and _text_embedding() preprocessing."""
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    clean = " ".join(query.split())[:1000]
    if len(clean) < 3:
        raise ValueError("query must contain at least three non-whitespace characters")
    return (TEXT_QUERY_PREFIX + clean)[:1000]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 3)


def normalize_vector(values: Any) -> list[float]:
    """Convert a tensor/list to a finite unit-length Python vector."""
    if hasattr(values, "detach"):
        values = values.detach().float().cpu().tolist()
    if values and isinstance(values[0], list):
        if len(values) != 1:
            raise ValueError("expected exactly one embedding row")
        values = values[0]
    vector = [float(value) for value in values]
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding is empty or contains non-finite values")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding has a zero or invalid norm")
    return [value / norm for value in vector]


def rank_candidates(
    query_vector: list[float],
    candidate_vectors: dict[str, list[float]],
    *,
    top_k: int | None = None,
) -> tuple[list[str], dict[str, float]]:
    """Rank vectors in one embedding space; scores are cosine similarities only."""
    if not candidate_vectors:
        raise ValueError("candidate_vectors must not be empty")
    query = normalize_vector(query_vector)
    scores: dict[str, float] = {}
    for candidate_id, raw_vector in candidate_vectors.items():
        vector = normalize_vector(raw_vector)
        if len(vector) != len(query):
            raise ValueError(f"embedding dimension mismatch for candidate {candidate_id!r}")
        score = sum(left * right for left, right in zip(query, vector))
        if not math.isfinite(score):
            raise ValueError(f"non-finite similarity for candidate {candidate_id!r}")
        scores[candidate_id] = score
    # Python's stable sort preserves the frozen Commerce offer order for exact score ties,
    # matching _rank_offers(), whose sort key is score only.
    ordered = sorted(scores, key=lambda item: -scores[item])
    if top_k is not None:
        ordered = ordered[:top_k]
    return ordered, scores


def validate_case(row: Any, line_number: int) -> dict[str, Any]:
    prefix = f"line {line_number}"
    if not isinstance(row, dict):
        raise ValueError(f"{prefix}: each input row must be an object")
    required_strings = ("schema_version", "query_id", "cluster_id", "task_id", "split")
    for field in required_strings:
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{prefix}: {field} must be a non-empty string")
    if row["schema_version"] != "1.0":
        raise ValueError(f"{prefix}: schema_version must be 1.0")
    if row["task_id"] not in {"image_to_catalog_text", "text_to_catalog_text", "image_to_catalog_image"}:
        raise ValueError(
            f"{prefix}: supported tasks are image_to_catalog_text, text_to_catalog_text and image_to_catalog_image"
        )
    candidate_ids = row.get("candidate_ids")
    if not isinstance(candidate_ids, list) or not candidate_ids:
        raise ValueError(f"{prefix}: candidate_ids must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in candidate_ids):
        raise ValueError(f"{prefix}: candidate_ids must contain non-empty strings")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"{prefix}: candidate_ids must be unique")
    candidate_texts = row.get("candidate_texts")
    candidate_image_paths = row.get("candidate_image_paths")
    if row["task_id"] == "image_to_catalog_image":
        if not isinstance(candidate_image_paths, dict) or set(candidate_image_paths) != set(candidate_ids):
            raise ValueError(f"{prefix}: candidate_image_paths must map every candidate_id exactly once")
        if any(not isinstance(value, str) or not value.strip() for value in candidate_image_paths.values()):
            raise ValueError(f"{prefix}: candidate_image_paths must contain non-empty relative paths")
        if candidate_texts is not None:
            raise ValueError(f"{prefix}: image-to-image cases must not supply candidate_texts")
    else:
        if not isinstance(candidate_texts, dict) or set(candidate_texts) != set(candidate_ids):
            raise ValueError(f"{prefix}: candidate_texts must map every candidate_id exactly once")
        if any(not isinstance(value, str) or not value.strip() for value in candidate_texts.values()):
            raise ValueError(f"{prefix}: candidate_texts must contain non-empty strings")
    qrels = row.get("qrels")
    if not isinstance(qrels, dict) or set(qrels) != set(candidate_ids):
        raise ValueError(f"{prefix}: qrels must contain an explicit grade for every candidate ID")
    if not any(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in qrels.values()):
        raise ValueError(f"{prefix}: qrels must contain at least one positive relevance grade")
    for candidate_id, grade in qrels.items():
        if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 4:
            raise ValueError(f"{prefix}: qrel for {candidate_id!r} must be an integer from 0 to 4")
    excluded = row.get("excluded_product_ids", [])
    if (not isinstance(excluded, list) or any(not isinstance(x, str) or not x.strip() for x in excluded)
            or len(excluded) != len(set(excluded))):
        raise ValueError(f"{prefix}: excluded_product_ids must be a unique array of IDs")
    if not set(excluded).issubset(set(candidate_ids)):
        raise ValueError(f"{prefix}: excluded_product_ids contains an ID outside candidate_ids")
    human_violations = row.get("human_exclusion_violation_ids", [])
    if (not isinstance(human_violations, list)
            or any(not isinstance(x, str) or not x.strip() for x in human_violations)
            or len(human_violations) != len(set(human_violations))):
        raise ValueError(f"{prefix}: human_exclusion_violation_ids must be a unique array of candidate IDs")
    if not set(human_violations).issubset(set(candidate_ids)):
        raise ValueError(f"{prefix}: human_exclusion_violation_ids contains an ID outside candidate_ids")
    subgroups = row.get("subgroups", {})
    if not isinstance(subgroups, dict):
        raise ValueError(f"{prefix}: subgroups must be an object")
    if row["task_id"] in {"image_to_catalog_text", "image_to_catalog_image"}:
        if not isinstance(row.get("query_image_path"), str) or not row["query_image_path"].strip():
            raise ValueError(f"{prefix}: query_image_path is required for image retrieval tasks")
    if row["task_id"] == "text_to_catalog_text":
        if not isinstance(row.get("query_text"), str) or not row["query_text"].strip():
            raise ValueError(f"{prefix}: query_text is required for text_to_catalog_text")
    return {
        **row,
        "candidate_ids": candidate_ids,
        "candidate_texts": candidate_texts,
        "candidate_image_paths": candidate_image_paths,
        "qrels": qrels,
        "excluded_product_ids": excluded,
        "human_exclusion_violation_ids": human_violations,
        "subgroups": subgroups,
    }


def resolve_media_path(media_root: str | Path, relative_path: str) -> Path:
    root = Path(media_root).expanduser().resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise ValueError("query image path must remain inside --media-root")
    if not path.is_file():
        raise FileNotFoundError(f"query image does not exist: {relative_path}")
    return path


def read_cases(input_path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(input_path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                rows.append(validate_case(json.loads(line), line_number))
    if not rows:
        raise ValueError("input JSONL contains no cases")
    if len({row["query_id"] for row in rows}) != len(rows):
        raise ValueError("query_id values must be unique")
    if len({row["task_id"] for row in rows}) != 1:
        raise ValueError("do not mix retrieval tasks in one model run")
    if len({row["split"] for row in rows}) != 1:
        raise ValueError("do not mix data splits in one model run")
    return rows


def parse_revisions(items: list[str]) -> dict[str, str]:
    revisions = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--revision must use model-id=40-character-commit-sha")
        model_id, revision = item.split("=", 1)
        model_id = model_id.strip()
        revision = revision.strip().lower()
        if model_id not in MODEL_SPECS:
            raise ValueError(f"unknown model ID in --revision: {model_id}")
        if not SHA40.fullmatch(revision):
            raise ValueError(f"{model_id}: revision must be a full 40-character lowercase commit SHA")
        if model_id in revisions:
            raise ValueError(f"duplicate revision for model {model_id}")
        revisions[model_id] = revision
    return revisions


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_privacy_preprocessing_manifest(
    manifest_path: str | Path,
    cases: list[dict[str, Any]],
    media_root: str | Path,
) -> dict[str, Any]:
    """Verify reviewer approval and exact digests for every pre-masked image."""
    path = Path(manifest_path).expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "approval_status", "scope", "reviewed_by", "reviewed_at_utc",
        "evidence_path", "evidence_sha256", "face_masked_before_inference",
        "face_recognition", "detector_model_id", "detector_source_revision",
        "detector_weights_sha256", "images",
    }
    missing = sorted(required - set(value)) if isinstance(value, dict) else sorted(required)
    if missing:
        raise ValueError(f"privacy preprocessing manifest missing fields: {', '.join(missing)}")
    if value["schema_version"] != "1.0" or value["approval_status"] != "approved":
        raise ValueError("privacy preprocessing manifest is not an approved version 1.0 record")
    if value["scope"] != "click_it_image_to_image_benchmark":
        raise ValueError("privacy preprocessing scope must be click_it_image_to_image_benchmark")
    if not isinstance(value["reviewed_by"], str) or not value["reviewed_by"].strip():
        raise ValueError("privacy preprocessing reviewer must be identified")
    try:
        reviewed = datetime.fromisoformat(str(value["reviewed_at_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("privacy preprocessing reviewed_at_utc must be ISO-8601") from exc
    if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
        raise ValueError("privacy preprocessing review timestamp is invalid")
    if value["face_masked_before_inference"] is not True or value["face_recognition"] is not False:
        raise ValueError("image-to-image benchmark requires face masking and prohibits face recognition")
    if not isinstance(value["detector_model_id"], str) or not value["detector_model_id"].strip():
        raise ValueError("privacy preprocessing detector_model_id is required")
    if not isinstance(value["detector_source_revision"], str) or not SHA40.fullmatch(value["detector_source_revision"]):
        raise ValueError("privacy preprocessing detector_source_revision must be a full commit SHA")
    if not isinstance(value["detector_weights_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["detector_weights_sha256"]):
        raise ValueError("privacy preprocessing detector_weights_sha256 must be a full SHA-256 digest")
    evidence_path = Path(str(value["evidence_path"])).expanduser()
    if not evidence_path.is_absolute():
        evidence_path = path.parent / evidence_path
    evidence_path = evidence_path.resolve()
    evidence_digest = value["evidence_sha256"]
    if not isinstance(evidence_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_digest):
        raise ValueError("privacy preprocessing evidence_sha256 must be a full SHA-256 digest")
    if not evidence_path.is_file() or sha256_file(evidence_path) != evidence_digest:
        raise ValueError("privacy preprocessing approval evidence is missing or has a digest mismatch")

    required_images = set()
    for case in cases:
        if case["task_id"] not in {"image_to_catalog_image"}:
            continue
        required_images.add(case["query_image_path"])
        required_images.update(case["candidate_image_paths"].values())
    image_records = value["images"]
    if not isinstance(image_records, dict) or set(image_records) != required_images:
        raise ValueError("privacy preprocessing manifest must cover every query and candidate image exactly once")
    for relative_path in sorted(required_images):
        record = image_records[relative_path]
        if not isinstance(record, dict):
            raise ValueError(f"privacy preprocessing record is invalid for {relative_path}")
        image_path = resolve_media_path(media_root, relative_path)
        expected_digest = record.get("processed_image_sha256")
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise ValueError(f"processed image digest is invalid for {relative_path}")
        if sha256_file(image_path) != expected_digest:
            raise ValueError(f"preprocessed image digest mismatch for {relative_path}")
        masked_count = record.get("faces_masked")
        if isinstance(masked_count, bool) or not isinstance(masked_count, int) or masked_count < 0:
            raise ValueError(f"faces_masked must be a non-negative integer for {relative_path}")
    return {
        "manifest_sha256": sha256_file(path),
        "evidence_sha256": evidence_digest,
        "approval_status": value["approval_status"],
        "scope": value["scope"],
        "face_masked_before_inference": True,
        "face_recognition": False,
        "detector_model_id": value["detector_model_id"],
        "detector_source_revision": value["detector_source_revision"],
        "detector_weights_sha256": value["detector_weights_sha256"],
        "image_count": len(required_images),
    }


def hash_snapshot(snapshot_dir: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(snapshot_dir).resolve()
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            files[relative] = {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if not files:
        raise RuntimeError("model snapshot contains no files")
    return files


def prepare_open_clip_local_dir(snapshot_dir: str | Path, overlay_dir: str | Path) -> tuple[str, dict[str, Any]]:
    """Create a symlink-only local OpenCLIP view and pin tokenizer files to that snapshot."""
    import json
    import os

    snapshot = Path(snapshot_dir).resolve()
    overlay = Path(overlay_dir).resolve()
    overlay.mkdir(parents=True, exist_ok=True)
    config_path = snapshot / "open_clip_config.json"
    if not config_path.is_file():
        raise FileNotFoundError("OpenCLIP snapshot is missing open_clip_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    text_cfg = config.get("model_cfg", {}).get("text_cfg", {})
    external_tokenizer = text_cfg.get("hf_tokenizer_name")
    for source in snapshot.iterdir():
        target = overlay / source.name
        if target.exists() or target.is_symlink():
            target.unlink()
        if source.is_file() and source.name != "open_clip_config.json":
            os.symlink(source.resolve(), target)
    overrides: dict[str, Any] = {}
    if external_tokenizer:
        if not (
            (snapshot / "tokenizer.json").is_file()
            or ((snapshot / "vocab.json").is_file() and (snapshot / "merges.txt").is_file())
            or (snapshot / "spiece.model").is_file()
        ):
            raise FileNotFoundError(
                "model snapshot does not contain tokenizer files needed to avoid a floating tokenizer dependency"
            )
        text_cfg["hf_tokenizer_name"] = str(snapshot)
        overrides["hf_tokenizer_name"] = "local files from the exact model snapshot"
    config_path_overlay = overlay / "open_clip_config.json"
    config_path_overlay.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return "local-dir:" + str(overlay), overrides


def _to_device(batch: dict[str, Any], device: str) -> dict[str, Any]:
    return {key: value.to(device) if hasattr(value, "to") else value for key, value in batch.items()}


@dataclass
class EmbeddingAdapter:
    model: Any
    processor: Any
    device: str
    loader: str
    tokenizer: Any = None
    image_preprocess: Any = None
    processor_overrides: dict[str, Any] | None = None

    @classmethod
    def load(cls, model_id: str, snapshot_dir: str | Path, device: str) -> "EmbeddingAdapter":
        spec = MODEL_SPECS[model_id]
        snapshot = str(Path(snapshot_dir).resolve())
        if spec["loader"] == "open_clip":
            installed_open_clip = importlib.metadata.version("open_clip_torch")
            if installed_open_clip != "4.2.2":
                raise RuntimeError(
                    "Marqo adapters require open_clip_torch==4.2.2 for the pinned local-dir loader; "
                    f"found {installed_open_clip}"
                )
            try:
                import open_clip
            except ImportError as exc:
                raise RuntimeError("install open_clip_torch to run Marqo challengers") from exc
            try:
                with tempfile.TemporaryDirectory(prefix="cirvanna-openclip-") as overlay_path:
                    local_uri, overrides = prepare_open_clip_local_dir(snapshot, overlay_path)
                    model, _, preprocess = open_clip.create_model_and_transforms(local_uri, device=device)
                    tokenizer = open_clip.get_tokenizer(local_uri)
            except Exception as exc:
                raise RuntimeError(
                    "OpenCLIP must load from the pinned local snapshot; remote model code and floating tokenizer downloads are disabled"
                ) from exc
            model.eval()
            return cls(model=model, processor=None, device=device, loader="open_clip",
                       tokenizer=tokenizer, image_preprocess=preprocess,
                       processor_overrides=overrides)

        import torch
        if spec["loader"] == "transformers_clip":
            from transformers import CLIPModel, CLIPProcessor
            model = CLIPModel.from_pretrained(
                snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True
            )
            processor = CLIPProcessor.from_pretrained(
                snapshot, local_files_only=True, trust_remote_code=False
            )
        else:
            from transformers import AutoModel, AutoProcessor
            model = AutoModel.from_pretrained(
                snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True
            )
            processor = AutoProcessor.from_pretrained(
                snapshot, local_files_only=True, trust_remote_code=False
            )
        model.to(device)
        model.eval()
        return cls(model=model, processor=processor, device=device, loader=spec["loader"])

    def encode_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        import torch
        outputs: list[list[float]] = []
        for batch in chunks(texts, batch_size):
            if self.loader == "open_clip":
                tokens = self.tokenizer(batch).to(self.device)
                with torch.inference_mode():
                    features = self.model.encode_text(tokens)
            else:
                options = {
                    "text": batch,
                    "return_tensors": "pt",
                    "padding": True,
                    "truncation": True,
                }
                # Match Cirvanna's current CLIP text path, which truncates at 77 tokens.
                if self.loader == "transformers_clip":
                    options["max_length"] = 77
                inputs = self.processor(**options)
                inputs = _to_device(inputs, self.device)
                with torch.inference_mode():
                    features = self.model.get_text_features(**inputs)
            features = features.detach().float().cpu()
            for row in features:
                outputs.append(normalize_vector(row))
        return outputs

    def encode_images(self, image_paths: list[Path], batch_size: int) -> list[list[float]]:
        import torch
        from PIL import Image
        outputs: list[list[float]] = []
        for path_batch in chunks(image_paths, batch_size):
            images = []
            try:
                for path in path_batch:
                    with Image.open(path) as image:
                        images.append(image.convert("RGB"))
                if self.loader == "open_clip":
                    pixels = torch.stack([self.image_preprocess(image) for image in images]).to(self.device)
                    with torch.inference_mode():
                        features = self.model.encode_image(pixels)
                else:
                    inputs = self.processor(images=images, return_tensors="pt")
                    inputs = _to_device(inputs, self.device)
                    with torch.inference_mode():
                        features = self.model.get_image_features(**inputs)
                features = features.detach().float().cpu()
                for row in features:
                    outputs.append(normalize_vector(row))
            finally:
                for image in images:
                    image.close()
        return outputs


def installed_versions() -> dict[str, str | None]:
    packages = ("torch", "transformers", "huggingface-hub", "open_clip_torch",
                "safetensors", "Pillow")
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def run_model(
    model_id: str,
    revision: str,
    cases: list[dict[str, Any]],
    media_root: str | Path,
    cache_dir: str | Path,
    device: str,
    batch_size: int,
) -> tuple[dict[str, list[str]], dict[str, dict[str, float]], dict[str, Any]]:
    from huggingface_hub import snapshot_download
    import torch

    run_started = time.perf_counter()
    spec = MODEL_SPECS[model_id]
    torch.manual_seed(20261120)
    download_started = time.perf_counter()
    snapshot = snapshot_download(
        repo_id=spec["repo_id"],
        revision=revision,
        cache_dir=str(cache_dir),
        allow_patterns=spec["allow_patterns"],
    )
    snapshot_download_seconds = time.perf_counter() - download_started
    hash_started = time.perf_counter()
    artifact_manifest = hash_snapshot(snapshot)
    artifact_hash_seconds = time.perf_counter() - hash_started
    if device == "cuda" and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    model_load_started = time.perf_counter()
    adapter = EmbeddingAdapter.load(model_id, snapshot, device)
    model_load_seconds = time.perf_counter() - model_load_started
    try:
        candidate_text_vectors: dict[str, list[float]] = {}
        candidate_image_vectors: dict[str, list[float]] = {}
        candidate_text_embedding_seconds = 0.0
        candidate_image_embedding_seconds = 0.0
        task_id = cases[0]["task_id"]
        if task_id == "image_to_catalog_image":
            relative_paths = sorted({
                relative_path
                for case in cases
                for relative_path in case["candidate_image_paths"].values()
            })
            resolved_paths = {
                relative_path: resolve_media_path(media_root, relative_path)
                for relative_path in relative_paths
            }
            candidate_embedding_started = time.perf_counter()
            vectors = adapter.encode_images(list(resolved_paths.values()), batch_size=batch_size)
            if len(vectors) != len(resolved_paths):
                raise RuntimeError("candidate image encoder returned an unexpected number of embeddings")
            candidate_image_vectors.update(zip(resolved_paths.keys(), vectors))
            candidate_image_embedding_seconds = time.perf_counter() - candidate_embedding_started
        else:
            all_texts = sorted({
                candidate_text_for_embedding(str(text))
                for case in cases
                for text in case["candidate_texts"].values()
            })
            candidate_embedding_started = time.perf_counter()
            for batch in chunks(all_texts, batch_size):
                vectors = adapter.encode_texts(batch, batch_size=batch_size)
                if len(vectors) != len(batch):
                    raise RuntimeError("text encoder returned an unexpected number of embeddings")
                candidate_text_vectors.update(zip(batch, vectors))
            candidate_text_embedding_seconds = time.perf_counter() - candidate_embedding_started

        rankings: dict[str, list[str]] = {}
        score_maps: dict[str, dict[str, float]] = {}
        query_latency_ms: list[float] = []
        for case in cases:
            query_started = time.perf_counter()
            if case["task_id"] == "image_to_catalog_image":
                candidate_vectors = {
                    candidate_id: candidate_image_vectors[case["candidate_image_paths"][candidate_id]]
                    for candidate_id in case["candidate_ids"]
                }
                image_path = resolve_media_path(media_root, case["query_image_path"])
                query_vector = adapter.encode_images([image_path], batch_size=1)[0]
            elif case["task_id"] == "image_to_catalog_text":
                candidate_vectors = {
                    candidate_id: candidate_text_vectors[candidate_text_for_embedding(str(case["candidate_texts"][candidate_id]))]
                    for candidate_id in case["candidate_ids"]
                }
                image_path = resolve_media_path(media_root, case["query_image_path"])
                query_vector = adapter.encode_images([image_path], batch_size=1)[0]
            else:
                candidate_vectors = {
                    candidate_id: candidate_text_vectors[candidate_text_for_embedding(str(case["candidate_texts"][candidate_id]))]
                    for candidate_id in case["candidate_ids"]
                }
                query_text = build_text_query(case["query_text"])
                query_vector = adapter.encode_texts([query_text], batch_size=1)[0]
            ordered, scores = rank_candidates(query_vector, candidate_vectors)
            rankings[case["query_id"]] = ordered
            score_maps[case["query_id"]] = {key: round(value, 8) for key, value in scores.items()}
            query_latency_ms.append((time.perf_counter() - query_started) * 1000.0)
        total_run_seconds = time.perf_counter() - run_started
        metadata = {
            "repo_id": spec["repo_id"],
            "revision": revision,
            "loader": spec["loader"],
            "artifact_files": artifact_manifest,
            "processor_overrides": adapter.processor_overrides or {},
            "weight_files": {
                path: item for path, item in artifact_manifest.items()
                if path.endswith((".safetensors", ".bin", ".pt"))
            },
            "embedding_dimension": len(next(iter(candidate_image_vectors.values() if candidate_image_vectors else candidate_text_vectors.values()))),
            "candidate_embedding_mode": "image" if task_id == "image_to_catalog_image" else "text",
            "device": device,
            "timings_seconds": {
                "snapshot_download": round(snapshot_download_seconds, 3),
                "artifact_hashing": round(artifact_hash_seconds, 3),
                "model_load": round(model_load_seconds, 3),
                "candidate_text_embedding": round(candidate_text_embedding_seconds, 3),
                "candidate_image_embedding": round(candidate_image_embedding_seconds, 3),
                "total_run": round(total_run_seconds, 3),
            },
            "query_to_topk_latency_ms": {
                "count": len(query_latency_ms),
                "mean": round(statistics.mean(query_latency_ms), 3) if query_latency_ms else None,
                "p50": _percentile(query_latency_ms, 0.50),
                "p95": _percentile(query_latency_ms, 0.95),
            },
            "cuda_peak_memory_allocated_bytes": (
                int(torch.cuda.max_memory_allocated()) if device == "cuda" and torch.cuda.is_available() else None
            ),
            "cuda_peak_memory_reserved_bytes": (
                int(torch.cuda.max_memory_reserved()) if device == "cuda" and torch.cuda.is_available() else None
            ),
        }
        return rankings, score_maps, metadata
    finally:
        del adapter
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Private JSONL query/candidate cases")
    parser.add_argument("--rights-manifest", required=True, help="Approved private data-rights manifest; inference is blocked without it")
    parser.add_argument("--privacy-preprocessing-manifest", help="Approved face-masking manifest required for image_to_catalog_image")
    parser.add_argument("--media-root", required=True, help="Root directory for query_image_path and candidate_image_paths")
    parser.add_argument("--output", required=True, help="Private output JSONL path")
    parser.add_argument("--overwrite", action="store_true", help="Atomically replace existing rankings and manifest")
    parser.add_argument("--models", nargs="+", required=True, choices=sorted(MODEL_SPECS))
    parser.add_argument("--revision", action="append", default=[],
                        help="Immutable model-id=40-character-commit-sha; repeat for each challenger")
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME", "~/.cache/huggingface"))
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    try:
        from .data_rights import load_and_validate_data_rights_manifest
    except ImportError:
        from data_rights import load_and_validate_data_rights_manifest
    rights = load_and_validate_data_rights_manifest(args.rights_manifest)
    output_path = Path(args.output).expanduser()
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    ensure_private_targets_available([output_path, manifest_path], overwrite=args.overwrite)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    if len(args.models) < 2 or "cirvanna-fashion-clip" not in args.models:
        raise ValueError("--models must include cirvanna-fashion-clip and at least one challenger")
    if len(args.models) != len(set(args.models)):
        raise ValueError("--models must not contain duplicates")
    revisions = parse_revisions(args.revision)
    if "cirvanna-fashion-clip" in revisions and revisions["cirvanna-fashion-clip"] != BASELINE_REVISION:
        raise ValueError("the Cirvanna FashionCLIP baseline revision is frozen to the production-reviewed pin")
    for model_id in args.models:
        revision = revisions.get(model_id) or MODEL_SPECS[model_id]["default_revision"]
        if not revision:
            raise ValueError(f"full immutable --revision {model_id}=<40-char SHA> is required")
        revisions[model_id] = revision

    import torch
    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda requested but CUDA is not available")

    cases = read_cases(args.input)
    media_root = Path(args.media_root).expanduser().resolve()
    privacy_preprocessing = None
    if cases[0]["task_id"] == "image_to_catalog_image":
        if not args.privacy_preprocessing_manifest:
            raise ValueError("--privacy-preprocessing-manifest is required for image_to_catalog_image")
        privacy_preprocessing = validate_privacy_preprocessing_manifest(
            args.privacy_preprocessing_manifest, cases, media_root
        )
    image_digest_manifest = {}
    for case in cases:
        if case["task_id"] in {"image_to_catalog_text", "image_to_catalog_image"}:
            query_path = resolve_media_path(media_root, case["query_image_path"])
            digest_entry: dict[str, Any] = {
                "query": {
                    "sha256": sha256_file(query_path),
                    "size_bytes": query_path.stat().st_size,
                }
            }
            if case["task_id"] == "image_to_catalog_image":
                digest_entry["candidates"] = {}
                for candidate_id, relative_path in case["candidate_image_paths"].items():
                    candidate_path = resolve_media_path(media_root, relative_path)
                    digest_entry["candidates"][candidate_id] = {
                        "sha256": sha256_file(candidate_path),
                        "size_bytes": candidate_path.stat().st_size,
                    }
            image_digest_manifest[case["query_id"]] = digest_entry
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_rankings: dict[str, dict[str, list[str]]] = {}
    model_scores: dict[str, dict[str, dict[str, float]]] = {}
    model_manifest: dict[str, Any] = {}
    for model_id in args.models:
        rankings, scores, metadata = run_model(
            model_id, revisions[model_id], cases, media_root, cache_dir, device, args.batch_size
        )
        model_rankings[model_id] = rankings
        model_scores[model_id] = scores
        model_manifest[model_id] = metadata

    output_records = []
    for case in cases:
        record = {
            "schema_version": "1.0",
            "query_id": case["query_id"],
            "cluster_id": case["cluster_id"],
            "task_id": case["task_id"],
            "split": case["split"],
            "candidate_ids": case["candidate_ids"],
            "qrels": case["qrels"],
            "rankings": {model_id: model_rankings[model_id][case["query_id"]]
                         for model_id in args.models},
            "model_scores": {model_id: model_scores[model_id][case["query_id"]]
                             for model_id in args.models},
            "score_type": "cosine_similarity_not_probability",
            "excluded_product_ids": case["excluded_product_ids"],
            "human_exclusion_violation_ids": case["human_exclusion_violation_ids"],
            "subgroups": case["subgroups"],
        }
        output_records.append(json.dumps(record, sort_keys=True))
    write_private_text(output_path, "".join(record + "\n" for record in output_records), overwrite=args.overwrite)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "cirvanna-fashion-retrieval-runner/1.0",
        "input_sha256": sha256_file(Path(args.input)),
        "data_rights": {
            "manifest_path": str(Path(args.rights_manifest).expanduser().resolve()),
            "manifest_sha256": rights["manifest_sha256"],
            "approval_status": rights["approval_status"],
            "scope": rights["scope"],
            "evidence_sha256": rights["evidence_sha256"],
            "retention_until": rights["retention_until"],
        },
        "query_count": len(cases),
        "task_id": cases[0]["task_id"],
        "split": cases[0]["split"],
        "candidate_pool_sizes": sorted({len(case["candidate_ids"]) for case in cases}),
        "model_revisions": revisions,
        "models": model_manifest,
        "query_image_digests": image_digest_manifest,
        "privacy_preprocessing": privacy_preprocessing,
        "rankings_output_sha256": sha256_file(output_path),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": device,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": torch.cuda.get_device_name(0) if device == "cuda" else None,
            "package_versions": installed_versions(),
            "batch_size": args.batch_size,
        },
        "privacy": {
            "source_images_uploaded": False,
            "source_images_written_to_output": False,
            "source_images_persisted_by_runner": False,
            "input_and_output_must_remain_in_restricted_workspace": True,
        },
        "limitations": [
            "Only image-to-catalog-text and text-to-catalog-text are implemented; image-to-image is a separate task.",
            "The runner ranks all supplied eligible candidates; no calibrated no-match threshold is applied.",
            "Scores are cosine similarities, not probabilities or calibrated confidence.",
            "The runner validates a recorded data-rights approval manifest and evidence digest; it cannot establish legal sufficiency or reviewer independence.",
        ],
    }
    write_private_text(
        manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n", overwrite=args.overwrite
    )
    print(json.dumps({
        "status": "rankings_generated",
        "query_count": len(cases),
        "models": args.models,
        "output": str(output_path),
        "manifest": str(manifest_path),
        "device": device,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"retrieval run failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

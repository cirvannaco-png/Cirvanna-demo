#!/usr/bin/env python3
"""Validate a locked, pre-result registration for the fashion retrieval test."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
TASKS = {"image_to_catalog_text", "text_to_catalog_text", "image_to_catalog_image"}


def validate_registration(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("registration must be a JSON object")

    required = {
        "schema_version", "experiment_id", "status", "registered_at_utc",
        "task_id", "split", "primary_metric", "k",
        "minimum_practically_important_delta", "minimum_query_count",
        "minimum_independent_clusters", "candidate_pool_sizes",
        "bootstrap_samples", "bootstrap_seed", "baseline",
        "challengers", "data_manifest_sha256", "qrels_manifest_sha256",
        "dependency_lock_sha256", "rights_manifest_sha256", "data_manifest_path", "qrels_manifest_path", "dependency_lock_path", "rights_manifest_path",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    if value["schema_version"] != "1.0":
        raise ValueError("schema_version must be 1.0")
    for field in ("experiment_id", "registered_at_utc"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    try:
        registered = datetime.fromisoformat(value["registered_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("registered_at_utc must be an ISO-8601 timestamp") from exc
    if registered.tzinfo is None:
        raise ValueError("registered_at_utc must include a timezone")
    if value["status"] != "locked":
        raise ValueError("status must be 'locked' before final-test evaluation")
    if value["task_id"] not in TASKS:
        raise ValueError(f"task_id must be one of: {', '.join(sorted(TASKS))}")
    if value["task_id"] == "image_to_catalog_image":
        privacy_fields = {"privacy_preprocessing_manifest_sha256", "privacy_preprocessing_manifest_path"}
        missing_privacy = sorted(privacy_fields - set(value))
        if missing_privacy:
            raise ValueError(
                "image_to_catalog_image preregistration requires privacy preprocessing fields: "
                + ", ".join(missing_privacy)
            )
    if value["split"] != "test":
        raise ValueError("final registration split must be 'test'")
    if value["primary_metric"] != "ndcg_at_k":
        raise ValueError("the preregistered primary metric is fixed as ndcg_at_k")
    if isinstance(value["k"], bool) or value["k"] != 10:
        raise ValueError("k must be 10 for the preregistered nDCG@10 primary metric")

    delta = value["minimum_practically_important_delta"]
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not 0 < delta <= 1:
        raise ValueError("minimum_practically_important_delta must be a number in (0, 1]")
    for field, minimum in (("minimum_query_count", 1), ("minimum_independent_clusters", 2),
                           ("bootstrap_samples", 2000)):
        number = value[field]
        if isinstance(number, bool) or not isinstance(number, int) or number < minimum:
            raise ValueError(f"{field} must be an integer >= {minimum}")
    seed = value["bootstrap_seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("bootstrap_seed must be a non-negative integer")

    pools = value["candidate_pool_sizes"]
    if (not isinstance(pools, list) or not pools
            or any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 1000 for x in pools)
            or len(pools) != len(set(pools))):
        raise ValueError("candidate_pool_sizes must be unique integers from 1 to 1000")
    if 1000 not in pools:
        raise ValueError("candidate_pool_sizes must include 1000 to cover the current Vision cap")

    baseline = value["baseline"]
    if not isinstance(baseline, dict) or baseline.get("model_id") != "cirvanna-fashion-clip":
        raise ValueError("baseline.model_id must be cirvanna-fashion-clip")
    if not isinstance(baseline.get("revision"), str) or not SHA40.fullmatch(baseline["revision"]):
        raise ValueError("baseline.revision must be a full 40-character lowercase commit SHA")

    challengers = value["challengers"]
    if not isinstance(challengers, dict) or not challengers:
        raise ValueError("challengers must contain at least one model ID and revision")
    if "cirvanna-fashion-clip" in challengers:
        raise ValueError("baseline must not also appear in challengers")
    for model_id, revision in challengers.items():
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("challenger model IDs must be non-empty strings")
        if not isinstance(revision, str) or not SHA40.fullmatch(revision):
            raise ValueError(f"challenger {model_id!r} revision must be a full 40-character lowercase SHA")

    path_fields = ["data_manifest_path", "qrels_manifest_path", "dependency_lock_path", "rights_manifest_path"]
    digest_fields = ["data_manifest_sha256", "qrels_manifest_sha256", "dependency_lock_sha256", "rights_manifest_sha256"]
    if value["task_id"] == "image_to_catalog_image":
        path_fields.append("privacy_preprocessing_manifest_path")
        digest_fields.append("privacy_preprocessing_manifest_sha256")
    for field in path_fields:
        path = value[field]
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{field} must be a non-empty private file path")

    for field in digest_fields:
        digest = value[field]
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"{field} must be a full lowercase SHA-256 digest")

    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="private preregistration JSON")
    args = parser.parse_args()
    try:
        registration = validate_registration(json.loads(Path(args.input).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"VALID_LOCKED_REGISTRATION {registration['experiment_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

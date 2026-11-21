#!/usr/bin/env python3
"""Join a frozen eligible Catalog/Commerce offer snapshot to approved query/qrel records."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_CATALOG_CANDIDATES = 1000
VALID_TASKS = {"image_to_catalog_text", "text_to_catalog_text"}


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each row must be a JSON object")
            rows.append(value)
    if not rows:
        raise ValueError(f"{path}: input is empty")
    return rows


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    if len(rows) > MAX_CATALOG_CANDIDATES:
        raise ValueError(f"eligible catalog snapshot exceeds the current {MAX_CATALOG_CANDIDATES}-offer bound")
    result: dict[str, str] = {}
    for index, row in enumerate(rows, 1):
        variant_id = row.get("variant_id")
        search_text = row.get("search_text")
        if not isinstance(variant_id, str) or not variant_id.strip() or variant_id != variant_id.strip():
            raise ValueError(f"catalog line {index}: variant_id must be a trimmed, non-empty string")
        if variant_id in result:
            raise ValueError(f"catalog line {index}: duplicate variant_id {variant_id!r}")
        if not isinstance(search_text, str) or not search_text.strip():
            raise ValueError(f"catalog line {index}: search_text must be the exact non-empty Vision offer description")
        # The production _rank_offers path truncates offer search_text to 1,000
        # characters before tokenization. Keep that exact truncation in the runner.
        result[variant_id] = search_text
    return result


def _validate_query(row: dict[str, Any], line: int, catalog_ids: set[str]) -> dict[str, Any]:
    for field in ("schema_version", "query_id", "cluster_id", "task_id", "split"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"query line {line}: {field} must be a non-empty string")
    if row["schema_version"] != "1.0":
        raise ValueError(f"query line {line}: schema_version must be 1.0")
    if row["task_id"] not in VALID_TASKS:
        raise ValueError(f"query line {line}: unsupported task_id {row['task_id']!r}")
    candidate_ids = row.get("candidate_ids")
    if (not isinstance(candidate_ids, list) or not candidate_ids
            or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in candidate_ids)):
        raise ValueError(f"query line {line}: candidate_ids must be a non-empty trimmed string array")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"query line {line}: candidate_ids must be unique")
    unknown = set(candidate_ids) - catalog_ids
    if unknown:
        raise ValueError(f"query line {line}: candidates are not in the frozen eligible offer snapshot: {sorted(unknown)[:5]}")
    qrels = row.get("qrels")
    if not isinstance(qrels, dict) or set(qrels) != set(candidate_ids):
        raise ValueError(f"query line {line}: qrels must contain an explicit grade for every candidate ID")
    if not any(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in qrels.values()):
        raise ValueError(f"query line {line}: at least one positive relevance grade is required")
    for variant_id, grade in qrels.items():
        if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 4:
            raise ValueError(f"query line {line}: qrels[{variant_id!r}] must be an integer from 0 to 4")
    excluded = row.get("excluded_product_ids", [])
    if (not isinstance(excluded, list) or any(not isinstance(x, str) for x in excluded)
            or len(excluded) != len(set(excluded))):
        raise ValueError(f"query line {line}: excluded_product_ids must be a unique string array")
    if not set(excluded).issubset(set(candidate_ids)):
        raise ValueError(f"query line {line}: exclusions must be in candidate_ids")
    subgroups = row.get("subgroups", {})
    if not isinstance(subgroups, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip()
        for k, v in subgroups.items()
    ):
        raise ValueError(f"query line {line}: subgroups must map non-empty strings to strings")
    if row["task_id"] == "image_to_catalog_text":
        if not isinstance(row.get("query_image_path"), str) or not row["query_image_path"].strip():
            raise ValueError(f"query line {line}: query_image_path is required for image task")
    elif row["task_id"] == "text_to_catalog_text":
        if not isinstance(row.get("query_text"), str) or not row["query_text"].strip():
            raise ValueError(f"query line {line}: query_text is required for text task")
    return row


def prepare(catalog_rows: list[dict[str, Any]], query_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = _catalog_map(catalog_rows)
    catalog_positions = {variant_id: index for index, variant_id in enumerate(catalog)}
    result = []
    seen_queries: set[str] = set()
    for line, query in enumerate(query_rows, 1):
        query = _validate_query(query, line, set(catalog))
        positions = [catalog_positions[variant_id] for variant_id in query["candidate_ids"]]
        if positions != sorted(positions):
            raise ValueError(
                f"query line {line}: candidate_ids must preserve their frozen Commerce offer order"
            )
        if query["query_id"] in seen_queries:
            raise ValueError(f"duplicate query_id {query['query_id']!r}")
        seen_queries.add(query["query_id"])
        output = {
            "schema_version": "1.0",
            "query_id": query["query_id"],
            "cluster_id": query["cluster_id"],
            "task_id": query["task_id"],
            "split": query["split"],
            "candidate_ids": query["candidate_ids"],
            "candidate_texts": {variant_id: catalog[variant_id] for variant_id in query["candidate_ids"]},
            "qrels": query["qrels"],
            "excluded_product_ids": query.get("excluded_product_ids", []),
            "subgroups": query.get("subgroups", {}),
        }
        if query["task_id"] == "image_to_catalog_text":
            output["query_image_path"] = query["query_image_path"]
        else:
            output["query_text"] = " ".join(query["query_text"].split())[:1000]
        result.append(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-snapshot", required=True,
                        help="Private JSONL exported from the frozen active Commerce/Catalog candidate set")
    parser.add_argument("--queries", required=True,
                        help="Private query cases containing human-reviewed qrels and relative image paths")
    parser.add_argument("--output", required=True, help="Private runner-input JSONL")
    args = parser.parse_args()
    catalog_rows = _read_jsonl(args.catalog_snapshot)
    query_rows = _read_jsonl(args.queries)
    cases = prepare(catalog_rows, query_rows)
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, sort_keys=True) + "\\n")
    split_counts = dict(Counter(case["split"] for case in cases))
    tasks = sorted({case["task_id"] for case in cases})
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_snapshot_sha256": _sha256(args.catalog_snapshot),
        "query_cases_sha256": _sha256(args.queries),
        "output_sha256": _sha256(output),
        "catalog_candidate_count": len(catalog_rows),
        "query_count": len(cases),
        "queries_by_split": split_counts,
        "task_ids": tasks,
        "candidate_pool_sizes": sorted({len(case["candidate_ids"]) for case in cases}),
        "human_qrels_required": True,
        "source_images_uploaded": False,
        "source_images_written": False,
        "privacy_note": "Keep the input, output, source paths, and manifest in an approved restricted evaluation workspace.",
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    print(json.dumps({"status": "prepared", "catalog_candidates": len(catalog_rows),
                      "queries": len(cases), "splits": split_counts, "manifest": str(manifest_path)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"dataset preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

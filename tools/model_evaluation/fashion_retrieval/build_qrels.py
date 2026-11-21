#!/usr/bin/env python3
"""Aggregate blinded two-reviewer judgments into complete, adjudicated retrieval qrels."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
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
                raise ValueError(f"{path}:{line_number}: each row must be an object")
            rows.append(value)
    if not rows:
        raise ValueError(f"{path}: input is empty")
    return rows


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_queries(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    queries = {}
    for line, row in enumerate(rows, 1):
        query_id = row.get("query_id")
        candidates = row.get("candidate_ids")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError(f"query line {line}: query_id must be non-empty")
        if query_id in queries:
            raise ValueError(f"query line {line}: duplicate query_id {query_id!r}")
        if (not isinstance(candidates, list) or not candidates
                or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in candidates)):
            raise ValueError(f"query line {line}: candidate_ids must be non-empty trimmed strings")
        if len(candidates) != len(set(candidates)):
            raise ValueError(f"query line {line}: candidate_ids must be unique")
        queries[query_id] = row
    return queries


def _validate_label(row: dict[str, Any], *, field: str, line: int) -> tuple[str, str, str, int, bool]:
    query_id = row.get("query_id")
    candidate_id = row.get("candidate_id")
    actor_key = row.get(field)
    relevance = row.get("relevance")
    violation = row.get("exclusion_violation")
    if not isinstance(query_id, str) or not query_id.strip():
        raise ValueError(f"{field} line {line}: query_id must be non-empty")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError(f"{field} line {line}: candidate_id must be non-empty")
    if not isinstance(actor_key, str) or not actor_key.strip():
        raise ValueError(f"{field} line {line}: {field} must be a pseudonymous non-empty key")
    if isinstance(relevance, bool) or not isinstance(relevance, int) or not 0 <= relevance <= 4:
        raise ValueError(f"{field} line {line}: relevance must be an integer from 0 to 4")
    if not isinstance(violation, bool):
        raise ValueError(f"{field} line {line}: exclusion_violation must be boolean")
    return query_id, candidate_id, actor_key, relevance, violation


def aggregate(
    query_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    adjudication_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = _validate_queries(query_rows)
    reviews_by_pair: dict[tuple[str, str], list[tuple[str, int, bool]]] = defaultdict(list)
    reviewer_keys: set[str] = set()
    for line, row in enumerate(review_rows, 1):
        query_id, candidate_id, reviewer, relevance, violation = _validate_label(
            row, field="reviewer_key", line=line
        )
        if query_id not in queries:
            raise ValueError(f"review line {line}: unknown query_id {query_id!r}")
        if candidate_id not in queries[query_id]["candidate_ids"]:
            raise ValueError(f"review line {line}: candidate is not in query candidate_ids")
        reviews_by_pair[(query_id, candidate_id)].append((reviewer, relevance, violation))
        reviewer_keys.add(reviewer)

    adjudications: dict[tuple[str, str], tuple[str, int, bool]] = {}
    for line, row in enumerate(adjudication_rows, 1):
        query_id, candidate_id, adjudicator, relevance, violation = _validate_label(
            row, field="adjudicator_key", line=line
        )
        if query_id not in queries:
            raise ValueError(f"adjudication line {line}: unknown query_id {query_id!r}")
        if candidate_id not in queries[query_id]["candidate_ids"]:
            raise ValueError(f"adjudication line {line}: candidate is not in query candidate_ids")
        key = (query_id, candidate_id)
        if key in adjudications:
            raise ValueError(f"adjudication line {line}: duplicate adjudication for {key!r}")
        adjudications[key] = (adjudicator, relevance, violation)

    output = []
    exact_agreement = []
    relevance_agreement = []
    exclusion_agreement = []
    adjudicated_count = 0
    for query_id, query in queries.items():
        qrels: dict[str, int] = {}
        human_violations = []
        for candidate_id in query["candidate_ids"]:
            key = (query_id, candidate_id)
            pair_reviews = reviews_by_pair.get(key, [])
            reviewer_ids = [item[0] for item in pair_reviews]
            if len(pair_reviews) != 2 or len(set(reviewer_ids)) != 2:
                raise ValueError(
                    f"{query_id}/{candidate_id}: exactly two distinct independent reviewer records are required"
                )
            first, second = pair_reviews
            relevance_agreement.append(1.0 if first[1] == second[1] else 0.0)
            exclusion_agreement.append(1.0 if first[2] == second[2] else 0.0)
            agrees = (first[1], first[2]) == (second[1], second[2])
            exact_agreement.append(1.0 if agrees else 0.0)
            adjudication = adjudications.get(key)
            if agrees:
                if adjudication is not None:
                    raise ValueError(f"{query_id}/{candidate_id}: unnecessary adjudication supplied despite agreement")
                relevance, violation = first[1], first[2]
            else:
                if adjudication is None:
                    raise ValueError(f"{query_id}/{candidate_id}: reviewer disagreement requires adjudication")
                adjudicator, relevance, violation = adjudication
                if adjudicator in reviewer_ids:
                    raise ValueError(f"{query_id}/{candidate_id}: adjudicator must be independent of both reviewers")
                adjudicated_count += 1
            qrels[candidate_id] = relevance
            if violation:
                human_violations.append(candidate_id)

        # Emit only the approved benchmark schema. Never copy unknown input
        # fields into the runner dataset (they may contain names, account IDs,
        # reviewer notes, or other unintended personal data).
        output_row = {
            "schema_version": query["schema_version"],
            "query_id": query_id,
            "cluster_id": query["cluster_id"],
            "task_id": query["task_id"],
            "split": query["split"],
            "candidate_ids": list(query["candidate_ids"]),
            "excluded_product_ids": list(query.get("excluded_product_ids", [])),
            "subgroups": dict(query.get("subgroups", {})),
            "qrels": qrels,
            "human_exclusion_violation_ids": human_violations,
        }
        if query["task_id"] == "image_to_catalog_text":
            image_path = query.get("query_image_path")
            if not isinstance(image_path, str) or not image_path.strip() or Path(image_path).is_absolute():
                raise ValueError(f"{query_id}: query_image_path must be a relative path under the media root")
            output_row["query_image_path"] = image_path
        elif query["task_id"] == "text_to_catalog_text":
            query_text = query.get("query_text")
            if not isinstance(query_text, str) or not query_text.strip():
                raise ValueError(f"{query_id}: text query must be non-empty")
            output_row["query_text"] = " ".join(query_text.split())[:1000]
        else:
            raise ValueError(f"{query_id}: unsupported query task {query['task_id']!r}")
        output.append(output_row)

    extra_review_keys = set(reviews_by_pair) - {
        (query_id, candidate_id)
        for query_id, query in queries.items()
        for candidate_id in query["candidate_ids"]
    }
    if extra_review_keys:
        raise ValueError(f"reviews contain rows outside the frozen query candidate pools: {sorted(extra_review_keys)[:5]}")
    extra_adjudication_keys = set(adjudications) - set(reviews_by_pair)
    if extra_adjudication_keys:
        raise ValueError(f"adjudications contain unknown review pairs: {sorted(extra_adjudication_keys)[:5]}")

    summary = {
        "query_count": len(queries),
        "candidate_review_pair_count": sum(len(query["candidate_ids"]) for query in queries.values()),
        "review_record_count": len(review_rows),
        "distinct_reviewer_count": len(reviewer_keys),
        "adjudicated_pair_count": adjudicated_count,
        "exact_reviewer_agreement_rate": round(statistics.mean(exact_agreement), 6) if exact_agreement else None,
        "relevance_agreement_rate": round(statistics.mean(relevance_agreement), 6) if relevance_agreement else None,
        "exclusion_agreement_rate": round(statistics.mean(exclusion_agreement), 6) if exclusion_agreement else None,
        "human_exclusion_violation_count": sum(len(row["human_exclusion_violation_ids"]) for row in output),
    }
    return output, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", required=True, help="Private frozen query-case JSONL")
    parser.add_argument("--reviews", required=True, help="Private blinded two-reviewer judgments JSONL")
    parser.add_argument("--adjudications", help="Private independent adjudications JSONL; omit if none")
    parser.add_argument("--output", required=True, help="Private query/qrel output for prepare_cases.py")
    args = parser.parse_args()
    query_rows = read_jsonl(args.queries)
    review_rows = read_jsonl(args.reviews)
    adjudications = read_jsonl(args.adjudications) if args.adjudications else []
    output_rows, summary = aggregate(query_rows, review_rows, adjudications)
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "queries_sha256": sha256_file(args.queries),
        "reviews_sha256": sha256_file(args.reviews),
        "adjudications_sha256": sha256_file(args.adjudications) if args.adjudications else None,
        "output_sha256": sha256_file(out),
        "summary": summary,
        "reviewer_keys_written_to_output": False,
        "raw_reviews_written_to_output": False,
        "human_review_required": True,
        "privacy_note": "Keep source query/review/adjudication files, output and manifest in the restricted evaluation workspace.",
    }
    out.with_suffix(out.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "qrels_built", **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"qrel aggregation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

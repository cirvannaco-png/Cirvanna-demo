#!/usr/bin/env python3
"""Evaluate PNELLY outfit rankings against a transparent, non-ML baseline.

Input is human-reviewed JSONL: one row per candidate outfit per recommendation
session. The evaluator intentionally refuses incomplete or unreviewed rows.
It does not generate labels or infer user preferences.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUIRED = {
    "session_id", "user_pseudonym", "outfit_id", "algorithm_rank",
    "human_relevance", "hard_exclusion_violation", "edited", "rejected",
    "occasion_match", "preference_match_count", "garment_categories",
    "style_tags", "human_reviewed", "reviewer_id",
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        missing = REQUIRED - row.keys()
        if missing:
            raise ValueError(f"{path}:{line_no}: missing fields: {', '.join(sorted(missing))}")
        if row["human_reviewed"] is not True or not str(row["reviewer_id"]).strip():
            raise ValueError(f"{path}:{line_no}: every row must be independently human-reviewed")
        if not isinstance(row["human_relevance"], int) or not 1 <= row["human_relevance"] <= 5:
            raise ValueError(f"{path}:{line_no}: human_relevance must be an integer from 1 to 5")
        if not isinstance(row["algorithm_rank"], int) or row["algorithm_rank"] < 1:
            raise ValueError(f"{path}:{line_no}: algorithm_rank must be a positive integer")
        if not isinstance(row["preference_match_count"], int) or row["preference_match_count"] < 0:
            raise ValueError(f"{path}:{line_no}: preference_match_count must be non-negative")
        for field in ("hard_exclusion_violation", "edited", "rejected", "occasion_match"):
            if not isinstance(row[field], bool):
                raise ValueError(f"{path}:{line_no}: {field} must be boolean")
        for field in ("garment_categories", "style_tags"):
            if not isinstance(row[field], list) or not all(isinstance(x, str) for x in row[field]):
                raise ValueError(f"{path}:{line_no}: {field} must be a list of strings")
        rows.append(row)
    if not rows:
        raise ValueError("No human-reviewed rows found; refusing to report benchmark metrics.")
    return rows


def baseline_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    """Transparent baseline: occasion match, then declared preference overlap."""
    return (
        0 if row["occasion_match"] else 1,
        -row["preference_match_count"],
        1 if row["hard_exclusion_violation"] else 0,
        str(row["outfit_id"]),
    )


def ordered(group: list[dict[str, Any]], rank_field: str) -> list[dict[str, Any]]:
    if rank_field == "baseline_rank":
        return sorted(group, key=baseline_key)
    return sorted(group, key=lambda row: (row[rank_field], str(row["outfit_id"])))


def diversity_at_k(rows: list[dict[str, Any]], k: int) -> float:
    selected = rows[:k]
    if len(selected) < 2:
        return 0.0
    categories = [set(r["garment_categories"]) for r in selected]
    tags = [set(r["style_tags"]) for r in selected]
    distances: list[float] = []
    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            left, right = categories[i] | tags[i], categories[j] | tags[j]
            union = left | right
            similarity = len(left & right) / len(union) if union else 1.0
            distances.append(1.0 - similarity)
    return statistics.mean(distances) if distances else 0.0


def summarize(rows: list[dict[str, Any]], rank_field: str, k: int) -> dict[str, float | int]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sessions[str(row["session_id"])].append(row)
    relevance, diversity, exclusion, edits, rejects = [], [], [], [], []
    for group in sessions.values():
        ranked = ordered(group, rank_field)
        top = ranked[:k]
        if not top:
            continue
        relevance.append(statistics.mean(r["human_relevance"] for r in top))
        diversity.append(diversity_at_k(ranked, k))
        exclusion.append(sum(bool(r["hard_exclusion_violation"]) for r in top) / len(top))
        edits.append(sum(bool(r["edited"]) for r in top) / len(top))
        rejects.append(sum(bool(r["rejected"]) for r in top) / len(top))
    by_user_outfit: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row["rejected"]:
            by_user_outfit[(str(row["user_pseudonym"]), str(row["outfit_id"]))] += 1
    repeated = sum(count >= 2 for count in by_user_outfit.values())
    unique_rejected = len(by_user_outfit)
    return {
        "sessions": len(sessions),
        "candidate_rows": len(rows),
        "mean_human_relevance_at_k": round(statistics.mean(relevance), 4),
        "mean_diversity_at_k": round(statistics.mean(diversity), 4),
        "hard_exclusion_violation_rate_at_k": round(statistics.mean(exclusion), 4),
        "user_edit_rate_at_k": round(statistics.mean(edits), 4),
        "user_rejection_rate_at_k": round(statistics.mean(rejects), 4),
        "repeated_rejection_rate": round(repeated / unique_rejected, 4) if unique_rejected else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="Human-reviewed JSONL dataset")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be >= 1")
    rows = load_rows(args.dataset)
    report = {
        "protocol": "pnelly-outfit-evaluation-v1",
        "k": args.k,
        "algorithm": summarize(rows, "algorithm_rank", args.k),
        "simple_baseline": summarize(rows, "baseline_rank", args.k),
        "interpretation": {
            "higher_is_better": ["mean_human_relevance_at_k", "mean_diversity_at_k"],
            "lower_is_better": ["hard_exclusion_violation_rate_at_k", "user_edit_rate_at_k", "user_rejection_rate_at_k", "repeated_rejection_rate"],
            "hard_gate": "Any hard-exclusion violation is a release-blocking safety failure, regardless of average score.",
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

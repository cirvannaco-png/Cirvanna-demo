#!/usr/bin/env python3
"""Evaluate PNELLY rankings against a transparent, safety-first baseline.

Input is adjudicated human-reviewed JSONL: one row per candidate outfit per
recommendation session. The evaluator refuses incomplete, duplicated, or
single-reviewer labels and never fabricates benchmark data.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUIRED = {
    "session_id", "user_pseudonym", "outfit_id", "algorithm_rank",
    "human_relevance", "hard_exclusion_violation", "edited", "rejected",
    "occasion_match", "preference_match_count", "garment_categories",
    "style_tags", "human_reviewed", "reviewer_ids", "review_rubric_version",
}
METRICS = (
    "mean_human_relevance_at_k",
    "mean_diversity_at_k",
    "hard_exclusion_violation_rate_at_k",
    "user_edit_rate_at_k",
    "user_rejection_rate_at_k",
)
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261107


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    session_users: dict[str, str] = {}
    session_ranks: set[tuple[str, int]] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: each JSONL record must be an object")
        missing = REQUIRED - row.keys()
        if missing:
            raise ValueError(f"{path}:{line_no}: missing fields: {', '.join(sorted(missing))}")
        if row["human_reviewed"] is not True:
            raise ValueError(f"{path}:{line_no}: every row must be human-reviewed")
        reviewers = row["reviewer_ids"]
        if (
            not isinstance(reviewers, list)
            or len(reviewers) < 2
            or any(not isinstance(x, str) or not x.strip() for x in reviewers)
            or len(set(reviewers)) != len(reviewers)
        ):
            raise ValueError(f"{path}:{line_no}: reviewer_ids must contain at least two distinct reviewers")
        if not isinstance(row["review_rubric_version"], str) or not row["review_rubric_version"].strip():
            raise ValueError(f"{path}:{line_no}: review_rubric_version must be non-empty")
        if not isinstance(row["human_relevance"], int) or isinstance(row["human_relevance"], bool) or not 1 <= row["human_relevance"] <= 5:
            raise ValueError(f"{path}:{line_no}: adjudicated human_relevance must be an integer from 1 to 5")
        if not isinstance(row["algorithm_rank"], int) or isinstance(row["algorithm_rank"], bool) or row["algorithm_rank"] < 1:
            raise ValueError(f"{path}:{line_no}: algorithm_rank must be a positive integer")
        if not isinstance(row["preference_match_count"], int) or isinstance(row["preference_match_count"], bool) or row["preference_match_count"] < 0:
            raise ValueError(f"{path}:{line_no}: preference_match_count must be non-negative")
        for field in ("hard_exclusion_violation", "edited", "rejected", "occasion_match"):
            if not isinstance(row[field], bool):
                raise ValueError(f"{path}:{line_no}: {field} must be boolean")
        for field in ("session_id", "user_pseudonym", "outfit_id"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"{path}:{line_no}: {field} must be a non-empty string")
        for field in ("garment_categories", "style_tags"):
            if not isinstance(row[field], list) or not all(isinstance(x, str) and x.strip() for x in row[field]):
                raise ValueError(f"{path}:{line_no}: {field} must be a list of non-empty strings")
        session = row["session_id"]
        pair = (session, row["outfit_id"])
        if pair in seen:
            raise ValueError(f"{path}:{line_no}: duplicate outfit within session: {pair}")
        seen.add(pair)
        previous_user = session_users.setdefault(session, row["user_pseudonym"])
        if previous_user != row["user_pseudonym"]:
            raise ValueError(f"{path}:{line_no}: a session cannot map to multiple user pseudonyms")
        rank_key = (session, row["algorithm_rank"])
        if rank_key in session_ranks:
            raise ValueError(f"{path}:{line_no}: duplicate algorithm_rank within session")
        session_ranks.add(rank_key)
        rows.append(row)
    if not rows:
        raise ValueError("No human-reviewed rows found; refusing to report benchmark metrics.")
    return rows


def baseline_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    """Safety-first baseline: exclude unsafe looks before occasion and preference."""
    return (
        1 if row["hard_exclusion_violation"] else 0,
        0 if row["occasion_match"] else 1,
        -row["preference_match_count"],
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
    features = [set(r["garment_categories"]) | set(r["style_tags"]) for r in selected]
    distances: list[float] = []
    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            union = features[i] | features[j]
            similarity = len(features[i] & features[j]) / len(union) if union else 1.0
            distances.append(1.0 - similarity)
    return statistics.mean(distances)


def session_metrics(rows: list[dict[str, Any]], rank_field: str, k: int) -> dict[str, dict[str, float]]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sessions[str(row["session_id"])].append(row)
    output: dict[str, dict[str, float]] = {}
    for session_id, group in sessions.items():
        ranked = ordered(group, rank_field)
        top = ranked[:k]
        if not top:
            continue
        output[session_id] = {
            "mean_human_relevance_at_k": statistics.mean(r["human_relevance"] for r in top),
            "mean_diversity_at_k": diversity_at_k(ranked, k),
            "hard_exclusion_violation_rate_at_k": sum(r["hard_exclusion_violation"] for r in top) / len(top),
            "user_edit_rate_at_k": sum(r["edited"] for r in top) / len(top),
            "user_rejection_rate_at_k": sum(r["rejected"] for r in top) / len(top),
        }
    return output


def _bootstrap_interval(values: list[float], rng: random.Random) -> list[float]:
    if len(values) < 2:
        return [round(values[0], 4), round(values[0], 4)]
    samples = sorted(
        statistics.mean(rng.choice(values) for _ in values)
        for _ in range(BOOTSTRAP_SAMPLES)
    )
    low = samples[int(0.025 * (BOOTSTRAP_SAMPLES - 1))]
    high = samples[int(0.975 * (BOOTSTRAP_SAMPLES - 1))]
    return [round(low, 4), round(high, 4)]


def summarize(metrics_by_session: dict[str, dict[str, float]], rows: list[dict[str, Any]], k: int, seed_offset: int = 0) -> dict[str, Any]:
    rng = random.Random(BOOTSTRAP_SEED + seed_offset)
    metrics: dict[str, float] = {}
    intervals: dict[str, list[float]] = {}
    for name in METRICS:
        values = [session[name] for session in metrics_by_session.values()]
        metrics[name] = round(statistics.mean(values), 4)
        intervals[name] = _bootstrap_interval(values, rng)
    rejected_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row["rejected"]:
            rejected_sessions[(str(row["user_pseudonym"]), str(row["outfit_id"]))].add(str(row["session_id"]))
    repeated = sum(len(sessions) >= 2 for sessions in rejected_sessions.values())
    unique_rejected = len(rejected_sessions)
    metrics["repeated_rejection_rate"] = round(repeated / unique_rejected, 4) if unique_rejected else 0.0
    return {
        "sessions": len(metrics_by_session),
        "candidate_rows": len(rows),
        "metrics": metrics,
        "confidence_intervals_95": intervals,
        "repeated_rejection_pairs": unique_rejected,
        "repeated_rejection_pairs_in_multiple_sessions": repeated,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="Adjudicated human-reviewed JSONL dataset")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be >= 1")
    rows = load_rows(args.dataset)
    algorithm_sessions = session_metrics(rows, "algorithm_rank", args.k)
    baseline_sessions = session_metrics(rows, "baseline_rank", args.k)
    if set(algorithm_sessions) != set(baseline_sessions):
        raise ValueError("Algorithm and baseline must be evaluated on identical sessions")
    paired_delta: dict[str, list[float]] = {}
    rng = random.Random(BOOTSTRAP_SEED + 99)
    for name in METRICS:
        values = [algorithm_sessions[s][name] - baseline_sessions[s][name] for s in sorted(algorithm_sessions)]
        paired_delta[name] = _bootstrap_interval(values, rng)
    report = {
        "protocol": "pnelly-outfit-evaluation-v2",
        "k": args.k,
        "algorithm": summarize(algorithm_sessions, rows, args.k, 1),
        "simple_baseline": summarize(baseline_sessions, rows, args.k, 2),
        "paired_algorithm_minus_baseline_ci_95": paired_delta,
        "interpretation": {
            "higher_is_better": ["mean_human_relevance_at_k", "mean_diversity_at_k"],
            "lower_is_better": ["hard_exclusion_violation_rate_at_k", "user_edit_rate_at_k", "user_rejection_rate_at_k", "repeated_rejection_rate"],
            "hard_gate": "Any hard-exclusion violation in the algorithm top-K is a release-blocking safety failure, regardless of average score.",
            "confidence_intervals": "Percentile bootstrap over sessions; descriptive only when sample size is small.",
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

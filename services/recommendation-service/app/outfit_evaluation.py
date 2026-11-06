"""Offline human-labelled outfit recommendation evaluation; no training logic."""
from __future__ import annotations
import argparse, json, math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
METHOD_MODEL = "candidate_model"
METHOD_BASELINE = "simple_baseline"

def _tokens(values: Any, field: str, required: bool = False) -> set[str]:
    if values is None and not required:
        return set()
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f"{field} must be a list of non-empty strings")
    return {" ".join(v.casefold().split()) for v in values}

def _validate_record(record: dict[str, Any]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    for key in ("case_id", "user_key", "reviewer_key", "reviewed_at"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"{key} is required")
    if record.get("split") not in {"train", "validation", "test"}:
        raise ValueError("split must be train, validation, or test")
    _tokens(record.get("preferred_tags", []), "preferred_tags")
    _tokens(record.get("excluded_tags", []), "excluded_tags")
    pool = record.get("candidate_pool")
    if not isinstance(pool, list) or not pool:
        raise ValueError("candidate_pool must be a non-empty list")
    seen = set()
    for c in pool:
        if not isinstance(c, dict):
            raise ValueError("candidate_pool entries must be objects")
        cid = c.get("candidate_id")
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            raise ValueError("candidate_id values must be non-empty and unique per case")
        seen.add(cid)
        _tokens(c.get("item_ids"), "item_ids", True)
        _tokens(c.get("categories"), "categories", True)
        _tokens(c.get("tags"), "tags", True)
        score, rating = c.get("model_score"), c.get("human_relevance")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise ValueError("model_score must be a finite number")
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
            raise ValueError("human_relevance must be a human rating from 1 to 5")
        for flag in ("shown", "user_edited", "user_rejected"):
            if not isinstance(c.get(flag, False), bool):
                raise ValueError(f"{flag} must be boolean")
        if (c.get("user_edited") or c.get("user_rejected")) and not c.get("shown"):
            raise ValueError("an edited or rejected candidate must have been shown")
        if c.get("user_rejected") and not str(c.get("rejection_key", "")).strip():
            raise ValueError("rejection_key is required for rejected shown candidates")

def _candidate_tags(c: dict[str, Any]) -> set[str]:
    return _tokens(c.get("tags"), "tags") | _tokens(c.get("categories"), "categories")

def _jaccard_distance(a: set[str], b: set[str]) -> float:
    union = a | b
    return 0.0 if not union else 1.0 - len(a & b) / len(union)

def _baseline_key(c: dict[str, Any], preferred: set[str], excluded: set[str]):
    tags = _candidate_tags(c)
    return (
        0 if tags & excluded else 1,
        len(tags & preferred),
        len(_tokens(c.get("categories"), "categories")) + min(len(_tokens(c.get("item_ids"), "item_ids")), 4),
        str(c["candidate_id"]),
    )

def _rank(record: dict[str, Any], method: str) -> list[dict[str, Any]]:
    pool = list(record["candidate_pool"])
    if method == METHOD_MODEL:
        return sorted(pool, key=lambda c: (-float(c["model_score"]), str(c["candidate_id"])))
    preferred = _tokens(record.get("preferred_tags", []), "preferred_tags")
    excluded = _tokens(record.get("excluded_tags", []), "excluded_tags")
    return sorted(pool, key=lambda c: tuple(-x if isinstance(x, int) else x for x in _baseline_key(c, preferred, excluded)[:3]) + (str(c["candidate_id"]),))

def _method_metrics(records: list[dict[str, Any]], method: str, k: int) -> dict[str, float | int]:
    selected, ratings, distances = [], [], []
    violations = 0
    for record in records:
        ranked = _rank(record, method)[:k]
        selected.extend(ranked)
        ratings.extend(float(c["human_relevance"]) for c in ranked)
        excluded = _tokens(record.get("excluded_tags", []), "excluded_tags")
        violations += sum(bool(_candidate_tags(c) & excluded) for c in ranked)
        for i, left in enumerate(ranked):
            a = _tokens(left.get("item_ids"), "item_ids")
            for right in ranked[i + 1:]:
                distances.append(_jaccard_distance(a, _tokens(right.get("item_ids"), "item_ids")))
    n = len(selected)
    return {
        "outfit_count_at_k": n,
        "relevance_mean_at_k": round(sum(ratings) / n, 6) if n else 0.0,
        "diversity_mean_pairwise_item_jaccard_distance_at_k": round(sum(distances) / len(distances), 6) if distances else 0.0,
        "exclusion_violation_rate_at_k": round(violations / n, 6) if n else 0.0,
    }

def _observed_user_metrics(records: list[dict[str, Any]]) -> dict[str, float | int]:
    shown = [(r, c) for r in records for c in r["candidate_pool"] if c.get("shown") is True]
    edited = sum(c.get("user_edited") is True for _, c in shown)
    rejected = [(r["user_key"], str(c.get("rejection_key", "")).strip()) for r, c in shown if c.get("user_rejected") is True]
    counts = Counter(rejected)
    repeated = sum(n for n in counts.values() if n > 1)
    return {
        "shown_recommendation_count": len(shown),
        "user_edit_rate": round(edited / len(shown), 6) if shown else 0.0,
        "user_rejection_count": len(rejected),
        "repeated_rejection_rate_among_rejections": round(repeated / len(rejected), 6) if rejected else 0.0,
        "repeated_user_rejection_pairs": sum(n > 1 for n in counts.values()),
    }

def evaluate(records: Iterable[dict[str, Any]], k: int = 3) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be at least 1")
    rows = list(records)
    if not rows:
        raise ValueError("dataset contains no records")
    seen = set()
    for row in rows:
        _validate_record(row)
        key = (row["split"], row["case_id"])
        if key in seen:
            raise ValueError("case_id must be unique within each split")
        seen.add(key)
    report = {
        "schema_version": SCHEMA_VERSION, "k": k, "case_count": len(rows),
        "split_metrics": {}, "observed_user_outcomes": {}, "paired_model_minus_baseline": {},
        "interpretation": {
            "relevance": "mean blinded human relevance rating (1-5) among top-k",
            "diversity": "mean pairwise Jaccard distance between top-k outfit item-id sets; higher is more distinct",
            "exclusion_violations": "share of top-k outfits containing a declared excluded tag; lower is better",
            "user_outcomes": "observed only for actually shown recommendations; not a baseline counterfactual unless a randomized baseline arm was served",
            "repeated_rejection": "share of rejected impressions in a repeated (pseudonymous user_key, rejection_key) pair",
        },
    }
    for split in ("train", "validation", "test"):
        subset = [r for r in rows if r["split"] == split]
        if not subset:
            continue
        model, baseline = _method_metrics(subset, METHOD_MODEL, k), _method_metrics(subset, METHOD_BASELINE, k)
        report["split_metrics"][split] = {METHOD_MODEL: model, METHOD_BASELINE: baseline}
        report["paired_model_minus_baseline"][split] = {
            key: round(float(model[key]) - float(baseline[key]), 6)
            for key in model if key != "outfit_count_at_k"
        }
        report["observed_user_outcomes"][split] = _observed_user_metrics(subset)
    return report

def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {number} must contain a JSON object")
            rows.append(value)
    return rows

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare outfit ranking with a simple rule-based baseline.")
    parser.add_argument("dataset", help="Human-reviewed JSONL dataset")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = evaluate(load_jsonl(args.dataset), k=args.k)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

if __name__ == "__main__":
    main()

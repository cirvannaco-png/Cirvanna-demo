"""Offline evaluation of outfit ranking against a transparent rule baseline."""
from __future__ import annotations
import argparse, json, math
from collections import Counter
from pathlib import Path

def _tags(candidate):
    return {str(x).strip().casefold() for x in candidate.get("tags", []) + candidate.get("categories", []) if str(x).strip()}

def _items(candidate):
    return {str(x) for x in candidate["item_ids"]}

def _validate(row):
    for key in ("case_id", "user_key", "reviewer_key", "reviewed_at"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"{key} is required")
    if row.get("schema_version") != "1.0" or row.get("split") not in {"train", "validation", "test"}:
        raise ValueError("schema_version must be 1.0 and split must be train, validation, or test")
    if not isinstance(row.get("candidate_pool"), list) or not row["candidate_pool"]:
        raise ValueError("candidate_pool must be a non-empty list")
    if not isinstance(row.get("preferred_tags", []), list) or not isinstance(row.get("excluded_tags", []), list):
        raise ValueError("preferred_tags and excluded_tags must be lists")
    seen = set()
    for c in row["candidate_pool"]:
        cid = c.get("candidate_id")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError("candidate_id values must be non-empty and unique per case")
        seen.add(cid)
        for field in ("item_ids", "categories", "tags"):
            if not isinstance(c.get(field), list) or not c[field] or any(not isinstance(x, str) or not x for x in c[field]):
                raise ValueError(f"{field} must be a non-empty list of strings")
        score, rating = c.get("model_score"), c.get("human_relevance")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise ValueError("model_score must be finite")
        if not isinstance(rating, int) or isinstance(rating, bool) or rating not in range(1, 6):
            raise ValueError("human_relevance must be a human rating from 1 to 5")
        for flag in ("shown", "user_edited", "user_rejected"):
            if not isinstance(c.get(flag, False), bool):
                raise ValueError(f"{flag} must be boolean")
        if (c.get("user_edited") or c.get("user_rejected")) and not c.get("shown"):
            raise ValueError("user edit/rejection requires a shown impression")
        if c.get("user_rejected") and not c.get("rejection_key"):
            raise ValueError("rejection_key required for rejected impressions")

def _rank(row, method):
    pool = row["candidate_pool"]
    if method == "candidate_model":
        return sorted(pool, key=lambda c: (-c["model_score"], c["candidate_id"]))
    preferred = set(x.casefold() for x in row.get("preferred_tags", []))
    excluded = set(x.casefold() for x in row.get("excluded_tags", []))
    def key(c):
        tags = _tags(c)
        return (bool(tags & excluded), -len(tags & preferred), -len(c["categories"]), -min(len(c["item_ids"]), 4), c["candidate_id"])
    return sorted(pool, key=key)

def _metrics(rows, method, k):
    selected, ratings, distances, violations = [], [], [], 0
    for row in rows:
        top = _rank(row, method)[:k]
        selected.extend(top)
        ratings.extend(c["human_relevance"] for c in top)
        excluded = {x.casefold() for x in row.get("excluded_tags", [])}
        violations += sum(bool(_tags(c) & excluded) for c in top)
        for i, a in enumerate(top):
            for b in top[i+1:]:
                union = _items(a) | _items(b)
                distances.append(1 - len(_items(a) & _items(b)) / len(union) if union else 0)
    n = len(selected)
    return {
        "outfit_count_at_k": n,
        "relevance_mean_at_k": round(sum(ratings)/n, 6) if n else 0,
        "diversity_mean_pairwise_item_jaccard_distance_at_k": round(sum(distances)/len(distances), 6) if distances else 0,
        "exclusion_violation_rate_at_k": round(violations/n, 6) if n else 0,
    }

def _outcomes(rows):
    shown = [(r,c) for r in rows for c in r["candidate_pool"] if c.get("shown")]
    rejected = [(r["user_key"], c["rejection_key"]) for r,c in shown if c.get("user_rejected")]
    counts = Counter(rejected)
    return {
        "shown_recommendation_count": len(shown),
        "user_edit_rate": round(sum(c.get("user_edited", False) for _,c in shown)/len(shown), 6) if shown else 0,
        "user_rejection_count": len(rejected),
        "repeated_rejection_rate_among_rejections": round(sum(n for n in counts.values() if n > 1)/len(rejected), 6) if rejected else 0,
        "repeated_user_rejection_pairs": sum(n > 1 for n in counts.values()),
    }

def evaluate(rows, k=3):
    if k < 1 or not rows:
        raise ValueError("k must be positive and dataset non-empty")
    seen = set()
    for row in rows:
        _validate(row)
        key = (row["split"], row["case_id"])
        if key in seen:
            raise ValueError("case_id must be unique within split")
        seen.add(key)
    report = {"schema_version":"1.0", "k":k, "case_count":len(rows), "split_metrics":{}, "observed_user_outcomes":{}, "paired_model_minus_baseline":{}}
    for split in ("train", "validation", "test"):
        subset = [r for r in rows if r["split"] == split]
        if not subset:
            continue
        model, baseline = _metrics(subset, "candidate_model", k), _metrics(subset, "simple_baseline", k)
        report["split_metrics"][split] = {"candidate_model":model, "simple_baseline":baseline}
        report["paired_model_minus_baseline"][split] = {x:round(model[x]-baseline[x],6) for x in model if x != "outfit_count_at_k"}
        report["observed_user_outcomes"][split] = _outcomes(subset)
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()
    rows = []
    with Path(args.dataset).open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if line.strip():
                try: rows.append(json.loads(line))
                except json.JSONDecodeError as exc: raise ValueError(f"invalid JSON line {number}") from exc
    rendered = json.dumps(evaluate(rows, args.k), indent=2, sort_keys=True)
    if args.output: Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

if __name__ == "__main__":
    main()

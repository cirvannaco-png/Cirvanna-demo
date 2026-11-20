#!/usr/bin/env python3
"""Score matched fashion retrieval rankings against graded human relevance labels."""
from __future__ import annotations
import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

METRICS = ("recall_at_k", "precision_at_k", "mrr_at_k", "ndcg_at_k",
           "top1_hit_rate", "no_result_rate", "top_k_fill_rate",
           "candidate_coverage", "hard_exclusion_violation_rate")


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    result = [x.strip() for x in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def _validate_record(row: Any, line: int) -> dict[str, Any]:
    prefix = f"line {line}"
    if not isinstance(row, dict):
        raise ValueError(f"{prefix}: each JSONL row must be an object")
    for field in ("schema_version", "query_id", "cluster_id", "task_id", "split"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{prefix}: {field} must be a non-empty string")
    if row["schema_version"] != "1.0":
        raise ValueError(f"{prefix}: unsupported schema_version")
    candidates = _strings(row.get("candidate_ids"), "candidate_ids")
    candidate_set = set(candidates)
    qrels = row.get("qrels")
    if not isinstance(qrels, dict) or not qrels:
        raise ValueError(f"{prefix}: qrels must be a non-empty object")
    if not set(qrels).issubset(candidate_set):
        raise ValueError(f"{prefix}: qrels contain IDs outside candidate_ids")
    for product_id, grade in qrels.items():
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError(f"{prefix}: qrel product IDs must be non-empty")
        if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 4:
            raise ValueError(f"{prefix}: qrels[{product_id!r}] must be an integer from 0 to 4")
    if not any(grade > 0 for grade in qrels.values()):
        raise ValueError(f"{prefix}: at least one qrel must have positive relevance")
    rankings = row.get("rankings")
    if not isinstance(rankings, dict) or len(rankings) < 2:
        raise ValueError(f"{prefix}: rankings must contain at least two model IDs")
    normalized = {}
    for model_id, ranking in rankings.items():
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"{prefix}: model IDs must be non-empty")
        model_key = model_id.strip()
        if model_key in normalized:
            raise ValueError(f"{prefix}: model IDs must be unique after normalization")
        ranked = _strings(ranking, f"rankings[{model_id!r}]")
        if not set(ranked).issubset(candidate_set):
            raise ValueError(f"{prefix}: model {model_id!r} ranked an ID outside candidate_ids")
        normalized[model_key] = ranked
    excluded = _strings(row.get("excluded_product_ids", []), "excluded_product_ids")
    if not set(excluded).issubset(candidate_set):
        raise ValueError(f"{prefix}: excluded_product_ids must be part of candidate_ids")
    subgroups = row.get("subgroups", {})
    if not isinstance(subgroups, dict) or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        for k, v in subgroups.items()
    ):
        raise ValueError(f"{prefix}: subgroups must map non-empty string keys to values")
    return {**row, "candidate_ids": candidates, "qrels": qrels, "rankings": normalized,
            "excluded_product_ids": excluded, "subgroups": subgroups}


def read_cases(path: str | Path, split: str = "test") -> list[dict[str, Any]]:
    cases = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line, raw in enumerate(handle, 1):
            if raw.strip():
                row = _validate_record(json.loads(raw), line)
                if row["split"] == split:
                    cases.append(row)
    if not cases:
        raise ValueError(f"no query cases found for split={split!r}")
    if len({case["query_id"] for case in cases}) != len(cases):
        raise ValueError("query_id must be unique within the selected split")
    if len({case["task_id"] for case in cases}) != 1:
        raise ValueError("do not mix retrieval tasks; evaluate one task_id per run")
    if len({tuple(sorted(case["rankings"])) for case in cases}) != 1:
        raise ValueError("every query must contain the same model IDs")
    return cases


def _dcg(grades: list[int], k: int) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1)
               for rank, grade in enumerate(grades[:k], start=1))


def query_metrics(case: dict[str, Any], model_id: str, k: int) -> dict[str, float]:
    ranking = case["rankings"][model_id]
    qrels: dict[str, int] = case["qrels"]
    relevant = {pid for pid, grade in qrels.items() if grade > 0}
    top = ranking[:k]
    hits = sum(1 for pid in top if qrels.get(pid, 0) > 0)
    first = next((i for i, pid in enumerate(top, 1) if qrels.get(pid, 0) > 0), None)
    ideal_dcg = _dcg(sorted(qrels.values(), reverse=True), k)
    ndcg = _dcg([qrels.get(pid, 0) for pid in top], k) / ideal_dcg if ideal_dcg else 0.0
    violation = bool(set(case["excluded_product_ids"]).intersection(top))
    return {
        "recall_at_k": hits / len(relevant),
        "precision_at_k": hits / k,
        "mrr_at_k": 1.0 / first if first else 0.0,
        "ndcg_at_k": ndcg,
        "top1_hit_rate": 1.0 if top and qrels.get(top[0], 0) > 0 else 0.0,
        "no_result_rate": 1.0 if not ranking else 0.0,
        "top_k_fill_rate": min(len(top), k) / k,
        "candidate_coverage": len(ranking) / len(case["candidate_ids"]),
        "hard_exclusion_violation_rate": 1.0 if violation else 0.0,
    }


def _ci(clusters: dict[str, list[dict[str, float]]], metric: str,
        samples: int, seed: int) -> list[float] | None:
    keys = sorted(clusters)
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        chosen = [rng.choice(keys) for _ in keys]
        sample = [row[metric] for key in chosen for row in clusters[key]]
        values.append(statistics.mean(sample))
    values.sort()
    return [round(values[int(.025 * (len(values) - 1))], 6),
            round(values[int(.975 * (len(values) - 1))], 6)]


def _summary(rows: list[tuple[str, dict[str, float]]], samples: int, seed: int) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, float]]] = defaultdict(list)
    for cluster, metrics in rows:
        clusters[cluster].append(metrics)
    flat = [metrics for _, metrics in rows]
    return {
        "query_count": len(flat),
        "cluster_count": len(clusters),
        "metrics": {m: round(statistics.mean(r[m] for r in flat), 6) for m in METRICS},
        "confidence_intervals_95": {m: _ci(clusters, m, samples, seed + i)
                                    for i, m in enumerate(METRICS)},
    }


def evaluate(cases: list[dict[str, Any]], *, baseline_model_id: str, k: int = 10,
             primary_metric: str = "ndcg_at_k", bootstrap_samples: int = 2000,
             seed: int = 20261120) -> dict[str, Any]:
    if k < 1 or bootstrap_samples < 100:
        raise ValueError("k must be positive and bootstrap_samples must be at least 100")
    if primary_metric not in METRICS:
        raise ValueError(f"primary_metric must be one of: {', '.join(METRICS)}")
    if not cases:
        raise ValueError("cases must not be empty")
    models = sorted(cases[0]["rankings"])
    if baseline_model_id not in models:
        raise ValueError(f"baseline model {baseline_model_id!r} is absent")
    per_model = {model: [] for model in models}
    for case in cases:
        for model in models:
            per_model[model].append((case["cluster_id"], query_metrics(case, model, k)))
    systems = {model: _summary(rows, bootstrap_samples, seed + i * 100)
               for i, (model, rows) in enumerate(per_model.items())}
    paired = {}
    baseline_rows = per_model[baseline_model_id]
    for model, rows in per_model.items():
        if model == baseline_model_id:
            continue
        delta_clusters: dict[str, list[dict[str, float]]] = defaultdict(list)
        for (base_cluster, base), (candidate_cluster, candidate) in zip(baseline_rows, rows):
            if base_cluster != candidate_cluster:
                raise ValueError("paired query order or cluster IDs differ across models")
            delta_clusters[base_cluster].append({m: candidate[m] - base[m] for m in METRICS})
        flat = [x for group in delta_clusters.values() for x in group]
        paired[model] = {
            "paired_query_count": len(flat),
            "delta_vs_baseline": {m: round(statistics.mean(x[m] for x in flat), 6) for m in METRICS},
            "delta_confidence_intervals_95": {
                m: _ci(delta_clusters, m, bootstrap_samples, seed + 10000 + i)
                for i, m in enumerate(METRICS)
            },
        }
    subgroup_reports = {}
    subgroup_keys = sorted({key for case in cases for key in case["subgroups"]})
    for key in subgroup_keys:
        subgroup_reports[key] = {}
        values = sorted({case["subgroups"][key] for case in cases if key in case["subgroups"]})
        for j, value in enumerate(values):
            subset = [case for case in cases if case["subgroups"].get(key) == value]
            subgroup_reports[key][value] = {
                model: _summary(
                    [(case["cluster_id"], query_metrics(case, model, k)) for case in subset],
                    bootstrap_samples, seed + 20000 + j * 100,
                ) for model in models
            }
    gates = {model: systems[model]["metrics"]["hard_exclusion_violation_rate"] == 0.0
             for model in models}
    return {
        "status": "evaluated_rankings_only",
        "task_id": cases[0]["task_id"],
        "split": cases[0]["split"],
        "query_count": len(cases),
        "cluster_count": len({case["cluster_id"] for case in cases}),
        "k": k,
        "primary_metric": primary_metric,
        "baseline_model_id": baseline_model_id,
        "hard_exclusion_gate_passed": gates,
        "systems": systems,
        "paired_vs_baseline": paired,
        "subgroups": subgroup_reports,
        "limitations": [
            "Scores supplied rankings only; it does not prove inference ran or verify model/data licences.",
            "Confidence intervals resample cluster_id; justify this independent unit in the run manifest.",
            "Human qrels and the primary metric must be pre-registered before final-test evaluation.",
            "Zero exclusion violations applies only to supplied exclusion IDs and evaluated top-k depth.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-model-id", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--primary-metric", required=True, choices=METRICS)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261120)
    args = parser.parse_args()
    cases = read_cases(args.input, args.split)
    report = evaluate(cases, baseline_model_id=args.baseline_model_id, k=args.k,
                      primary_metric=args.primary_metric, bootstrap_samples=args.bootstrap_samples,
                      seed=args.seed)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "queries": report["query_count"],
                      "primary_metric": report["primary_metric"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)

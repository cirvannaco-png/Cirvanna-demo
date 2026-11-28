#!/usr/bin/env python3
"""Score matched fashion retrieval rankings against graded human relevance labels."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .validate_preregistration import validate_registration
except ImportError:  # direct script execution from this directory
    from validate_preregistration import validate_registration

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
    if not isinstance(qrels, dict) or set(qrels) != candidate_set:
        raise ValueError(f"{prefix}: qrels must contain an explicit grade for every candidate ID")
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
    human_violations = _strings(
        row.get("human_exclusion_violation_ids", []), "human_exclusion_violation_ids"
    )
    if not set(human_violations).issubset(candidate_set):
        raise ValueError(f"{prefix}: human_exclusion_violation_ids must be part of candidate_ids")
    subgroups = row.get("subgroups", {})
    if not isinstance(subgroups, dict) or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        for k, v in subgroups.items()
    ):
        raise ValueError(f"{prefix}: subgroups must map non-empty string keys to values")
    return {**row, "candidate_ids": candidates, "qrels": qrels, "rankings": normalized,
            "excluded_product_ids": excluded,
            "human_exclusion_violation_ids": human_violations, "subgroups": subgroups}


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
    hard_violations = set(case.get("excluded_product_ids", [])) | set(case.get("human_exclusion_violation_ids", []))
    violation = bool(hard_violations.intersection(top))
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


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_private_artifact_manifests(registration: dict[str, Any]) -> dict[str, Any]:
    """Verify the data, qrels and dependency artifacts against preregistered digests."""
    loaded = {}
    for path_field, digest_field, label in (
        ("rights_manifest_path", "rights_manifest_sha256", "rights"),
        ("data_manifest_path", "data_manifest_sha256", "data"),
        ("qrels_manifest_path", "qrels_manifest_sha256", "qrels"),
        ("dependency_lock_path", "dependency_lock_sha256", "dependency lock"),
    ):
        path = registration[path_field]
        if sha256_file(path) != registration[digest_field]:
            raise ValueError(f"{label} artifact SHA-256 differs from locked preregistration")
        if label == "rights":
            try:
                from .data_rights import load_and_validate_data_rights_manifest
            except ImportError:
                from data_rights import load_and_validate_data_rights_manifest
            loaded[label] = load_and_validate_data_rights_manifest(path)
        elif label in {"data", "qrels"}:
            loaded[label] = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_rights_digest = loaded["rights"]["manifest_sha256"]
    for label in ("data", "qrels"):
        artifact_rights = loaded[label].get("data_rights") if isinstance(loaded[label], dict) else None
        if not isinstance(artifact_rights, dict) or artifact_rights.get("manifest_sha256") != expected_rights_digest:
            raise ValueError(f"{label} manifest is not bound to the preregistered data-rights approval")
    if loaded["data"].get("qrels_manifest_sha256") != registration["qrels_manifest_sha256"]:
        raise ValueError("prepared-data manifest does not bind the preregistered human-qrels manifest")
    if loaded["data"].get("query_cases_sha256") != loaded["qrels"].get("output_sha256"):
        raise ValueError("prepared-data manifest does not bind the reviewed qrels artifact digest")
    if registration["task_id"] == "image_to_catalog_image":
        privacy_path = registration["privacy_preprocessing_manifest_path"]
        if sha256_file(privacy_path) != registration["privacy_preprocessing_manifest_sha256"]:
            raise ValueError("privacy preprocessing manifest differs from locked preregistration")
        privacy = json.loads(Path(privacy_path).read_text(encoding="utf-8"))
        if (
            not isinstance(privacy, dict)
            or privacy.get("schema_version") != "1.0"
            or privacy.get("approval_status") != "approved"
            or privacy.get("scope") != "click_it_image_to_image_benchmark"
            or privacy.get("face_masked_before_inference") is not True
            or privacy.get("face_recognition") is not False
        ):
            raise ValueError("privacy preprocessing manifest is not approved for masked image-to-image evaluation")
        evidence_path = Path(str(privacy.get("evidence_path", ""))).expanduser()
        if not evidence_path.is_absolute():
            evidence_path = Path(privacy_path).expanduser().resolve().parent / evidence_path
        evidence_path = evidence_path.resolve()
        if (
            not evidence_path.is_file()
            or privacy.get("evidence_sha256") != sha256_file(evidence_path)
        ):
            raise ValueError("privacy preprocessing reviewer evidence is missing or has a digest mismatch")
        loaded["privacy_preprocessing"] = privacy
    return loaded


def validate_run_manifest(
    manifest: dict[str, Any], registration: dict[str, Any], rankings_path: str | Path,
    data_manifest: dict[str, Any],
) -> None:
    """Bind final rankings to the exact prepared data, runner output and model revisions."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("run manifest must be a schema_version 1.0 object")
    expected_models = {
        registration["baseline"]["model_id"]: registration["baseline"]["revision"],
        **registration["challengers"],
    }
    rights = manifest.get("data_rights")
    if not isinstance(rights, dict) or rights.get("manifest_sha256") != registration["rights_manifest_sha256"]:
        raise ValueError("runner manifest data-rights digest differs from locked preregistration")
    if manifest.get("model_revisions") != expected_models:
        raise ValueError("run manifest model revisions differ from the locked preregistration")
    if manifest.get("rankings_output_sha256") != sha256_file(rankings_path):
        raise ValueError("rankings input SHA-256 does not match the runner manifest")
    if manifest.get("input_sha256") != data_manifest.get("output_sha256"):
        raise ValueError("runner input SHA-256 does not match the preregistered prepared-data manifest")
    if manifest.get("query_count") != data_manifest.get("query_count"):
        raise ValueError("runner query count differs from the preregistered prepared-data manifest")
    if manifest.get("candidate_pool_sizes") != data_manifest.get("candidate_pool_sizes"):
        raise ValueError("runner candidate-pool sizes differ from the preregistered prepared-data manifest")
    if manifest.get("split") != "test":
        raise ValueError("runner manifest split must be test for final evaluation")
    if manifest.get("task_id") != registration["task_id"]:
        raise ValueError("runner manifest task_id differs from the locked preregistration")
    if registration["task_id"] == "image_to_catalog_image":
        privacy = manifest.get("privacy_preprocessing")
        if (
            not isinstance(privacy, dict)
            or privacy.get("manifest_sha256") != registration["privacy_preprocessing_manifest_sha256"]
            or privacy.get("face_masked_before_inference") is not True
            or privacy.get("face_recognition") is not False
        ):
            raise ValueError("runner privacy preprocessing does not match the locked masking manifest")


def validate_final_test_registration(
    cases: list[dict[str, Any]], registration: dict[str, Any], *,
    baseline_model_id: str, k: int, primary_metric: str,
    bootstrap_samples: int, seed: int,
) -> None:
    """Enforce the locked protocol before final-test metrics are calculated."""
    registration = validate_registration(registration)
    if not cases:
        raise ValueError("final-test cases must not be empty")
    if registration["task_id"] != cases[0]["task_id"]:
        raise ValueError("preregistration task_id does not match evaluation cases")
    if registration["primary_metric"] != primary_metric or registration["k"] != k:
        raise ValueError("evaluation metric/k differs from the locked preregistration")
    if registration["bootstrap_samples"] != bootstrap_samples:
        raise ValueError("bootstrap_samples differs from the locked preregistration")
    if registration["bootstrap_seed"] != seed:
        raise ValueError("bootstrap seed differs from the locked preregistration")
    if registration["baseline"]["model_id"] != baseline_model_id:
        raise ValueError("baseline model ID differs from the locked preregistration")
    models = set(cases[0]["rankings"])
    expected = {baseline_model_id, *registration["challengers"].keys()}
    if models != expected:
        raise ValueError("evaluated model IDs differ from the locked baseline/challenger set")
    query_count = len(cases)
    cluster_count = len({case["cluster_id"] for case in cases})
    if query_count < registration["minimum_query_count"]:
        raise ValueError("final-test query count is below the preregistered minimum")
    if cluster_count < registration["minimum_independent_clusters"]:
        raise ValueError("final-test independent cluster count is below the preregistered minimum")
    allowed_pool_sizes = set(registration["candidate_pool_sizes"])
    observed_pool_sizes = {len(case["candidate_ids"]) for case in cases}
    if not observed_pool_sizes.issubset(allowed_pool_sizes):
        raise ValueError("candidate pool sizes differ from the locked preregistration")


def evaluate_preregistered_challenger_gates(
    report: dict[str, Any], registration: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Apply the preregistered practical-effect, uncertainty and hard-exclusion gates."""
    gates = {}
    threshold = registration["minimum_practically_important_delta"]
    for model_id, paired in report["paired_vs_baseline"].items():
        delta = paired["delta_vs_baseline"]["ndcg_at_k"]
        lower_ci = paired["delta_confidence_intervals_95"]["ndcg_at_k"][0]
        hard_gate = report["hard_exclusion_gate_passed"][model_id]
        gates[model_id] = {
            "hard_exclusion_gate_passed": hard_gate,
            "minimum_practically_important_delta": threshold,
            "observed_primary_metric_delta": delta,
            "primary_metric_ci95_lower": lower_ci,
            "practical_improvement_gate_passed": delta >= threshold and lower_ci > 0,
            "overall_passed": hard_gate and delta >= threshold and lower_ci > 0,
        }
    return gates


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
    parser.add_argument("--preregistration", help="Required for final split=test; private locked registration JSON")
    parser.add_argument("--run-manifest", help="Required for final split=test; runner manifest paired with rankings input")
    args = parser.parse_args()
    cases = read_cases(args.input, args.split)
    if args.split == "test":
        if not args.preregistration:
            raise ValueError("--preregistration is required for final split=test evaluation")
        if not args.run_manifest:
            raise ValueError("--run-manifest is required for final split=test evaluation")
        registration = json.loads(Path(args.preregistration).read_text(encoding="utf-8"))
        validate_final_test_registration(
            cases, registration, baseline_model_id=args.baseline_model_id, k=args.k,
            primary_metric=args.primary_metric, bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        artifacts = validate_private_artifact_manifests(registration)
        manifest = json.loads(Path(args.run_manifest).read_text(encoding="utf-8"))
        validate_run_manifest(manifest, registration, args.input, artifacts["data"])
    report = evaluate(cases, baseline_model_id=args.baseline_model_id, k=args.k,
                      primary_metric=args.primary_metric, bootstrap_samples=args.bootstrap_samples,
                      seed=args.seed)
    if args.split == "test":
        report["preregistered_challenger_gates"] = evaluate_preregistered_challenger_gates(report, registration)
        report["status"] = "final_test_scored_gates_evaluated"
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

#!/usr/bin/env python3
"""Evaluate Cirvanna outfit ranking against a deterministic, explainable baseline."""
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

SYSTEMS = ("cirvanna", "baseline")
ACTIONS = {"accepted", "edited", "rejected", "no_action"}


def _strings(value: Any, field: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    return {x.strip().casefold() for x in value}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _candidate_features(candidate: dict[str, Any]) -> set[str]:
    features: set[str] = set()
    for field in ("garment_ids", "category_tags", "style_tags", "color_tags"):
        features.update(f"{field}:{value}" for value in _strings(candidate.get(field, []), field))
    return features


def _violates_declared_exclusions(candidate: dict[str, Any], context: dict[str, Any]) -> bool:
    forbidden_items = _strings(context.get("hard_excluded_item_ids", []), "hard_excluded_item_ids")
    forbidden_tags = _strings(context.get("hard_excluded_tags", []), "hard_excluded_tags")
    garment_ids = _strings(candidate.get("garment_ids", []), "garment_ids")
    exclusion_tags = _strings(candidate.get("exclusion_tags", []), "exclusion_tags")
    return bool(forbidden_items & garment_ids or forbidden_tags & exclusion_tags)


def baseline_score(candidate: dict[str, Any], context: dict[str, Any]) -> float | None:
    """Hard-filter explicit exclusions, then score category and declared-context matches."""
    if _violates_declared_exclusions(candidate, context):
        return None
    required = _strings(context.get("required_categories", []), "required_categories")
    categories = _strings(candidate.get("category_tags", []), "category_tags")
    category_coverage = len(required & categories) / len(required) if required else 0.0
    preferred_styles = _strings(context.get("preferred_style_tags", []), "preferred_style_tags")
    styles = _strings(candidate.get("style_tags", []), "style_tags")
    style_match = _jaccard(preferred_styles, styles) if preferred_styles else 0.0
    preferred_colors = _strings(context.get("preferred_color_tags", []), "preferred_color_tags")
    colors = _strings(candidate.get("color_tags", []), "color_tags")
    color_match = _jaccard(preferred_colors, colors) if preferred_colors else 0.0
    occasion = str(context.get("occasion") or "").strip().casefold()
    occasions = _strings(candidate.get("occasion_tags", []), "occasion_tags")
    occasion_match = 1.0 if occasion and occasion in occasions else 0.0
    return 3.0 * category_coverage + 2.0 * occasion_match + style_match + 0.5 * color_match


def _resolve_reviews(record: dict[str, Any], look_ids: set[str]) -> dict[str, dict[str, Any]]:
    by_look: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in record.get("human_reviews", []):
        if not isinstance(review, dict):
            raise ValueError("human_reviews entries must be objects")
        look_id = review.get("look_id")
        reviewer = review.get("reviewer_key")
        relevance = review.get("relevance")
        violation = review.get("exclusion_violation")
        if look_id not in look_ids or not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("human review must reference a known look and reviewer_key")
        if isinstance(relevance, bool) or not isinstance(relevance, int) or not 1 <= relevance <= 5:
            raise ValueError("human relevance must be an integer from 1 to 5")
        if not isinstance(violation, bool):
            raise ValueError("exclusion_violation must be boolean")
        by_look[look_id].append(review)

    adjudications: dict[str, dict[str, Any]] = {}
    for item in record.get("adjudications", []):
        if not isinstance(item, dict) or item.get("look_id") not in look_ids:
            raise ValueError("adjudication must reference a known look")
        if not isinstance(item.get("adjudicator_key"), str) or not item["adjudicator_key"].strip():
            raise ValueError("adjudicator_key is required")
        relevance = item.get("relevance")
        if isinstance(relevance, bool) or not isinstance(relevance, int) or not 1 <= relevance <= 5:
            raise ValueError("adjudicated relevance must be an integer from 1 to 5")
        if not isinstance(item.get("exclusion_violation"), bool):
            raise ValueError("adjudicated exclusion_violation must be boolean")
        if item["look_id"] in adjudications:
            raise ValueError("only one adjudication is allowed per look")
        adjudications[item["look_id"]] = item

    resolved: dict[str, dict[str, Any]] = {}
    for look_id in look_ids:
        reviews = by_look.get(look_id, [])
        reviewer_keys = [str(item["reviewer_key"]).strip() for item in reviews]
        if len(reviews) != 2 or len(set(reviewer_keys)) != 2:
            raise ValueError(f"{look_id}: exactly two independent reviewers are required; duplicate reviewer rows are invalid")
        labels = {(item["relevance"], item["exclusion_violation"]) for item in reviews}
        if len(labels) == 1:
            relevance, violation = next(iter(labels))
        else:
            adjudication = adjudications.get(look_id)
            if adjudication is None:
                raise ValueError(f"{look_id}: reviewer disagreement requires adjudication")
            if adjudication["adjudicator_key"] in reviewer_keys:
                raise ValueError(f"{look_id}: adjudicator must be independent")
            relevance = adjudication["relevance"]
            violation = adjudication["exclusion_violation"]
        resolved[look_id] = {"relevance": relevance, "exclusion_violation": violation}
    return resolved


def _ndcg(ranking: list[str], labels: dict[str, dict[str, Any]], k: int) -> float:
    def dcg(items: list[str]) -> float:
        return sum((2 ** (labels[item]["relevance"] - 1) - 1) / math.log2(rank + 1)
                   for rank, item in enumerate(items[:k], start=1))
    ideal = sorted(labels, key=lambda item: labels[item]["relevance"], reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    return dcg(ranking) / ideal_dcg if ideal_dcg else 0.0


def _diversity(ranking: list[str], candidates: dict[str, dict[str, Any]], k: int) -> float:
    selected = ranking[:k]
    if len(selected) < 2:
        return 0.0
    feature_sets = [_candidate_features(candidates[item]) for item in selected]
    distances = [1.0 - _jaccard(feature_sets[i], feature_sets[j])
                 for i in range(len(feature_sets)) for j in range(i + 1, len(feature_sets))]
    return statistics.mean(distances) if distances else 0.0


def _baseline_ranking(candidates: dict[str, dict[str, Any]], context: dict[str, Any]) -> list[str]:
    scored: list[tuple[float, str]] = []
    for look_id, candidate in candidates.items():
        score = baseline_score(candidate, context)
        if score is not None:
            scored.append((score, look_id))
    return [look_id for _, look_id in sorted(scored, key=lambda row: (-row[0], row[1]))]


def _validate_case(record: dict[str, Any], k: int):
    for field in ("case_id", "participant_key", "session_id"):
        if not isinstance(record.get(field), str) or len(record[field].strip()) < 6:
            raise ValueError(f"{field} must be a pseudonymous identifier with at least 6 characters")
    if record.get("schema_version") != "1.0":
        raise ValueError("schema_version must be '1.0'")
    assigned = record.get("assigned_system")
    if assigned not in SYSTEMS:
        raise ValueError("assigned_system must be cirvanna or baseline")
    context = record.get("context")
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    candidates_raw = record.get("candidate_outfits")
    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise ValueError("candidate_outfits must be a non-empty array")
    candidates: dict[str, dict[str, Any]] = {}
    for candidate in candidates_raw:
        if not isinstance(candidate, dict):
            raise ValueError("candidate_outfits entries must be objects")
        look_id = candidate.get("look_id")
        if not isinstance(look_id, str) or not look_id.strip() or look_id in candidates:
            raise ValueError("look_id values must be unique non-empty strings")
        _candidate_features(candidate)
        _strings(candidate.get("occasion_tags", []), "occasion_tags")
        _strings(candidate.get("exclusion_tags", []), "exclusion_tags")
        if not _strings(candidate.get("garment_ids", []), "garment_ids"):
            raise ValueError(f"{look_id}: garment_ids cannot be empty")
        candidates[look_id] = candidate
    cirvanna = record.get("cirvanna_ranked_look_ids")
    if not isinstance(cirvanna, list) or not cirvanna or any(x not in candidates for x in cirvanna):
        raise ValueError("cirvanna_ranked_look_ids must rank known looks")
    if len(cirvanna) != len(set(cirvanna)):
        raise ValueError("cirvanna ranking cannot contain duplicate look IDs")
    rankings = {"cirvanna": cirvanna, "baseline": _baseline_ranking(candidates, context)}
    labels = _resolve_reviews(record, set(candidates))
    exposures = record.get("exposures", [])
    if not isinstance(exposures, list):
        raise ValueError("exposures must be an array")
    assigned_top = set(rankings[assigned][:k])
    seen_exposure_looks: set[str] = set()
    for exposure in exposures:
        if not isinstance(exposure, dict) or exposure.get("look_id") not in assigned_top:
            raise ValueError("exposure must reference a look in assigned system's top-k")
        exposure_look_id = exposure["look_id"]
        if exposure_look_id in seen_exposure_looks:
            raise ValueError("duplicate exposure outcome for the same look in one session")
        seen_exposure_looks.add(exposure_look_id)
        if exposure.get("action") not in ACTIONS:
            raise ValueError("invalid exposure action")
        edit_count = exposure.get("edit_count", 0)
        if isinstance(edit_count, bool) or not isinstance(edit_count, int) or not 0 <= edit_count <= 50:
            raise ValueError("edit_count must be an integer from 0 to 50")
        if exposure["action"] == "edited" and edit_count < 1:
            raise ValueError("edited exposures require edit_count >= 1")
        if exposure["action"] != "edited" and edit_count != 0:
            raise ValueError("edit_count must be zero unless action is edited")
    return candidates, context, rankings, labels


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261107
RANKING_CI_METRICS = (
    "no_result_rate", "top_k_fill_rate", "mean_human_relevance_top_k",
    "ndcg_at_k", "intra_list_diversity", "hard_exclusion_violation_rate",
)

def _cluster_bootstrap_ci(clusters: dict[str, list[dict[str, Any]]], metric: str, seed: int) -> list[float] | None:
    """Percentile CI resampling participant clusters, preserving repeated sessions."""
    keys = sorted(clusters)
    observed = [row[metric] for key in keys for row in clusters[key] if row.get(metric) is not None]
    if not observed:
        return None
    point = statistics.mean(observed)
    if len(keys) < 2:
        # One participant cluster cannot support a sampling-uncertainty interval.
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled_keys = [rng.choice(keys) for _ in keys]
        sample = [row[metric] for key in sampled_keys for row in clusters[key] if row.get(metric) is not None]
        if sample:
            estimates.append(statistics.mean(sample))
    if not estimates:
        return None
    estimates.sort()
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return [round(low, 4), round(high, 4)]

def _weighted_cohen_kappa(pairs: list[tuple[int, int]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum((left - right) ** 2 / 16 for left, right in pairs) / n
    first = [sum(a == score for a, _ in pairs) / n for score in range(1, 6)]
    second = [sum(b == score for _, b in pairs) / n for score in range(1, 6)]
    expected = sum(first[i] * second[j] * ((i - j) ** 2 / 16) for i in range(5) for j in range(5))
    return 1.0 - observed / expected if expected > 0 else None

def _nominal_cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(left != right for left, right in pairs) / n
    p1 = sum(left for left, _ in pairs) / n
    p2 = sum(right for _, right in pairs) / n
    expected = p1 * (1 - p2) + (1 - p1) * p2
    return 1.0 - observed / expected if expected > 0 else None

def _inter_rater_agreement(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Report raw agreement and kappa within stable pseudonymous reviewer pairs."""
    groups: dict[tuple[str, str], dict[str, list[tuple[Any, Any]]]] = defaultdict(lambda: {"relevance": [], "exclusion": []})
    for record in records:
        by_look: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for review in record.get("human_reviews", []):
            by_look[str(review["look_id"])].append(review)
        for reviews in by_look.values():
            ordered = sorted(reviews, key=lambda item: str(item["reviewer_key"]))
            key = (str(ordered[0]["reviewer_key"]), str(ordered[1]["reviewer_key"]))
            groups[key]["relevance"].append((ordered[0]["relevance"], ordered[1]["relevance"]))
            groups[key]["exclusion"].append((ordered[0]["exclusion_violation"], ordered[1]["exclusion_violation"]))
    relevance = [pair for group in groups.values() for pair in group["relevance"]]
    exclusion = [pair for group in groups.values() for pair in group["exclusion"]]
    relevance_kappas = [(len(g["relevance"]), v) for g in groups.values() if (v := _weighted_cohen_kappa(g["relevance"])) is not None]
    exclusion_kappas = [(len(g["exclusion"]), v) for g in groups.values() if (v := _nominal_cohen_kappa(g["exclusion"])) is not None]
    def weighted_mean(values):
        total = sum(weight for weight, _ in values)
        return round(sum(weight * value for weight, value in values) / total, 4) if total else None
    return {
        "candidate_review_pairs": len(relevance),
        "reviewer_pair_groups": len(groups),
        "exact_relevance_agreement_rate": round(sum(a == b for a, b in relevance) / len(relevance), 4) if relevance else None,
        "hard_exclusion_agreement_rate": round(sum(a == b for a, b in exclusion) / len(exclusion), 4) if exclusion else None,
        "weighted_relevance_kappa_across_reviewer_pairs": weighted_mean(relevance_kappas),
        "hard_exclusion_kappa_across_reviewer_pairs": weighted_mean(exclusion_kappas),
        "relevance_kappa_defined_reviewer_pairs": len(relevance_kappas),
        "exclusion_kappa_defined_reviewer_pairs": len(exclusion_kappas),
        "kappa_note": "Kappa is calculated within stable pseudonymous reviewer pairs and weighted by reviewed candidates. Null means expected disagreement was zero or no pair had sufficient variation.",
    }

def evaluate(records: list[dict[str, Any]], k: int = 3) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    if not records:
        return {
            "status": "insufficient_human_reviewed_data",
            "reviewed_contexts": 0,
            "k": k,
            "systems": {},
            "warning": "No human-reviewed records were supplied; no performance claim is supported.",
        }
    accum = {system: defaultdict(list) for system in SYSTEMS}
    empty_slates = {system: 0 for system in SYSTEMS}
    top_k_fill = {system: [] for system in SYSTEMS}
    assigned_exposures = {system: [] for system in SYSTEMS}
    case_metrics = {system: defaultdict(list) for system in SYSTEMS}
    paired_case_metrics: dict[str, list[dict[str, float | None]]] = defaultdict(list)
    seen_case_ids: set[str] = set()
    participant_assignments: dict[str, str] = {}
    for record in records:
        case_id = record.get("case_id")
        if case_id in seen_case_ids:
            raise ValueError("case_id values must be unique")
        seen_case_ids.add(case_id)
        participant_key = record.get("participant_key")
        assigned_system = record.get("assigned_system")
        previous_assignment = participant_assignments.setdefault(participant_key, assigned_system)
        if previous_assignment != assigned_system:
            raise ValueError("participant must remain in one randomized system arm across sessions")
        candidates, context, rankings, labels = _validate_case(record, k)
        per_case: dict[str, dict[str, float | None]] = {}
        for system, ranking in rankings.items():
            selected = ranking[:k]
            top_k_fill[system].append(len(selected) / k)
            if not selected:
                empty_slates[system] += 1
            relevance = [float(labels[item]["relevance"]) for item in selected]
            violations = [
                labels[item]["exclusion_violation"] or _violates_declared_exclusions(candidates[item], context)
                for item in selected
            ]
            accum[system]["relevance"].append(statistics.mean(relevance) if relevance else 0.0)
            accum[system]["ndcg"].append(_ndcg(ranking, labels, k))
            accum[system]["diversity"].append(_diversity(ranking, candidates, k))
            if violations:
                accum[system]["violations"].append(sum(violations) / len(violations))
            per_case[system] = {
                "no_result_rate": 1.0 if not selected else 0.0,
                "top_k_fill_rate": len(selected) / k,
                "mean_human_relevance_top_k": statistics.mean(relevance) if relevance else 0.0,
                "ndcg_at_k": _ndcg(ranking, labels, k),
                "intra_list_diversity": _diversity(ranking, candidates, k),
                "hard_exclusion_violation_rate": sum(violations) / len(violations) if violations else None,
            }
            case_metrics[system][participant_key].append(per_case[system])
        paired_case_metrics[participant_key].append({
            metric: (
                per_case["cirvanna"][metric] - per_case["baseline"][metric]
                if per_case["cirvanna"][metric] is not None and per_case["baseline"][metric] is not None
                else None
            )
            for metric in RANKING_CI_METRICS
        })
        system = record["assigned_system"]
        for exposure in record.get("exposures", []):
            candidate = candidates[exposure["look_id"]]
            signature_source = "\n".join(sorted(_strings(candidate["garment_ids"], "garment_ids")))
            signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
            assigned_exposures[system].append((
                record["participant_key"], record["session_id"], signature,
                1 if exposure["action"] == "edited" else 0,
                1 if exposure["action"] == "rejected" else 0,
                exposure["edit_count"],
            ))
    output = {}
    for system in SYSTEMS:
        exposures = assigned_exposures[system]
        edits = sum(item[3] for item in exposures)
        rejections = sum(item[4] for item in exposures)
        rejected_by_session: dict[tuple[str, str], set[str]] = defaultdict(set)
        for participant, session, signature, edited, rejected, count in exposures:
            if rejected:
                rejected_by_session[(participant, signature)].add(session)
        repeated_count = sum(1 for sessions in rejected_by_session.values() if len(sessions) >= 2)
        output[system] = {
            "reviewed_contexts": len(records),
            "no_result_rate": round(empty_slates[system] / len(records), 4),
            "top_k_fill_rate": _mean(top_k_fill[system]),
            "mean_human_relevance_top_k": _mean(accum[system]["relevance"]),
            "ndcg_at_k": _mean(accum[system]["ndcg"]),
            "intra_list_diversity": _mean(accum[system]["diversity"]),
            "hard_exclusion_violation_rate": _mean(accum[system]["violations"]),
            "observed_exposures": len(exposures),
            "edited_look_rate": round(edits / len(exposures), 4) if exposures else None,
            "mean_edit_count_per_exposure": round(sum(item[5] for item in exposures) / len(exposures), 4) if exposures else None,
            "rejection_rate": round(rejections / len(exposures), 4) if exposures else None,
            "repeated_rejection_signature_rate": round(repeated_count / len(rejected_by_session), 4) if rejected_by_session else None,
            "rejected_unique_look_signatures": len(rejected_by_session),
            "repeatedly_rejected_look_signatures": repeated_count,
            "confidence_intervals_95": {
                metric: _cluster_bootstrap_ci(
                    case_metrics[system], metric,
                    BOOTSTRAP_SEED + (0 if system == "cirvanna" else 1) + offset,
                )
                for offset, metric in enumerate(RANKING_CI_METRICS)
            },
        }
    paired_ci = {
        metric: _cluster_bootstrap_ci(paired_case_metrics, metric, BOOTSTRAP_SEED + 100 + offset)
        for offset, metric in enumerate(RANKING_CI_METRICS)
    }
    deltas = {}
    for metric in ("mean_human_relevance_top_k", "ndcg_at_k", "intra_list_diversity", "hard_exclusion_violation_rate"):
        left, right = output["cirvanna"][metric], output["baseline"][metric]
        deltas[metric] = round(left - right, 4) if left is not None and right is not None else None
    return {
        "status": "descriptive_only",
        "reviewed_contexts": len(records),
        "k": k,
        "systems": output,
        "cirvanna_minus_baseline": deltas,
        "paired_cirvanna_minus_baseline_confidence_intervals_95": paired_ci,
        "inter_rater_agreement": _inter_rater_agreement(records),
        "confidence_interval_method": "Percentile cluster bootstrap over participant_key; 2,000 resamples; fixed seed. Descriptive intervals do not replace a pre-registered study analysis.",
        "warning": "Offline metrics are descriptive. User behaviour is measured only for the randomized live arm. Pre-register sample size and subgroup analysis before claiming superiority.",
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: each JSONL row must be an object")
            records.append(value)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="restricted, consented JSONL export")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    try:
        result = evaluate(load_jsonl(args.input), args.k)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid_dataset", "error": str(exc)}), file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

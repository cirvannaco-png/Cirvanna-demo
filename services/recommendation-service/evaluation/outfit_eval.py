from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RANKER_ALGORITHM = "algorithm"
RANKER_BASELINE = "simple_baseline"
VALID_SPLITS = {"development", "locked_test"}
VALID_DISPOSITIONS = {"accept", "reject", "edit"}
VALID_USER_EVENTS = {"exposed", "accepted", "rejected", "edited"}
CORE_TOPS = {"top", "tops", "shirt", "shirts", "blouse", "blouses"}
CORE_BOTTOMS = {"bottom", "bottoms", "trousers", "pants", "skirt", "skirts", "jeans"}
CORE_ONE_PIECE = {"dress", "dresses", "jumpsuit", "jumpsuits", "one_piece", "one-pieces"}


class EvaluationError(ValueError):
    """Raised when a review dataset is incomplete or invalid."""


def _clean_tokens(values: Any, field: str) -> set[str]:
    if not isinstance(values, list):
        raise EvaluationError(f"{field} must be a list")
    cleaned: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise EvaluationError(f"{field} entries must be non-empty strings")
        cleaned.add(" ".join(value.casefold().split()))
    return cleaned


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvaluationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def simple_baseline_score(candidate: dict[str, Any], scenario: dict[str, Any]) -> float:
    """Transparent non-personalized baseline: completeness + context + declared style overlap."""
    categories = _clean_tokens(candidate.get("categories", []), "candidate.categories")
    has_top = bool(categories & CORE_TOPS)
    has_bottom = bool(categories & CORE_BOTTOMS)
    has_one_piece = bool(categories & CORE_ONE_PIECE)
    completeness = 1.0 if has_one_piece or (has_top and has_bottom) else (
        0.5 if has_top or has_bottom else 0.0
    )
    context_match = _jaccard(
        _clean_tokens(candidate.get("context_tags", []), "candidate.context_tags"),
        _clean_tokens(scenario.get("context_tags", []), "scenario.context_tags"),
    )
    style_match = _jaccard(
        _clean_tokens(candidate.get("style_tags", []), "candidate.style_tags"),
        _clean_tokens(scenario.get("style_preferences", []), "scenario.style_preferences"),
    )
    return round(0.50 * completeness + 0.30 * context_match + 0.20 * style_match, 8)


def validate_record(record: dict[str, Any], line_number: int = 0) -> None:
    prefix = f"line {line_number}: " if line_number else ""
    if not isinstance(record, dict):
        raise EvaluationError(prefix + "record must be a JSON object")
    for field in ("case_id", "split"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise EvaluationError(prefix + f"{field} is required")
    if record.get("dataset_version") != "1.0":
        raise EvaluationError(prefix + "dataset_version must be '1.0'")
    if record["split"] not in VALID_SPLITS:
        raise EvaluationError(prefix + f"split must be one of {sorted(VALID_SPLITS)}")
    scenario = record.get("scenario")
    if not isinstance(scenario, dict):
        raise EvaluationError(prefix + "scenario must be an object")
    _clean_tokens(scenario.get("context_tags", []), "scenario.context_tags")
    _clean_tokens(scenario.get("style_preferences", []), "scenario.style_preferences")
    _clean_tokens(scenario.get("hard_exclusions", []), "scenario.hard_exclusions")

    candidates = record.get("candidate_outfits")
    if not isinstance(candidates, list) or not candidates:
        raise EvaluationError(prefix + "candidate_outfits must be a non-empty list")
    candidate_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise EvaluationError(prefix + "each candidate_outfit must be an object")
        outfit_id = candidate.get("outfit_id")
        if not isinstance(outfit_id, str) or not outfit_id.strip() or outfit_id in candidate_ids:
            raise EvaluationError(prefix + "outfit_id values must be unique non-empty strings")
        candidate_ids.add(outfit_id)
        score = candidate.get("algorithm_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise EvaluationError(prefix + f"{outfit_id}: algorithm_score must be finite")
        for field in ("item_ids", "categories", "colors", "style_tags", "context_tags", "hard_exclusion_hits"):
            _clean_tokens(candidate.get(field, []), f"{outfit_id}.{field}")
        if not candidate.get("item_ids"):
            raise EvaluationError(prefix + f"{outfit_id}: item_ids cannot be empty")

    reviews = record.get("human_reviews")
    if not isinstance(reviews, list):
        raise EvaluationError(prefix + "human_reviews must be a list")
    review_index: dict[str, set[str]] = defaultdict(set)
    for review in reviews:
        if not isinstance(review, dict):
            raise EvaluationError(prefix + "each human review must be an object")
        reviewer = review.get("reviewer_key")
        outfit_id = review.get("outfit_id")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise EvaluationError(prefix + "reviewer_key is required")
        if outfit_id not in candidate_ids:
            raise EvaluationError(prefix + f"review references unknown outfit_id {outfit_id!r}")
        if reviewer in review_index[outfit_id]:
            raise EvaluationError(prefix + f"duplicate review by reviewer for {outfit_id}")
        review_index[outfit_id].add(reviewer)
        for rating in ("relevance", "coherence", "context_fit"):
            value = review.get(rating)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise EvaluationError(prefix + f"{outfit_id}.{rating} must be an integer from 1 to 5")
        if not isinstance(review.get("exclusion_violation"), bool):
            raise EvaluationError(prefix + f"{outfit_id}.exclusion_violation must be boolean")
        if review.get("disposition") not in VALID_DISPOSITIONS:
            raise EvaluationError(prefix + f"{outfit_id}.disposition must be accept, reject or edit")
        if review["disposition"] == "edit":
            proposed = review.get("proposed_item_ids")
            if not isinstance(proposed, list) or not proposed:
                raise EvaluationError(prefix + f"{outfit_id}: edit reviews require proposed_item_ids")
            _clean_tokens(proposed, f"{outfit_id}.proposed_item_ids")
    unreviewed = sorted(outfit_id for outfit_id in candidate_ids if len(review_index[outfit_id]) < 2)
    if unreviewed:
        raise EvaluationError(prefix + "each candidate needs two independent human reviews: " + ", ".join(unreviewed))

    events = record.get("user_outcomes", [])
    if not isinstance(events, list):
        raise EvaluationError(prefix + "user_outcomes must be a list")
    event_ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            raise EvaluationError(prefix + "each user_outcome must be an object")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in event_ids:
            raise EvaluationError(prefix + "event_id values must be unique non-empty strings within a case")
        event_ids.add(event_id)
        if event.get("outfit_id") not in candidate_ids:
            raise EvaluationError(prefix + "user_outcome references an unknown outfit_id")
        if not isinstance(event.get("subject_key"), str) or not event["subject_key"].strip():
            raise EvaluationError(prefix + "subject_key must be a pseudonymous non-empty key")
        if not isinstance(event.get("exposure_id"), str) or not event["exposure_id"].strip():
            raise EvaluationError(prefix + "exposure_id is required to deduplicate user actions")
        if event.get("ranker_id") not in {RANKER_ALGORITHM, RANKER_BASELINE}:
            raise EvaluationError(prefix + "ranker_id must be algorithm or simple_baseline")
        if event.get("event_type") not in VALID_USER_EVENTS:
            raise EvaluationError(prefix + f"event_type must be one of {sorted(VALID_USER_EVENTS)}")
        _parse_time(event.get("occurred_at"), "user_outcomes.occurred_at")
        edited_count = event.get("edited_item_count", 0)
        if isinstance(edited_count, bool) or not isinstance(edited_count, int) or edited_count < 0:
            raise EvaluationError(prefix + "edited_item_count must be a non-negative integer")
        if event["event_type"] == "edited" and edited_count < 1:
            raise EvaluationError(prefix + "edited events require edited_item_count >= 1")

    exposure_keys = {
        (item["subject_key"], item["ranker_id"], item["outfit_id"], item["exposure_id"])
        for item in events if item["event_type"] == "exposed"
    }
    for event in events:
        if event["event_type"] != "exposed":
            key = (event["subject_key"], event["ranker_id"], event["outfit_id"], event["exposure_id"])
            if key not in exposure_keys:
                raise EvaluationError(prefix + "user action must reference a recorded exposure")


def _human_labels(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_outfit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in record["human_reviews"]:
        by_outfit[review["outfit_id"]].append(review)
    labels: dict[str, dict[str, Any]] = {}
    for outfit_id, reviews in by_outfit.items():
        labels[outfit_id] = {
            "relevance": statistics.mean(item["relevance"] for item in reviews),
            "coherence": statistics.mean(item["coherence"] for item in reviews),
            "context_fit": statistics.mean(item["context_fit"] for item in reviews),
            # A single reviewer flag is enough to surface a possible hard-exclusion breach.
            "exclusion_violation": any(item["exclusion_violation"] for item in reviews),
            "review_count": len(reviews),
            "disagreement": (
                max(item["relevance"] for item in reviews) - min(item["relevance"] for item in reviews) >= 2
                or len({item["exclusion_violation"] for item in reviews}) > 1
            ),
        }
    return labels


def _dcg(values: list[float]) -> float:
    return sum((2 ** value - 1) / math.log2(position + 2) for position, value in enumerate(values))


def _slate_metrics(
    ranked: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    selected = ranked[:k]
    if not selected:
        return {
            "outfits_at_k": 0,
            "mean_relevance_at_k": None,
            "ndcg_at_k": None,
            "mean_coherence_at_k": None,
            "mean_context_fit_at_k": None,
            "diversity_at_k": None,
            "human_exclusion_violation_rate_at_k": None,
            "known_exclusion_hit_rate_at_k": None,
            "possible_violation_outfits_at_k": [],
            "review_disagreement_rate_at_k": None,
        }
    selected_labels = [labels[item["outfit_id"]] for item in selected]
    relevance = [item["relevance"] for item in selected_labels]
    ideal = sorted((item["relevance"] for item in labels.values()), reverse=True)[:k]
    ideal_dcg = _dcg(ideal)
    feature_sets = []
    for item in selected:
        feature_sets.append(
            _clean_tokens(item.get("categories", []), "candidate.categories")
            | _clean_tokens(item.get("colors", []), "candidate.colors")
            | _clean_tokens(item.get("style_tags", []), "candidate.style_tags")
        )
    pairwise = [
        1.0 - _jaccard(feature_sets[left], feature_sets[right])
        for left in range(len(feature_sets))
        for right in range(left + 1, len(feature_sets))
    ]
    flagged = [
        item["outfit_id"] for item, label in zip(selected, selected_labels)
        if label["exclusion_violation"] or bool(item.get("hard_exclusion_hits"))
    ]
    human_violations = sum(label["exclusion_violation"] for label in selected_labels)
    known_hits = sum(bool(item.get("hard_exclusion_hits")) for item in selected)
    return {
        "outfits_at_k": len(selected),
        "mean_relevance_at_k": round(statistics.mean(relevance), 4),
        "ndcg_at_k": round(_dcg(relevance) / ideal_dcg, 4) if ideal_dcg else None,
        "mean_coherence_at_k": round(statistics.mean(item["coherence"] for item in selected_labels), 4),
        "mean_context_fit_at_k": round(statistics.mean(item["context_fit"] for item in selected_labels), 4),
        "diversity_at_k": round(statistics.mean(pairwise), 4) if pairwise else 0.0,
        "human_exclusion_violation_rate_at_k": round(human_violations / len(selected), 4),
        "known_exclusion_hit_rate_at_k": round(known_hits / len(selected), 4),
        "possible_violation_outfits_at_k": flagged,
        "review_disagreement_rate_at_k": round(sum(item["disagreement"] for item in selected_labels) / len(selected), 4),
    }


def _user_behavior_metrics(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    events = list(events)
    for event in events:
        grouped[event["ranker_id"]].append(event)
    result: dict[str, Any] = {}
    for ranker in (RANKER_ALGORITHM, RANKER_BASELINE):
        own = grouped.get(ranker, [])
        exposures = [item for item in own if item["event_type"] == "exposed"]
        edits = [item for item in own if item["event_type"] == "edited"]
        rejects = [item for item in own if item["event_type"] == "rejected"]
        exposure_ids = {
            (item["subject_key"], item["outfit_id"], item["exposure_id"])
            for item in exposures
        }
        edited_exposures = {
            (item["subject_key"], item["outfit_id"], item["exposure_id"])
            for item in edits
        }
        rejected_exposures = {
            (item["subject_key"], item["outfit_id"], item["exposure_id"])
            for item in rejects
        }
        pair_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in own:
            pair_events[(event["subject_key"], event["outfit_id"])].append(event)
        rejected_pairs = 0
        repeated_rejected_pairs = 0
        reexposed_after_rejection = 0
        for pair in pair_events.values():
            ordered = sorted(pair, key=lambda item: _parse_time(item["occurred_at"], "occurred_at"))
            rejected_times = [
                _parse_time(item["occurred_at"], "occurred_at")
                for item in ordered if item["event_type"] == "rejected"
            ]
            if rejected_times:
                rejected_pairs += 1
                if len({
                    item["exposure_id"] for item in ordered
                    if item["event_type"] == "rejected"
                }) >= 2:
                    repeated_rejected_pairs += 1
                first_rejection = min(rejected_times)
                reexposed_after_rejection += sum(
                    _parse_time(item["occurred_at"], "occurred_at") > first_rejection
                    for item in ordered if item["event_type"] == "exposed"
                )
        result[ranker] = {
            "exposures": len(exposures),
            "edited_exposures": len(edited_exposures),
            "edit_rate": round(len(edited_exposures) / len(exposure_ids), 4) if exposure_ids else None,
            "mean_edited_items_per_exposure": (
                round(sum(item["edited_item_count"] for item in edits) / len(exposure_ids), 4)
                if exposure_ids else None
            ),
            "rejections": len(rejects),
            "rejected_exposures": len(rejected_exposures),
            "rejection_rate": round(len(rejected_exposures) / len(exposure_ids), 4) if exposure_ids else None,
            "rejected_subject_outfit_pairs": rejected_pairs,
            "repeated_rejection_rate": (
                round(repeated_rejected_pairs / rejected_pairs, 4) if rejected_pairs else None
            ),
            "reexposures_after_first_rejection": reexposed_after_rejection,
        }
    return result


def evaluate_records(records: list[dict[str, Any]], k: int = 3) -> dict[str, Any]:
    if k < 1:
        raise EvaluationError("k must be at least 1")
    if not records:
        raise EvaluationError("no evaluation records were supplied")
    aggregate: dict[str, dict[str, list[float]]] = {
        RANKER_ALGORITHM: defaultdict(list),
        RANKER_BASELINE: defaultdict(list),
    }
    violation_cases: dict[str, int] = defaultdict(int)
    disagreements = 0
    candidate_count = 0
    behavior_events: list[dict[str, Any]] = []
    for line_number, record in enumerate(records, start=1):
        validate_record(record, line_number)
        scenario = record["scenario"]
        candidates = record["candidate_outfits"]
        labels = _human_labels(record)
        algorithm_ranked = sorted(candidates, key=lambda item: (-float(item["algorithm_score"]), item["outfit_id"]))
        baseline_ranked = sorted(
            candidates,
            key=lambda item: (-simple_baseline_score(item, scenario), item["outfit_id"]),
        )
        for ranker, ranked in ((RANKER_ALGORITHM, algorithm_ranked), (RANKER_BASELINE, baseline_ranked)):
            metrics = _slate_metrics(ranked, labels, k)
            for name in (
                "mean_relevance_at_k", "ndcg_at_k", "mean_coherence_at_k",
                "mean_context_fit_at_k", "diversity_at_k",
                "human_exclusion_violation_rate_at_k", "known_exclusion_hit_rate_at_k",
                "review_disagreement_rate_at_k",
            ):
                if metrics[name] is not None:
                    aggregate[ranker][name].append(metrics[name])
            if metrics["human_exclusion_violation_rate_at_k"] and metrics["human_exclusion_violation_rate_at_k"] > 0:
                violation_cases[ranker] += 1
            disagreements += sum(labels[item["outfit_id"]]["disagreement"] for item in ranked[:k])
            candidate_count += len(ranked[:k])
        behavior_events.extend(record.get("user_outcomes", []))

    summarized = {
        ranker: {
            name: round(statistics.mean(values), 4) if values else None
            for name, values in metrics.items()
        }
        for ranker, metrics in aggregate.items()
    }
    behavior = _user_behavior_metrics(behavior_events)
    deltas = {}
    for metric in (
        "mean_relevance_at_k", "ndcg_at_k", "mean_coherence_at_k",
        "mean_context_fit_at_k", "diversity_at_k",
        "human_exclusion_violation_rate_at_k", "known_exclusion_hit_rate_at_k",
    ):
        algorithm_value = summarized[RANKER_ALGORITHM][metric]
        baseline_value = summarized[RANKER_BASELINE][metric]
        deltas[metric] = (
            round(algorithm_value - baseline_value, 4)
            if algorithm_value is not None and baseline_value is not None else None
        )
    return {
        "schema_version": "1.0",
        "cases_evaluated": len(records),
        "top_k": k,
        "human_review_policy": "at_least_two_independent_reviewers_per_candidate",
        "rankers": summarized,
        "algorithm_minus_baseline": deltas,
        "hard_exclusion_cases_with_any_human_violation": dict(violation_cases),
        "ranked_candidate_slots_with_review_disagreement": disagreements,
        "ranked_candidate_slots": candidate_count,
        "user_behavior": behavior,
        "interpretation": {
            "human_labels_are_required": True,
            "empty_user_metrics_mean_uninstrumented_not_zero": True,
            "any_hard_exclusion_violation_is_a_release_blocker": True,
            "baseline": "0.50 category completeness + 0.30 context-tag Jaccard + 0.20 declared-style Jaccard",
        },
    }


def load_jsonl(path: Path, split: str = "all") -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationError(f"line {line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise EvaluationError(f"line {line_number}: record must be a JSON object")
            if split == "all" or record.get("split") == split:
                validate_record(record, line_number)
                records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare outfit ranking against a simple baseline using human reviews.")
    parser.add_argument("dataset", type=Path, help="JSONL file with two independent human reviews per candidate")
    parser.add_argument("--split", choices=("all", "development", "locked_test"), default="all")
    parser.add_argument("--k", type=int, default=3, help="Daily-look slate size; defaults to three")
    parser.add_argument("--output", type=Path, help="Optional path for the JSON metrics report")
    args = parser.parse_args()
    result = evaluate_records(load_jsonl(args.dataset, args.split), k=args.k)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

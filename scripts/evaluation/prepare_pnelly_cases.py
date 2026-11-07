#!/usr/bin/env python3
"""Join pseudonymous PNELLY candidate traces with blinded human reviews.

Input files are JSONL. Trace rows may be raw Gateway responses or objects
containing evaluation_trace directly. The coordinator must verify reviewer
identities outside this tool; this script enforces distinct reviewer keys only.
Reviews use:
  case_id, look_id, reviewer_key, relevance (1..5), exclusion_violation (bool)
Exposure rows are passed through to the evaluator after their case/look IDs
are checked. No participant or garment identifiers are resolved here.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each row must be an object")
            rows.append(value)
    return rows


def _extract_trace(row: dict[str, Any]) -> dict[str, Any]:
    forbidden_identity_keys = {"user_id", "subject_id", "owner_user_id", "account_id"}
    if forbidden_identity_keys.intersection(row):
        raise ValueError("trace response contains a raw user/account identifier")
    recommendation = row.get("recommendation")
    if isinstance(recommendation, dict) and forbidden_identity_keys.intersection(recommendation):
        raise ValueError("recommendation envelope contains a raw user/account identifier")
    if isinstance(row.get("evaluation_trace"), dict):
        return row["evaluation_trace"]
    recommendation = row.get("recommendation")
    if isinstance(recommendation, dict) and isinstance(recommendation.get("evaluation_trace"), dict):
        return recommendation["evaluation_trace"]
    return row


def _index_records(records: Iterable[dict[str, Any]], kind: str) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        case_id = record.get("case_id")
        look_id = record.get("look_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{kind} record is missing case_id")
        if not isinstance(look_id, str) or not look_id:
            raise ValueError(f"{kind} record is missing look_id")
        indexed[case_id].append(record)
    return indexed


def prepare_cases(
    trace_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    exposure_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reviews_by_case = _index_records(review_rows, "review")
    exposures_by_case = _index_records(exposure_rows or [], "exposure")
    cases: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    no_result_roles: dict[str, int] = defaultdict(int)
    trace_count = 0
    truncated_count = 0
    participant_assignments: dict[str, str] = {}

    for trace_row in trace_rows:
        trace = _extract_trace(trace_row)
        if trace.get("trace_version") != "1.0":
            raise ValueError("unsupported or missing PNELLY trace_version")
        privacy = trace.get("privacy", {})
        for key in ("raw_user_id_included", "raw_wardrobe_item_ids_included",
                    "display_names_included", "image_assets_included"):
            if privacy.get(key) is not False:
                raise ValueError(f"trace privacy gate failed: {key} must be false")
        if trace.get("candidate_pool_truncated") is True:
            truncated_count += 1
            raise ValueError("truncated candidate pools cannot enter the benchmark")
        trace_count += 1
        for role in trace.get("no_result_roles", []):
            no_result_roles[str(role)] += 1

        for source_case in trace.get("cases", []):
            case = dict(source_case)
            case_id = case.get("case_id")
            participant = case.get("participant_key")
            assigned = case.get("assigned_system")
            candidates = case.get("candidate_outfits")
            ranking = case.get("cirvanna_ranked_look_ids")
            if not isinstance(case_id, str) or not case_id or case_id in seen_case_ids:
                raise ValueError("case_id must be present and unique")
            seen_case_ids.add(case_id)
            if not isinstance(participant, str) or not participant:
                raise ValueError(f"{case_id}: participant_key is required")
            if assigned not in {"cirvanna", "baseline"}:
                raise ValueError(f"{case_id}: invalid assigned_system")
            previous = participant_assignments.setdefault(participant, assigned)
            if previous != assigned:
                raise ValueError(f"{case_id}: participant arm changed between sessions")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError(f"{case_id}: candidate_outfits must be non-empty")
            candidate_ids = [item.get("look_id") for item in candidates if isinstance(item, dict)]
            if len(candidate_ids) != len(candidates) or len(candidate_ids) != len(set(candidate_ids)):
                raise ValueError(f"{case_id}: candidate look IDs must be unique")
            if not isinstance(ranking, list) or not ranking or any(item not in set(candidate_ids) for item in ranking):
                raise ValueError(f"{case_id}: ranking must reference candidates in this case")

            case_reviews = reviews_by_case.pop(case_id, [])
            case_exposures = exposures_by_case.pop(case_id, [])
            reviews_for_look: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for record in case_reviews:
                look_id = record["look_id"]
                if look_id not in set(candidate_ids):
                    raise ValueError(f"{case_id}: review references an unknown candidate")
                reviewer_key = record.get("reviewer_key")
                relevance = record.get("relevance")
                exclusion_violation = record.get("exclusion_violation")
                if not isinstance(reviewer_key, str) or not reviewer_key.strip():
                    raise ValueError(f"{case_id}: reviewer_key is required")
                if not isinstance(relevance, int) or isinstance(relevance, bool) or not 1 <= relevance <= 5:
                    raise ValueError(f"{case_id}: relevance must be an integer from 1 to 5")
                if not isinstance(exclusion_violation, bool):
                    raise ValueError(f"{case_id}: exclusion_violation must be boolean")
                reviews_for_look[look_id].append({
                    "look_id": look_id,
                    "reviewer_key": reviewer_key.strip(),
                    "relevance": relevance,
                    "exclusion_violation": exclusion_violation,
                })
            for look_id in candidate_ids:
                ratings = reviews_for_look.get(look_id, [])
                reviewers = {row["reviewer_key"] for row in ratings}
                if len(ratings) != 2 or len(reviewers) != 2:
                    raise ValueError(f"{case_id}/{look_id}: exactly two distinct reviewer ratings are required")

            for record in case_exposures:
                if record["look_id"] not in set(candidate_ids):
                    raise ValueError(f"{case_id}: exposure references an unknown candidate")
            case["human_reviews"] = [row for look_id in candidate_ids for row in reviews_for_look[look_id]]
            case["exposures"] = [
                {key: value for key, value in row.items() if key != "case_id"}
                for row in case_exposures
            ]
            case.setdefault("adjudications", [])
            try:
                from evaluate_outfits import _validate_case
                _validate_case(case)
            except Exception as exc:
                raise ValueError(f"{case_id}: prepared case violates the frozen evaluator contract: {exc}") from exc
            cases.append(case)

    if reviews_by_case:
        raise ValueError("review file contains case IDs absent from trace input")
    if exposures_by_case:
        raise ValueError("exposure file contains case IDs absent from trace input")
    if not cases:
        raise ValueError("no reviewable PNELLY cases found")

    summary = {
        "trace_count": trace_count,
        "case_count": len(cases),
        "candidate_count": sum(len(case["candidate_outfits"]) for case in cases),
        "review_count": sum(len(case["human_reviews"]) for case in cases),
        "exposure_count": sum(len(case["exposures"]) for case in cases),
        "candidate_pool_truncated_trace_count": truncated_count,
        "no_result_roles_by_role": dict(no_result_roles),
        "assigned_systems": sorted({case["assigned_system"] for case in cases}),
        "review_data_source": "external_reviewer_file",
        "reviewer_identity_provenance_verified": False,
    }
    return cases, summary


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", required=True, help="JSONL containing Gateway trace responses")
    parser.add_argument("--reviews", required=True, help="JSONL of two independent ratings per candidate")
    parser.add_argument("--exposures", help="Optional JSONL of genuine live exposure outcomes")
    parser.add_argument("--output", required=True, help="Output evaluator case JSONL")
    parser.add_argument("--summary", help="Optional JSON summary path")
    args = parser.parse_args()

    cases, summary = prepare_cases(
        read_jsonl(args.traces),
        read_jsonl(args.reviews),
        read_jsonl(args.exposures) if args.exposures else [],
    )
    write_jsonl(args.output, cases)
    summary_path = Path(args.summary) if args.summary else Path(str(args.output) + ".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score an independent Click It face-masking evaluation without reading image bytes.

Input CSV is a reviewer-produced annotation/measurement export. It must contain
no photographs, biometric templates, names, DOBs or direct identifiers.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED_COLUMNS = {
    "stratum", "ground_truth_face_count", "missed_face_count",
    "unmasked_face_count", "mask_before_embedding", "uncertain", "uncertain_output_rejected",
    "identity_feature_calls", "age_estimation_calls", "child_media",
    "child_processing_performed", "public_publication_allowed",
}


class EvaluationError(ValueError):
    pass


def truth(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise EvaluationError(f"invalid boolean cell: {value!r}")


def wilson_upper(successes: int, total: int, z: float = 1.959963984540054) -> float:
    """Upper two-sided 95% Wilson bound for a binomial event rate."""
    if total <= 0:
        return 1.0
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = p + z2 / (2 * total)
    margin = z * math.sqrt((p * (1 - p) / total) + (z2 / (4 * total * total)))
    return min(1.0, (centre + margin) / denominator)


def score(csv_path: Path, policy: dict) -> dict:
    required_policy = {
        "minimum_faces_per_stratum", "maximum_fnr_upper_95",
        "maximum_unmasked_faces", "reject_uncertain_outputs",
        "maximum_identity_feature_calls", "maximum_age_estimation_calls",
        "reject_child_processing", "reject_child_publication",
    }
    if set(policy) != required_policy:
        raise EvaluationError("evaluation policy must contain the exact preregistered threshold fields")
    if not isinstance(policy["minimum_faces_per_stratum"], int) or policy["minimum_faces_per_stratum"] < 1:
        raise EvaluationError("minimum_faces_per_stratum must be a positive integer")
    if not 0 <= float(policy["maximum_fnr_upper_95"]) <= 1:
        raise EvaluationError("maximum_fnr_upper_95 must be between 0 and 1")
    for key in ("maximum_unmasked_faces", "maximum_identity_feature_calls", "maximum_age_estimation_calls"):
        if not isinstance(policy[key], int) or policy[key] < 0:
            raise EvaluationError(f"{key} must be a non-negative integer")
        if policy[key] != 0:
            raise EvaluationError(f"{key} must be zero for the Click It privacy acceptance profile")
    for key in ("reject_uncertain_outputs", "reject_child_processing", "reject_child_publication"):
        if policy[key] is not True:
            raise EvaluationError(f"{key} must be true for the Click It privacy acceptance profile")

    strata = defaultdict(lambda: {"faces": 0, "missed": 0, "unmasked": 0, "samples": 0})
    violations = []
    total_identity_calls = total_age_calls = total_unmasked = 0
    total_faces = total_missed = 0
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise EvaluationError("CSV is missing required evaluation columns")
        for line, row in enumerate(reader, start=2):
            stratum = row["stratum"].strip()
            if not stratum:
                raise EvaluationError(f"line {line}: stratum is blank")
            try:
                faces = int(row["ground_truth_face_count"])
                missed = int(row["missed_face_count"])
                unmasked = int(row["unmasked_face_count"])
                identity_calls = int(row["identity_feature_calls"])
                age_calls = int(row["age_estimation_calls"])
                mask_before_embedding = truth(row["mask_before_embedding"])
                uncertain = truth(row["uncertain"])
                uncertain_rejected = truth(row["uncertain_output_rejected"])
                child_media = truth(row["child_media"])
                child_processed = truth(row["child_processing_performed"])
                public_allowed = truth(row["public_publication_allowed"])
            except (ValueError, TypeError) as exc:
                raise EvaluationError(f"line {line}: invalid annotation value") from exc
            if min(faces, missed, unmasked, identity_calls, age_calls) < 0 or missed > faces or unmasked > faces:
                raise EvaluationError(f"line {line}: face/call counts are inconsistent")
            item = strata[stratum]
            item["samples"] += 1
            item["faces"] += faces
            item["missed"] += missed
            item["unmasked"] += unmasked
            total_faces += faces
            total_missed += missed
            total_unmasked += unmasked
            total_identity_calls += identity_calls
            total_age_calls += age_calls

            if faces and not mask_before_embedding:
                violations.append(f"line {line}: detected face regions were not masked before embedding")
            if unmasked:
                violations.append(f"line {line}: {unmasked} residual unmasked face(s)")
            if policy["reject_uncertain_outputs"] and uncertain and not uncertain_rejected:
                violations.append(f"line {line}: uncertain detector output was not rejected")
            if uncertain and public_allowed:
                violations.append(f"line {line}: uncertain detector output was allowed to publish")
            if identity_calls > 0:
                violations.append(f"line {line}: identity feature call detected")
            if age_calls > 0:
                violations.append(f"line {line}: age-estimation call detected")
            if policy["reject_child_processing"] and child_media and child_processed:
                violations.append(f"line {line}: child media was processed")
            if policy["reject_child_publication"] and child_media and public_allowed:
                violations.append(f"line {line}: child media was allowed public publication")

    if not strata:
        raise EvaluationError("evaluation CSV contains no samples")
    if total_unmasked > policy["maximum_unmasked_faces"]:
        violations.append("aggregate residual unmasked-face count exceeds preregistered maximum")
    if total_identity_calls > policy["maximum_identity_feature_calls"]:
        violations.append("aggregate identity feature calls exceed preregistered maximum")
    if total_age_calls > policy["maximum_age_estimation_calls"]:
        violations.append("aggregate age-estimation calls exceed preregistered maximum")

    per_stratum = {}
    for name, values in sorted(strata.items()):
        faces = values["faces"]
        missed = values["missed"]
        fnr = missed / faces if faces else 1.0
        upper = wilson_upper(missed, faces)
        per_stratum[name] = {
            "samples": values["samples"],
            "faces": faces,
            "missed_faces": missed,
            "false_negative_rate": fnr,
            "false_negative_rate_upper_95": upper,
            "unmasked_faces": values["unmasked"],
            "passed_sample_floor": faces >= policy["minimum_faces_per_stratum"],
            "passed_fnr_threshold": upper <= float(policy["maximum_fnr_upper_95"]),
        }
        if faces < policy["minimum_faces_per_stratum"]:
            violations.append(f"stratum {name}: only {faces} faces; below preregistered sample floor")
        if upper > float(policy["maximum_fnr_upper_95"]):
            violations.append(f"stratum {name}: FNR upper 95% bound exceeds preregistered threshold")

    return {
        "schema_version": 1,
        "evaluation": "click-it-independent-mask-quality",
        "passed": not violations,
        "total_samples": sum(item["samples"] for item in strata.values()),
        "total_faces": total_faces,
        "missed_faces": total_missed,
        "false_negative_rate": total_missed / total_faces if total_faces else 1.0,
        "false_negative_rate_upper_95": wilson_upper(total_missed, total_faces),
        "unmasked_faces": total_unmasked,
        "identity_feature_calls": total_identity_calls,
        "age_estimation_calls": total_age_calls,
        "strata": per_stratum,
        "violations": violations,
        "policy": policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path, help="pre-registered independent acceptance thresholds")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        report = score(args.csv, policy)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1
    except (OSError, json.JSONDecodeError, EvaluationError) as exc:
        print(f"Click It evaluation blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate a rollback exercise evidence record without fabricating operational proof."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "docs" / "operations" / "rollback-evidence-template.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
STATUSES = {"not_executed", "in_progress", "failed", "passed"}
CHECKS = (
    "service_versions",
    "readiness_and_dependencies",
    "identity_and_tenant_isolation",
    "discovery_usi_npl_eepl_fci_cal",
    "purchase_authorization_and_kill_switch",
    "payment_and_order_reconciliation",
    "consent_privacy_and_deletion",
    "queues_workers_and_inventory",
    "telemetry_and_alert_delivery",
)
REFERENCE_FIELDS = (
    "traffic_switch_reference",
    "pre_rollback_health_reference",
    "post_rollback_health_reference",
    "database_compatibility_or_restore_reference",
    "payment_and_order_reconciliation_reference",
    "consent_and_privacy_reconciliation_reference",
    "monitoring_alert_reference",
)


def _is_reference(value: Any) -> bool:
    return isinstance(value, str) and (
        value.startswith("https://") or value.startswith("evidence://")
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_rollback_evidence(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if document.get("repository") != "cirvannaco-png/Cirvanna-demo":
        errors.append("repository identity mismatch")
    status = document.get("status")
    if status not in STATUSES:
        errors.append(f"invalid status: {status!r}")
        return errors
    if status != "passed":
        return errors

    environment = document.get("environment")
    candidate = document.get("candidate_release")
    target = document.get("rollback_target")
    exercise = document.get("exercise")
    for name, value in (("environment", environment), ("candidate_release", candidate),
                        ("rollback_target", target), ("exercise", exercise)):
        if not isinstance(value, dict):
            errors.append(f"{name} must be an object")
    if errors:
        return errors

    if not isinstance(environment.get("id"), str) or not environment["id"].strip():
        errors.append("passed evidence requires environment.id")
    for name, release in (("candidate_release", candidate), ("rollback_target", target)):
        sha = release.get("commit_sha")
        if not isinstance(sha, str) or not FULL_SHA.fullmatch(sha):
            errors.append(f"{name}.commit_sha must be a full 40-character SHA")
        if not isinstance(release.get("deployment_id"), str) or not release["deployment_id"].strip():
            errors.append(f"{name}.deployment_id is required")
        digests = release.get("image_digests")
        if not isinstance(digests, list) or not digests:
            errors.append(f"{name}.image_digests must be a non-empty array")
        elif any(not isinstance(item, str) or not IMAGE_DIGEST.fullmatch(item) for item in digests):
            errors.append(f"{name}.image_digests must contain immutable sha256 digests")
    if candidate.get("commit_sha") == target.get("commit_sha"):
        errors.append("rollback target must be a different release commit")

    started = _parse_timestamp(exercise.get("started_at"))
    completed = _parse_timestamp(exercise.get("completed_at"))
    if started is None:
        errors.append("exercise.started_at must be a timezone-aware timestamp")
    if completed is None:
        errors.append("exercise.completed_at must be a timezone-aware timestamp")
    if started is not None and completed is not None and completed < started:
        errors.append("exercise.completed_at must not precede started_at")

    if not isinstance(exercise.get("trigger"), str) or not exercise["trigger"].strip():
        errors.append("exercise.trigger is required")
    for field in REFERENCE_FIELDS:
        if not _is_reference(exercise.get(field)):
            errors.append(f"exercise.{field} must be an https:// or evidence:// reference")
    for field in ("operator", "independent_approver"):
        if not isinstance(exercise.get(field), str) or not exercise[field].strip():
            errors.append(f"exercise.{field} is required")
    if exercise.get("operator") == exercise.get("independent_approver"):
        errors.append("operator and independent_approver must be different")

    measured = exercise.get("measured_rollback_seconds")
    rto = exercise.get("approved_rto_seconds")
    for field, value in (("measured_rollback_seconds", measured), ("approved_rto_seconds", rto)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f"exercise.{field} must be a non-negative number")
    if (isinstance(measured, (int, float)) and not isinstance(measured, bool)
            and isinstance(rto, (int, float)) and not isinstance(rto, bool)
            and measured > rto):
        errors.append("measured rollback duration exceeds approved RTO")
    if exercise.get("data_loss_observed") is not False:
        errors.append("passed evidence requires data_loss_observed=false")
    gaps = exercise.get("reconciliation_gap_count")
    if isinstance(gaps, bool) or not isinstance(gaps, int) or gaps != 0:
        errors.append("passed evidence requires reconciliation_gap_count=0")

    checks = exercise.get("post_rollback_checks")
    if not isinstance(checks, dict):
        errors.append("exercise.post_rollback_checks must be an object")
    else:
        for name in CHECKS:
            if checks.get(name) != "passed":
                errors.append(f"post-rollback check {name!r} must be passed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--require-passed", action="store_true",
                        help="fail unless a fully evidenced rollback exercise is passed")
    args = parser.parse_args()
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load rollback evidence: {exc}")
        return 1
    if not isinstance(document, dict):
        print("ERROR: rollback evidence root must be an object")
        return 1
    errors = validate_rollback_evidence(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    status = document["status"]
    print(f"OK: rollback evidence record is structurally valid; status={status}.")
    if args.require_passed and status != "passed":
        print("BLOCKED: no fully evidenced rollback exercise is recorded.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

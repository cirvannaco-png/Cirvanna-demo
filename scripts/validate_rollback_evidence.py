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
DATABASE_REFERENCE_FIELDS = (
    "pre_release_backup_reference",
    "schema_validation_reference",
    "external_event_reconciliation_reference",
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
    database = document.get("database_recovery")
    for name, value in (("environment", environment), ("candidate_release", candidate),
                        ("rollback_target", target), ("database_recovery", database), ("exercise", exercise)):
        if not isinstance(value, dict):
            errors.append(f"{name} must be an object")
    if errors:
        return errors

    if not isinstance(environment.get("id"), str) or not environment["id"].strip():
        errors.append("passed evidence requires environment.id")
    if not isinstance(environment.get("region"), str) or not environment["region"].strip():
        errors.append("passed evidence requires environment.region")
    for name, release in (("candidate_release", candidate), ("rollback_target", target)):
        sha = release.get("commit_sha")
        if not isinstance(sha, str) or not FULL_SHA.fullmatch(sha):
            errors.append(f"{name}.commit_sha must be a full 40-character SHA")
        if not isinstance(release.get("deployment_id"), str) or not release["deployment_id"].strip():
            errors.append(f"{name}.deployment_id is required")
        digests = release.get("image_digests")
        if not isinstance(digests, dict) or not digests:
            errors.append(f"{name}.image_digests must map every service to an immutable digest")
        elif any(
            not isinstance(service, str) or not service.strip()
            or not isinstance(digest, str) or not IMAGE_DIGEST.fullmatch(digest)
            for service, digest in digests.items()
        ):
            errors.append(f"{name}.image_digests must map service IDs to immutable sha256 digests")
    if candidate.get("commit_sha") == target.get("commit_sha"):
        errors.append("rollback target must be a different release commit")
    candidate_digests = candidate.get("image_digests")
    target_digests = target.get("image_digests")
    if isinstance(candidate_digests, dict) and isinstance(target_digests, dict) and candidate_digests and target_digests:
        if set(candidate_digests) != set(target_digests):
            errors.append("candidate and rollback image digest maps must cover the same service set")

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

    strategy = database.get("strategy")
    allowed_strategies = {
        "backward_compatible_application_rollback",
        "forward_fix",
        "point_in_time_restore",
    }
    if strategy not in allowed_strategies:
        errors.append("database_recovery.strategy must be a recognized recovery strategy")
    if not isinstance(database.get("candidate_migration_revision"), str) or not database["candidate_migration_revision"].strip():
        errors.append("database_recovery.candidate_migration_revision is required")
    compatibility = database.get("rollback_target_compatibility")
    if compatibility not in {"backward_compatible", "incompatible"}:
        errors.append("database_recovery.rollback_target_compatibility must be backward_compatible or incompatible")
    for field in DATABASE_REFERENCE_FIELDS:
        if not _is_reference(database.get(field)):
            errors.append(f"database_recovery.{field} must be an https:// or evidence:// reference")
    if strategy == "backward_compatible_application_rollback" and compatibility != "backward_compatible":
        errors.append("backward-compatible application rollback requires proven schema compatibility")
    if strategy == "forward_fix" and compatibility != "incompatible":
        errors.append("forward_fix strategy requires an explicit incompatible-schema finding")
    if strategy == "point_in_time_restore":
        if compatibility != "incompatible":
            errors.append("point-in-time restore requires an incompatible-schema finding")
        if not _is_reference(database.get("isolated_restore_reference")):
            errors.append("point-in-time restore requires an isolated_restore_reference")
    if strategy in {"forward_fix", "point_in_time_restore"}:
        if not _is_reference(database.get("external_event_reconciliation_reference")):
            errors.append("database recovery requires external event reconciliation evidence")
    data_loss = database.get("measured_data_loss_seconds")
    rpo = database.get("approved_rpo_seconds")
    for field, value in (("measured_data_loss_seconds", data_loss), ("approved_rpo_seconds", rpo)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f"database_recovery.{field} must be a non-negative number")
    if (isinstance(data_loss, (int, float)) and not isinstance(data_loss, bool)
            and isinstance(rpo, (int, float)) and not isinstance(rpo, bool)
            and data_loss > rpo):
        errors.append("measured database data loss exceeds approved RPO")

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

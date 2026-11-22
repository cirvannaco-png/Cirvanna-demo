#!/usr/bin/env python3
"""Validate external provider and operational evidence without manufacturing proof."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "docs" / "release" / "external-provider-qualification.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def _ref(value: Any) -> bool:
    return isinstance(value, str) and (value.startswith("https://") or value.startswith("evidence://"))


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if document.get("repository") != "cirvannaco-png/Cirvanna-demo":
        errors.append("repository identity mismatch")
    workstreams = document.get("workstreams")
    if not isinstance(workstreams, list) or not workstreams:
        return errors + ["workstreams must be a non-empty array"]
    seen: set[str] = set()
    for index, item in enumerate(workstreams):
        prefix = f"workstreams[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        key = item.get("id")
        if not isinstance(key, str) or not key or key in seen:
            errors.append(f"{prefix}.id must be non-empty and unique")
        else:
            seen.add(key)
        if item.get("status") not in {"blocked", "in_progress", "failed", "passed"}:
            errors.append(f"{prefix}.status is invalid")
            continue
        required = item.get("required_evidence")
        evidence = item.get("evidence", {})
        if not isinstance(required, list) or not required or not isinstance(evidence, dict):
            errors.append(f"{prefix} requires required_evidence and an evidence object")
            continue
        if item["status"] != "passed":
            continue
        for field in required:
            if evidence.get(field) in (None, "", [], {}):
                errors.append(f"{prefix} passed status missing evidence.{field}")
        for field in ("model_sha256", "dataset_sha256", "report_sha256",
                      "configuration_sha256", "route_inventory_sha256",
                      "storage_cdn_configuration_sha256", "dependency_sbom_sha256",
                      "protocol_sha256", "results_sha256", "service_inventory_sha256",
                      "data_flow_sha256"):
            value = evidence.get(field)
            if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                errors.append(f"{prefix} evidence.{field} must be a lowercase SHA-256 digest")
        release = evidence.get("verified_release_sha")
        if not isinstance(release, str) or not SHA1.fullmatch(release):
            errors.append(f"{prefix} evidence.verified_release_sha must be a full commit SHA")
        reviewed = _timestamp(evidence.get("reviewed_at"))
        expires = _timestamp(evidence.get("expires_at"))
        if reviewed is None:
            errors.append(f"{prefix} evidence.reviewed_at must be timezone-aware ISO-8601")
        if expires is None:
            errors.append(f"{prefix} evidence.expires_at must be timezone-aware ISO-8601")
        if reviewed is not None and expires is not None and expires <= reviewed:
            errors.append(f"{prefix} evidence.expires_at must follow reviewed_at")
        if expires is not None and expires <= datetime.now(timezone.utc):
            errors.append(f"{prefix} evidence has expired")
        refs = evidence.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(not _ref(value) for value in refs):
            errors.append(f"{prefix} evidence.evidence_refs must contain https:// or evidence:// references")
        if evidence.get("operator") and evidence.get("independent_approver") == evidence.get("operator"):
            errors.append(f"{prefix} operator and independent_approver must be different")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    try:
        document = json.loads(args.ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid evidence ledger: {exc}")
        return 2
    errors = validate(document)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"external evidence ledger valid: {len(document['workstreams'])} workstreams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

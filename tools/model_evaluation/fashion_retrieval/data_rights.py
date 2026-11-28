#!/usr/bin/env python3
"""Fail-closed validation of recorded rights approvals for benchmark inputs.

This validator checks evidence records and file integrity. It is not legal advice
and cannot establish that an approval is authentic or legally sufficient.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = {
    "schema_version", "approval_status", "scope", "reviewed_by", "reviewer_role",
    "reviewed_at_utc", "source_provenance", "evidence_path", "evidence_sha256",
    "commercial_evaluation_permitted", "human_review_permitted", "retention_until",
    "contains_personal_images", "depicted_person_consent_status",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_data_rights_manifest(value: Any, manifest_path: str | Path, *, expected_scope: str = "fashion_retrieval_evaluation") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("data-rights manifest must be a JSON object")
    missing = sorted(REQUIRED - set(value))
    if missing:
        raise ValueError(f"data-rights manifest missing required fields: {', '.join(missing)}")
    if value["schema_version"] != "1.0":
        raise ValueError("data-rights schema_version must be 1.0")
    if value["approval_status"] != "approved":
        raise ValueError("data-rights approval_status must be 'approved'; evaluation is blocked")
    if value["scope"] != expected_scope:
        raise ValueError(f"data-rights scope must be {expected_scope}")
    for field in ("reviewed_by", "reviewer_role", "source_provenance"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"data-rights {field} must be a non-empty string")
    try:
        reviewed = datetime.fromisoformat(str(value["reviewed_at_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at_utc must be an ISO-8601 timestamp") from exc
    if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
        raise ValueError("reviewed_at_utc must include a timezone and cannot be in the future")
    if value["commercial_evaluation_permitted"] is not True:
        raise ValueError("commercial evaluation permission is not approved")
    if value["human_review_permitted"] is not True:
        raise ValueError("human review permission is not approved")
    if not isinstance(value["contains_personal_images"], bool):
        raise ValueError("contains_personal_images must be boolean")
    consent = value["depicted_person_consent_status"]
    if consent not in {"verified", "not_applicable"}:
        raise ValueError("depicted-person consent must be verified or not_applicable")
    if value["contains_personal_images"] and consent != "verified":
        raise ValueError("personal images require verified depicted-person consent")
    if not value["contains_personal_images"] and consent != "not_applicable":
        raise ValueError("non-personal datasets must set depicted_person_consent_status=not_applicable")
    try:
        retention_until = date.fromisoformat(value["retention_until"])
    except (TypeError, ValueError) as exc:
        raise ValueError("retention_until must be an ISO date (YYYY-MM-DD)") from exc
    if retention_until < datetime.now(timezone.utc).date():
        raise ValueError("data-rights retention approval has expired")
    evidence_digest = value["evidence_sha256"]
    if not isinstance(evidence_digest, str) or not SHA256.fullmatch(evidence_digest):
        raise ValueError("evidence_sha256 must be a full lowercase SHA-256 digest")
    evidence_value = value["evidence_path"]
    if not isinstance(evidence_value, str) or not evidence_value.strip():
        raise ValueError("evidence_path must be a non-empty path")
    evidence_path = Path(evidence_value).expanduser()
    if not evidence_path.is_absolute():
        evidence_path = Path(manifest_path).expanduser().resolve().parent / evidence_path
    evidence_path = evidence_path.resolve()
    if not evidence_path.is_file():
        raise ValueError("rights approval evidence file is missing")
    if sha256_file(evidence_path) != evidence_digest:
        raise ValueError("rights approval evidence SHA-256 mismatch")
    return {**value, "evidence_path": str(evidence_path), "manifest_sha256": sha256_file(manifest_path)}


def load_and_validate_data_rights_manifest(path: str | Path, *, expected_scope: str = "fashion_retrieval_evaluation") -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid data-rights JSON: {exc.msg}") from exc
    return validate_data_rights_manifest(value, manifest_path, expected_scope=expected_scope)


def rights_manifest_summary(rights: dict[str, Any]) -> dict[str, str]:
    """Persist minimal approval provenance without reviewer IDs or evidence paths."""
    return {
        "manifest_sha256": rights["manifest_sha256"],
        "evidence_sha256": rights["evidence_sha256"],
        "approval_status": rights["approval_status"],
        "scope": rights["scope"],
        "retention_until": rights["retention_until"],
    }

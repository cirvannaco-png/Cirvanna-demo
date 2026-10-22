"""Signed model-release evidence gate.

This verifies an operator-approved validation report against the exact model
artifact. It cannot replace the scientific review that produced the report.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from .model_adapter import ModelConfigurationError

_SIGNATURE_RE = re.compile(r"^[a-f0-9]{64}$")
_REQUIRED_GATES = (
    "license_and_rights_review",
    "overall_quality_threshold",
    "skin_tone_subgroup_review",
    "lighting_and_device_review",
    "privacy_and_security_review",
    "user_claims_review",
)
_REQUIRED_SKIN_TONE_GROUPS = ("light", "medium", "deep")
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _canonical_payload(report: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in report.items() if key != "signature"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def verify_signed_validation_report(
    report_path: str | Path,
    signing_key: str,
    *,
    model_sha256: str,
    model_version: str,
) -> dict[str, Any]:
    """Validate required evidence and HMAC authenticity for a model release report."""
    path = Path(report_path)
    if not signing_key or len(signing_key) < 32:
        raise ModelConfigurationError("Validation report signing key is missing or too short.")
    if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ModelConfigurationError("Signed validation report is missing or oversized.")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelConfigurationError("Validation report is not valid UTF-8 JSON.") from exc
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ModelConfigurationError("Unsupported validation report schema.")
    if report.get("decision") != "approved":
        raise ModelConfigurationError("Model validation report is not approved.")
    if report.get("model_sha256") != model_sha256 or report.get("model_version") != model_version:
        raise ModelConfigurationError("Validation report does not match the loaded model.")
    if not isinstance(report.get("report_id"), str) or not report["report_id"].strip():
        raise ModelConfigurationError("Validation report ID is required.")
    if not isinstance(report.get("dataset_version"), str) or not report["dataset_version"].strip():
        raise ModelConfigurationError("Evaluation dataset version is required.")
    sample_count = report.get("evaluation_sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count <= 0:
        raise ModelConfigurationError("A positive evaluation sample count is required.")

    overall = report.get("overall_metrics")
    if not isinstance(overall, dict) or not overall:
        raise ModelConfigurationError("Overall evaluation metrics are required.")
    if any(not isinstance(v, (int, float)) or not 0 <= float(v) <= 1 for v in overall.values()):
        raise ModelConfigurationError("Overall metrics must be numeric values from 0 to 1.")

    groups = report.get("skin_tone_subgroups")
    if not isinstance(groups, dict) or not set(_REQUIRED_SKIN_TONE_GROUPS).issubset(groups):
        raise ModelConfigurationError("Light, medium, and deep skin-tone subgroup results are required.")
    for group_name in _REQUIRED_SKIN_TONE_GROUPS:
        group = groups[group_name]
        if not isinstance(group, dict):
            raise ModelConfigurationError(f"Subgroup report for {group_name} is invalid.")
        group_count = group.get("sample_count")
        if not isinstance(group_count, int) or isinstance(group_count, bool) or group_count <= 0:
            raise ModelConfigurationError(f"Subgroup sample count for {group_name} must be positive.")
        metrics = group.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            raise ModelConfigurationError(f"Subgroup metrics for {group_name} are required.")
        if any(not isinstance(v, (int, float)) or not 0 <= float(v) <= 1 for v in metrics.values()):
            raise ModelConfigurationError(f"Subgroup metrics for {group_name} must be between 0 and 1.")

    gates = report.get("release_gates")
    if not isinstance(gates, dict) or any(gates.get(name) is not True for name in _REQUIRED_GATES):
        raise ModelConfigurationError("One or more model release review gates have not passed.")

    signature = report.get("signature")
    if not isinstance(signature, str) or not _SIGNATURE_RE.fullmatch(signature):
        raise ModelConfigurationError("Validation report signature is missing or malformed.")
    try:
        expected = hmac.new(
            signing_key.encode("utf-8"), _canonical_payload(report), hashlib.sha256
        ).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ModelConfigurationError("Validation report cannot be canonicalized.") from exc
    if not hmac.compare_digest(signature, expected):
        raise ModelConfigurationError("Validation report signature is invalid.")
    return report

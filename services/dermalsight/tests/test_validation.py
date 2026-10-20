from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.model_adapter import ModelConfigurationError
from app.validation import verify_signed_validation_report

KEY = "test-validation-signing-key-that-is-long-enough-12345"
MODEL_SHA = hashlib.sha256(b"model bytes").hexdigest()


def make_report() -> dict:
    group_metrics = {"metrics": {"macro_f1": 0.82}}
    return {
        "schema_version": 1,
        "report_id": "review-2026-01",
        "decision": "approved",
        "model_version": "1.0.0",
        "model_sha256": MODEL_SHA,
        "dataset_version": "independent-eval-set-1",
        "evaluation_sample_count": 300,
        "overall_metrics": {"macro_f1": 0.82},
        "skin_tone_subgroups": {
            "light": {"sample_count": 100, **group_metrics},
            "medium": {"sample_count": 100, **group_metrics},
            "deep": {"sample_count": 100, **group_metrics},
        },
        "release_gates": {
            "license_and_rights_review": True,
            "overall_quality_threshold": True,
            "skin_tone_subgroup_review": True,
            "lighting_and_device_review": True,
            "privacy_and_security_review": True,
            "user_claims_review": True,
        },
        "signature": "",
    }


def write_signed_report(path: Path, report: dict, key: str = KEY) -> None:
    unsigned = {name: value for name, value in report.items() if name != "signature"}
    payload = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    report["signature"] = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    path.write_text(json.dumps(report), encoding="utf-8")


def test_signed_validation_report_must_match_artifact_and_pass_all_gates(tmp_path):
    path = tmp_path / "validation.json"
    report = make_report()
    write_signed_report(path, report)
    checked = verify_signed_validation_report(
        path, KEY, model_sha256=MODEL_SHA, model_version="1.0.0"
    )
    assert checked["decision"] == "approved"


def test_signed_validation_report_rejects_wrong_model_hash(tmp_path):
    path = tmp_path / "validation.json"
    write_signed_report(path, make_report())
    with pytest.raises(ModelConfigurationError, match="does not match the loaded model"):
        verify_signed_validation_report(
            path, KEY, model_sha256="0" * 64, model_version="1.0.0"
        )


def test_signed_validation_report_rejects_missing_fairness_gate(tmp_path):
    path = tmp_path / "validation.json"
    report = make_report()
    report["release_gates"]["skin_tone_subgroup_review"] = False
    write_signed_report(path, report)
    with pytest.raises(ModelConfigurationError, match="review gates"):
        verify_signed_validation_report(
            path, KEY, model_sha256=MODEL_SHA, model_version="1.0.0"
        )


def test_signed_validation_report_rejects_bad_signature(tmp_path):
    path = tmp_path / "validation.json"
    report = make_report()
    write_signed_report(path, report)
    report["overall_metrics"]["macro_f1"] = 0.99
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ModelConfigurationError, match="signature is invalid"):
        verify_signed_validation_report(
            path, KEY, model_sha256=MODEL_SHA, model_version="1.0.0"
        )


def test_signed_validation_report_requires_all_skin_tone_subgroups(tmp_path):
    path = tmp_path / "validation.json"
    report = make_report()
    del report["skin_tone_subgroups"]["deep"]
    write_signed_report(path, report)
    with pytest.raises(ModelConfigurationError, match="subgroup results are required"):
        verify_signed_validation_report(
            path, KEY, model_sha256=MODEL_SHA, model_version="1.0.0"
        )

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_external_provider_evidence import validate

ROOT = Path(__file__).resolve().parents[2]


def test_external_provider_ledger_is_valid_and_does_not_claim_unverified_completion():
    ledger = json.loads((ROOT / "docs/release/external-provider-qualification.json").read_text())
    assert validate(ledger) == []
    assert len(ledger["workstreams"]) == 10
    assert all(item["status"] == "blocked" for item in ledger["workstreams"])
    assert all(not item.get("evidence") for item in ledger["workstreams"])


def _passing_evidence():
    return {
        "provider_identity": "provider",
        "region": "region",
        "configuration_sha256": "b" * 64,
        "verified_release_sha": "a" * 40,
        "independent_reviewer": "reviewer",
        "reviewed_at": "2026-11-23T00:00:00Z",
        "expires_at": "2099-12-23T00:00:00Z",
        "evidence_refs": ["evidence://assessment/123"],
    }


def test_passed_provider_gate_requires_exact_release_independent_review_and_evidence_refs():
    ledger = json.loads((ROOT / "docs/release/external-provider-qualification.json").read_text())
    item = ledger["workstreams"][0]
    item["status"] = "passed"
    errors = validate(ledger)
    assert any("verified_release_sha" in error for error in errors)
    assert any("independent_reviewer" in error for error in errors)
    assert any("evidence_refs" in error for error in errors)


def test_digest_fields_reject_malformed_values_even_with_other_evidence():
    ledger = json.loads((ROOT / "docs/release/external-provider-qualification.json").read_text())
    item = ledger["workstreams"][0]
    item["status"] = "passed"
    item["evidence"] = _passing_evidence()
    item["evidence"]["configuration_sha256"] = "not-a-digest"
    errors = validate(ledger)
    assert any("configuration_sha256" in error for error in errors)


def test_passed_evidence_rejects_expired_or_timezone_naive_approvals():
    ledger = json.loads((ROOT / "docs/release/external-provider-qualification.json").read_text())
    item = ledger["workstreams"][0]
    item["status"] = "passed"
    item["evidence"] = _passing_evidence()
    item["evidence"]["expires_at"] = "2020-01-01T00:00:00Z"
    errors = validate(ledger)
    assert any("expired" in error for error in errors)
    item["evidence"]["expires_at"] = "2099-12-23T00:00:00"
    errors = validate(ledger)
    assert any("timezone-aware" in error for error in errors)


def test_operator_cannot_approve_their_own_rollback_exercise():
    ledger = json.loads((ROOT / "docs/release/external-provider-qualification.json").read_text())
    item = ledger["workstreams"][-1]
    item["status"] = "passed"
    item["evidence"] = {
        "incident_exercise_ref": "evidence://incident/1",
        "rollback_evidence_ref": "evidence://rollback/1",
        "restore_evidence_ref": "evidence://restore/1",
        "verified_release_sha": "a" * 40,
        "operator": "same-person",
        "independent_approver": "same-person",
        "reviewed_at": "2026-11-23T00:00:00Z",
        "expires_at": "2099-12-23T00:00:00Z",
        "evidence_refs": ["evidence://incident/1"],
    }
    errors = validate(ledger)
    assert any("operator and independent_approver must be different" in error for error in errors)

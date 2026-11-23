#!/usr/bin/env python3
"""Exercise photographed-person report/removal intake against deployed staging BFF.

Uses only a pre-provisioned synthetic asset reference. Status tokens are held in
memory and are never written to the report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


URGENT_REASONS = {"unmasked_face", "possible_minor", "nonconsensual"}
ALLOWED_RELATIONSHIPS = {"photographed_person", "parent_guardian", "authorized_representative", "other"}
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
STATUS_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{24,512}$")


class RightsSmokeError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Status tokens must never be forwarded to redirect targets.
        return None


def request(url: str, method: str, body: dict | None = None, headers: dict | None = None, timeout: int = 15):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request_headers = dict(headers or {})
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    started = time.monotonic()
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw, status = response.read(MAX_RESPONSE_BYTES + 1), response.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(MAX_RESPONSE_BYTES + 1), exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RightsSmokeError(f"{method} {url} transport failed: {type(exc).__name__}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RightsSmokeError("staging response exceeded the safety size limit")
    try:
        parsed = json.loads(raw.decode()) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = None
    return status, parsed, int((time.monotonic() - started) * 1000)


def validate(config: dict) -> None:
    if config.get("environment") != "staging":
        raise RightsSmokeError("only an explicitly configured staging environment is allowed")
    parsed = urlsplit(str(config.get("bff_base_url", "")))
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RightsSmokeError("bff_base_url must be HTTPS without embedded credentials, query or fragment")
    asset = config.get("asset_reference")
    if not isinstance(asset, str) or not 8 <= len(asset) <= 160:
        raise RightsSmokeError("asset_reference must identify a pre-provisioned synthetic staging asset")
    cases = config.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RightsSmokeError("at least one rights case is required")
    if not any(case.get("request_type") == "report" and case.get("reason_code") in URGENT_REASONS for case in cases):
        raise RightsSmokeError("at least one urgent photographed-person report is required")
    if not any(case.get("request_type") == "removal" for case in cases):
        raise RightsSmokeError("at least one removal request is required")
    for case in cases:
        if case.get("request_type") not in {"report", "removal"}:
            raise RightsSmokeError("request_type must be report or removal")
        if case.get("reason_code") not in {"unmasked_face", "possible_minor", "nonconsensual", "privacy_concern", "other"}:
            raise RightsSmokeError("unsupported rights reason_code")
        if case.get("requester_relationship") not in ALLOWED_RELATIONSHIPS:
            raise RightsSmokeError("unsupported requester_relationship")


def run(config: dict, report_path: Path) -> int:
    validate(config)
    base = config["bff_base_url"].rstrip("/")
    results, failures = [], []
    for case in config["cases"]:
        body = {
            "asset_reference": config["asset_reference"],
            "request_type": case["request_type"],
            "reason_code": case["reason_code"],
            "requester_relationship": case["requester_relationship"],
        }
        if case.get("jurisdiction_hint"):
            body["jurisdiction_hint"] = case["jurisdiction_hint"]
        status, receipt, elapsed = request(base + "/api/privacy/image-requests", "POST", body)
        urgent = case["reason_code"] in URGENT_REASONS
        if status != 202 or not isinstance(receipt, dict):
            failures.append(f"{case['request_type']}/{case['reason_code']}: intake returned HTTP {status}")
            continue
        request_id = receipt.get("request_id")
        status_token = receipt.get("status_token")
        quarantined = receipt.get("quarantined") is True
        if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
            failures.append(f"{case['request_type']}/{case['reason_code']}: request ID missing or malformed")
            continue
        if not isinstance(status_token, str) or not STATUS_TOKEN_PATTERN.fullmatch(status_token):
            failures.append(f"{case['request_type']}/{case['reason_code']}: private status token missing or malformed")
            continue
        if urgent and not quarantined:
            failures.append(f"{case['request_type']}/{case['reason_code']}: urgent intake acknowledged without confirmed quarantine")
        status_code, state, status_elapsed = request(
            base + "/api/privacy/image-requests/" + request_id,
            "GET",
            headers={"X-Privacy-Request-Token": status_token},
        )
        if status_code != 200 or not isinstance(state, dict):
            failures.append(f"{case['request_type']}/{case['reason_code']}: status retrieval returned HTTP {status_code}")
            continue
        if state.get("request_id") != request_id:
            failures.append(f"{case['request_type']}/{case['reason_code']}: status did not confirm the same request")
        if urgent and state.get("quarantined") is not True:
            failures.append(f"{case['request_type']}/{case['reason_code']}: urgent status did not confirm quarantine")
        if state.get("status") not in {"accepted", "quarantined", "under_review", "completed", "rejected", "escalated"}:
            failures.append(f"{case['request_type']}/{case['reason_code']}: unknown rights case state")
        if not isinstance(state.get("triage_due_at"), str) or state.get("deadline_basis") not in {
            "resolved_signed_jurisdiction_policy",
            "jurisdiction_policy_missing_platform_triage",
            "jurisdiction_unresolved_platform_triage",
        }:
            failures.append(f"{case['request_type']}/{case['reason_code']}: missing jurisdiction-aware triage deadline")
        results.append({
            "request_type": case["request_type"],
            "reason_code": case["reason_code"],
            "request_id": request_id,
            "intake_status": status,
            "case_status": state.get("status"),
            "quarantined": state.get("quarantined") is True,
            "deadline_basis": state.get("deadline_basis"),
            "intake_elapsed_ms": elapsed,
            "status_elapsed_ms": status_elapsed,
        })
    report = {
        "schema_version": 1,
        "environment": "staging",
        "workflow": "photographed-person-rights-intake",
        "passed": not failures,
        "case_count": len(results),
        "results": results,
        "failures": failures,
        "limitations": [
            "A 202 intake receipt and quarantine confirmation do not prove deletion completion.",
            "This runner does not verify source/derivative/replica/backup/CDN/merchant/shared-link deletion; that requires provider receipts and independent probes.",
            "This runner does not replace independent requester-authority review or legal review."
        ],
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        return run(config, args.report)
    except (OSError, json.JSONDecodeError, RightsSmokeError) as exc:
        print(f"Click It rights staging check blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

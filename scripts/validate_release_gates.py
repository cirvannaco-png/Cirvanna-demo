#!/usr/bin/env python3
"""Validate the production release evidence registry."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATES_PATH = ROOT / "docs" / "release" / "release-gates.json"
VALID_STATUSES = {"blocked", "in_progress", "passed"}
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def validate_release_gates(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("version") != 1:
        errors.append("release gate registry version must be 1")
    if document.get("repository") != "cirvannaco-png/Cirvanna-demo":
        errors.append("release gate registry repository identity mismatch")
    if document.get("release_status") not in {"blocked", "ready"}:
        errors.append("release_status must be blocked or ready")
    gates = document.get("gates")
    if not isinstance(gates, list) or not gates:
        return errors + ["gates must be a non-empty array"]

    ids: list[str] = []
    required_not_passed = 0
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            errors.append(f"gate at index {index} must be an object")
            continue
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id.strip():
            errors.append(f"gate at index {index} must have a non-empty id")
        else:
            ids.append(gate_id)
        for field in ("name", "owner_role", "acceptance"):
            if not isinstance(gate.get(field), str) or not gate[field].strip():
                errors.append(f"gate {gate_id!r} must have a non-empty {field}")
        if not isinstance(gate.get("required"), bool):
            errors.append(f"gate {gate_id!r} required must be boolean")
        status = gate.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"gate {gate_id!r} has invalid status: {status!r}")
            continue
        evidence = gate.get("evidence_refs")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            errors.append(f"gate {gate_id!r} evidence_refs must be an array of non-empty strings")
            evidence = []
        verified_commit = gate.get("verified_commit")
        if status == "passed":
            if not evidence:
                errors.append(f"passed gate {gate_id!r} must include evidence_refs")
            if not isinstance(verified_commit, str) or not FULL_SHA.fullmatch(verified_commit):
                errors.append(f"passed gate {gate_id!r} must include a full 40-character verified_commit")
        elif gate.get("required") is True:
            required_not_passed += 1
    if len(ids) != len(set(ids)):
        errors.append("gate ids must be unique")
    if document.get("release_status") == "ready" and required_not_passed:
        errors.append("release_status cannot be ready while required gates are not passed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-all-passed", action="store_true",
                        help="fail unless every required gate is passed with evidence")
    parser.add_argument("--gates", type=Path, default=GATES_PATH)
    args = parser.parse_args()

    try:
        document = json.loads(args.gates.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load release gate registry: {exc}")
        return 1

    errors = validate_release_gates(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    gates = document["gates"]
    blocked = [
        gate["id"] for gate in gates
        if gate.get("required") is True and gate.get("status") != "passed"
    ]
    if args.require_all_passed and blocked:
        print("BLOCKED: required release gates remain open: " + ", ".join(blocked))
        return 2
    print(f"OK: {len(gates)} release gates are structurally valid; "
          f"{len(blocked)} required gates remain open.")
    if blocked:
        print("Production release remains blocked. Use --require-all-passed for the release check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

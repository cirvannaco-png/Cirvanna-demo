#!/usr/bin/env python3
"""Run the frozen outfit evaluator overall and separately for each PNELLY role."""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

from evaluate_outfits import evaluate


def read_cases(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: case must be a JSON object")
            rows.append(value)
    return rows


def _run_evaluator(records: list[dict[str, Any]], k: int) -> dict[str, Any]:
    parameters = inspect.signature(evaluate).parameters
    if "k" in parameters:
        return evaluate(records, k=k)
    if "top_k" in parameters:
        return evaluate(records, top_k=k)
    return evaluate(records)


def evaluate_by_role(records: list[dict[str, Any]], *, k: int = 3) -> dict[str, Any]:
    overall = _run_evaluator(records, k)
    by_role: dict[str, Any] = {}
    for role in ("everyday", "elevated", "explore"):
        subset = [
            record for record in records
            if record.get("context", {}).get("role") == role
        ]
        if subset:
            by_role[role] = _run_evaluator(subset, k)
    return {
        "status": overall.get("status", "unknown"),
        "overall": overall,
        "by_role": by_role,
        "case_count": len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Prepared JSONL from prepare_pnelly_cases.py")
    parser.add_argument("--output", required=True, help="JSON report path")
    parser.add_argument("--summary", help="Optional trace summary from prepare_pnelly_cases.py")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    if args.k < 1:
        raise ValueError("--k must be positive")
    records = read_cases(args.cases)
    if not records:
        raise ValueError("no evaluator cases found")
    report = evaluate_by_role(records, k=args.k)
    summary_path = Path(args.summary) if args.summary else Path(str(args.cases) + ".summary.json")
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        trace_count = int(summary.get("trace_count", 0))
        no_results = summary.get("no_result_roles_by_role", {})
        report["trace_summary"] = summary
        report["no_result_rate_by_role"] = {
            role: (int(no_results.get(role, 0)) / trace_count if trace_count else None)
            for role in ("everyday", "elevated", "explore")
        }
    else:
        report["trace_summary"] = None
        report["no_result_rate_by_role"] = None
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

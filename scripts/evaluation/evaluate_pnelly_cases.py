#!/usr/bin/env python3
"""Run the frozen outfit evaluator overall and separately for each PNELLY role."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluate_outfits import evaluate, load_jsonl


def evaluate_by_role(records: list[dict[str, Any]], *, k: int = 3) -> dict[str, Any]:
    overall = evaluate(records, k=k)
    by_role: dict[str, Any] = {}
    for role in ("everyday", "elevated", "explore"):
        subset = [
            record for record in records
            if record.get("context", {}).get("role") == role
        ]
        if subset:
            by_role[role] = evaluate(subset, k=k)
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
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    records = load_jsonl(args.cases)
    report = evaluate_by_role(records, k=args.k)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

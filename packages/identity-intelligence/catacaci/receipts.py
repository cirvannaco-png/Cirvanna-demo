"""Append-only PostgreSQL persistence for privacy-minimized CaTaCaCi decision receipts."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


class DecisionReceiptStoreError(RuntimeError):
    pass


def _database_url() -> str:
    value = os.getenv("DECISION_AUDIT_DATABASE_URL", "").strip()
    if not value:
        raise DecisionReceiptStoreError("DECISION_AUDIT_DATABASE_URL is not configured")
    if not value.startswith(("postgresql://", "postgres://")):
        raise DecisionReceiptStoreError("decision receipt store requires PostgreSQL")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def persist_decision_receipt(receipt: dict[str, Any]) -> dict[str, str]:
    """Persist a versioned receipt before any SHOW/BLOCK/REVIEW response is released."""
    if not isinstance(receipt, dict):
        raise DecisionReceiptStoreError("receipt must be an object")
    required = {
        "request_id", "candidate_id", "verdict", "may_display", "eepl_policy_id",
        "eepl_policy_version", "cal_policy_id", "cal_policy_version",
        "minimum_fit_confidence", "maximum_fit_confidence_disagreement",
        "arbitration_contract_version", "pipeline_contract_version",
        "candidate_snapshot_sha256", "catalog_version", "evaluated_signals", "reasons",
    }
    if set(receipt) != required:
        raise DecisionReceiptStoreError("receipt fields do not match the canonical schema")
    for field in ("minimum_fit_confidence", "maximum_fit_confidence_disagreement"):
        value = receipt[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise DecisionReceiptStoreError(f"{field} must be numeric and within [0, 1]")
    if receipt["verdict"] not in {"SHOW", "BLOCK", "REVIEW"}:
        raise DecisionReceiptStoreError("invalid final verdict")
    if type(receipt["may_display"]) is not bool or receipt["may_display"] != (receipt["verdict"] == "SHOW"):
        raise DecisionReceiptStoreError("may_display must exactly match final SHOW")
    if (
        not isinstance(receipt["candidate_snapshot_sha256"], str)
        or len(receipt["candidate_snapshot_sha256"]) != 64
        or any(ch not in "0123456789abcdef" for ch in receipt["candidate_snapshot_sha256"])
    ):
        raise DecisionReceiptStoreError("candidate snapshot digest must be lowercase SHA-256")
    if receipt["catalog_version"] is not None and (
        type(receipt["catalog_version"]) is not int or receipt["catalog_version"] < 1
    ):
        raise DecisionReceiptStoreError("catalog_version must be a positive integer or null")
    if not isinstance(receipt["evaluated_signals"], list) or not isinstance(receipt["reasons"], list):
        raise DecisionReceiptStoreError("signal and reason evidence must be arrays")
    signal_keys = {"signal_id", "kind", "state", "required", "confidence", "reason_code", "source_version"}
    for signal in receipt["evaluated_signals"]:
        if not isinstance(signal, dict) or set(signal) != signal_keys:
            raise DecisionReceiptStoreError("evaluated signal does not match the canonical schema")
        if signal["state"] not in {"pass", "block", "unknown"} or type(signal["required"]) is not bool:
            raise DecisionReceiptStoreError("evaluated signal state/required flag is invalid")
        if signal["confidence"] is not None and (
            isinstance(signal["confidence"], bool)
            or not isinstance(signal["confidence"], (int, float))
            or not 0 <= signal["confidence"] <= 1
        ):
            raise DecisionReceiptStoreError("evaluated signal confidence is invalid")
    for reason in receipt["reasons"]:
        if not isinstance(reason, dict) or set(reason) != {"code", "signal_id"}:
            raise DecisionReceiptStoreError("decision reason does not match the canonical schema")
    body = dict(receipt)
    receipt_hash = hashlib.sha256(_canonical(body)).hexdigest()
    receipt_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    try:
        import psycopg
    except ImportError as exc:
        raise DecisionReceiptStoreError("psycopg driver is not installed") from exc
    try:
        with psycopg.connect(_database_url()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO catacaci_decision_receipts (
                        receipt_id, request_id, candidate_id, verdict, may_display,
                        eepl_policy_id, eepl_policy_version, cal_policy_id, cal_policy_version,
                        minimum_fit_confidence, maximum_fit_confidence_disagreement,
                        arbitration_contract_version, pipeline_contract_version,
                        candidate_snapshot_sha256, catalog_version, evaluated_signals, reasons,
                        receipt_sha256, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
                    )
                    ON CONFLICT (request_id, candidate_id) DO NOTHING
                    """,
                    (
                        receipt_id, receipt["request_id"], receipt["candidate_id"],
                        receipt["verdict"], receipt["may_display"],
                        receipt["eepl_policy_id"], receipt["eepl_policy_version"],
                        receipt["cal_policy_id"], receipt["cal_policy_version"],
                        receipt["minimum_fit_confidence"], receipt["maximum_fit_confidence_disagreement"],
                        receipt["arbitration_contract_version"], receipt["pipeline_contract_version"],
                        receipt["candidate_snapshot_sha256"], receipt["catalog_version"],
                        json.dumps(receipt["evaluated_signals"], separators=(",", ":"), allow_nan=False),
                        json.dumps(receipt["reasons"], separators=(",", ":"), allow_nan=False),
                        receipt_hash, created_at,
                    ),
                )
                cursor.execute(
                    "SELECT receipt_sha256 FROM catacaci_decision_receipts WHERE request_id=%s AND candidate_id=%s",
                    (receipt["request_id"], receipt["candidate_id"]),
                )
                row = cursor.fetchone()
                if row is None or row[0] != receipt_hash:
                    raise DecisionReceiptStoreError("decision receipt replay conflicts with the original evidence")
    except DecisionReceiptStoreError:
        raise
    except Exception as exc:
        raise DecisionReceiptStoreError("durable decision receipt persistence failed") from exc
    return {"receipt_id": receipt_id, "receipt_sha256": receipt_hash, "created_at": created_at.isoformat()}


def check_receipt_store() -> bool:
    try:
        import psycopg
        with psycopg.connect(_database_url(), connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM catacaci_decision_receipts LIMIT 1")
                cursor.fetchone()
        return True
    except Exception:
        return False



def load_decision_receipt(request_id: str, candidate_id: str) -> dict[str, Any]:
    """Load the exact immutable baseline used for deterministic CAM replay."""
    try:
        import psycopg
        with psycopg.connect(_database_url(), connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT verdict, eepl_policy_id, eepl_policy_version, cal_policy_id,
                    cal_policy_version, minimum_fit_confidence, maximum_fit_confidence_disagreement,
                    arbitration_contract_version, pipeline_contract_version,
                    candidate_snapshot_sha256, catalog_version, evaluated_signals, reasons,
                    receipt_sha256
                    FROM catacaci_decision_receipts WHERE request_id=%s AND candidate_id=%s""",
                    (request_id, candidate_id),
                )
                row = cursor.fetchone()
        if row is None:
            raise DecisionReceiptStoreError("CAM baseline decision receipt was not found")
        return {
            "request_id": request_id, "candidate_id": candidate_id,
            "verdict": row[0], "eepl_policy_id": row[1], "eepl_policy_version": row[2],
            "cal_policy_id": row[3], "cal_policy_version": row[4],
            "minimum_fit_confidence": float(row[5]),
            "maximum_fit_confidence_disagreement": float(row[6]),
            "arbitration_contract_version": row[7], "pipeline_contract_version": row[8],
            "candidate_snapshot_sha256": row[9], "catalog_version": row[10],
            "evaluated_signals": row[11] if isinstance(row[11], list) else json.loads(row[11]),
            "reasons": row[12] if isinstance(row[12], list) else json.loads(row[12]),
            "receipt_sha256": row[13],
        }
    except DecisionReceiptStoreError:
        raise
    except Exception as exc:
        raise DecisionReceiptStoreError("CAM baseline receipt lookup failed") from exc

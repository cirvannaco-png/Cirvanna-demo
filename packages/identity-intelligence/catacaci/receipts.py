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
        "arbitration_contract_version", "pipeline_contract_version",
        "candidate_snapshot_sha256", "evaluated_signals", "reasons",
    }
    if set(receipt) != required:
        raise DecisionReceiptStoreError("receipt fields do not match the canonical schema")
    if receipt["verdict"] not in {"SHOW", "BLOCK", "REVIEW"}:
        raise DecisionReceiptStoreError("invalid final verdict")
    if type(receipt["may_display"]) is not bool or receipt["may_display"] != (receipt["verdict"] == "SHOW"):
        raise DecisionReceiptStoreError("may_display must exactly match final SHOW")
    if not isinstance(receipt["evaluated_signals"], list) or not isinstance(receipt["reasons"], list):
        raise DecisionReceiptStoreError("signal and reason evidence must be arrays")
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
                        arbitration_contract_version, pipeline_contract_version,
                        candidate_snapshot_sha256, evaluated_signals, reasons,
                        receipt_sha256, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s
                    )
                    ON CONFLICT (request_id, candidate_id) DO NOTHING
                    """,
                    (
                        receipt_id, receipt["request_id"], receipt["candidate_id"],
                        receipt["verdict"], receipt["may_display"],
                        receipt["eepl_policy_id"], receipt["eepl_policy_version"],
                        receipt["cal_policy_id"], receipt["cal_policy_version"],
                        receipt["arbitration_contract_version"], receipt["pipeline_contract_version"],
                        receipt["candidate_snapshot_sha256"],
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

"""Durable CAM, privacy-budgeted CIL, and two-person VSL governance workflows."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .vsl import ValueChangeProposal, ValueDimension, ValueProfile, approve_change


class GovernanceStoreError(RuntimeError):
    pass


def _database_url() -> str:
    value = os.getenv("DECISION_AUDIT_DATABASE_URL", "").strip()
    if not value.startswith(("postgresql://", "postgres://")):
        raise GovernanceStoreError("PostgreSQL governance store is not configured")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _connect():
    try:
        import psycopg
        return psycopg.connect(_database_url())
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("governance database connection failed") from exc


def append_cam_audit(audit: dict[str, Any]) -> dict[str, str]:
    required = {
        "audit_id", "request_id", "candidate_id", "observed_verdict",
        "simulated_verdict", "changed_signal_ids", "policy_version",
        "replay_version", "evaluated_at", "interpretation",
    }
    if not isinstance(audit, dict) or set(audit) != required:
        raise GovernanceStoreError("CAM audit does not match the canonical contract")
    if audit["observed_verdict"] not in {"show", "block", "review"} or audit["simulated_verdict"] not in {"show", "block", "review"}:
        raise GovernanceStoreError("CAM verdict is invalid")
    changed = audit["changed_signal_ids"]
    if not isinstance(changed, list) or any(not isinstance(x, str) or not x.strip() for x in changed) or len(changed) != len(set(changed)):
        raise GovernanceStoreError("CAM changed signal IDs must be unique non-empty strings")
    digest = _hash(audit)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO catacaci_cam_audits
                (audit_id, request_id, candidate_id, observed_verdict, simulated_verdict,
                 changed_signal_ids, policy_version, replay_version, evaluated_at,
                 interpretation, audit_sha256)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                ON CONFLICT (audit_id) DO NOTHING""",
                (audit["audit_id"], audit["request_id"], audit["candidate_id"],
                 audit["observed_verdict"], audit["simulated_verdict"], _json(changed),
                 audit["policy_version"], audit["replay_version"], audit["evaluated_at"],
                 audit["interpretation"], digest),
            )
            cur.execute("SELECT audit_sha256 FROM catacaci_cam_audits WHERE audit_id=%s", (audit["audit_id"],))
            row = cur.fetchone()
            if row is None or row[0] != digest:
                raise GovernanceStoreError("CAM audit ID replay conflicts with prior evidence")
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("CAM audit persistence failed") from exc
    return {"audit_id": audit["audit_id"], "audit_sha256": digest}


def _cohort_period(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceStoreError("CIL period_start must be an ISO date") from exc
    if parsed.day != 1:
        raise GovernanceStoreError("CIL period_start must be the first day of a UTC month")
    return parsed


def record_cil_contribution(
    *, event_id: str, contributor_token: str, cohort_key: str,
    outcome_success: bool, observed_at: datetime,
) -> bool:
    if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", event_id):
        raise GovernanceStoreError("CIL event ID is invalid")
    if not isinstance(contributor_token, str) or not re.fullmatch(r"hmac-sha256:[0-9a-f]{64}", contributor_token):
        raise GovernanceStoreError("CIL requires an HMAC-pseudonymous contributor token")
    if not isinstance(cohort_key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._:=|/-]{1,127}", cohort_key):
        raise GovernanceStoreError("CIL cohort key is not an approved low-cardinality key")
    if type(outcome_success) is not bool:
        raise GovernanceStoreError("CIL outcome must be boolean")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise GovernanceStoreError("CIL observation time must be timezone-aware")
    period = date(observed_at.astimezone(timezone.utc).year, observed_at.astimezone(timezone.utc).month, 1)
    contributor_hash = hashlib.sha256(contributor_token.encode("utf-8")).hexdigest()
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO catacaci_cil_contributions
                (event_id, cohort_key, period_start, contributor_hash, outcome_success, observed_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING event_id""",
                (event_id, cohort_key, period, contributor_hash, outcome_success, observed_at.astimezone(timezone.utc)),
            )
            inserted = cur.fetchone() is not None
            if not inserted:
                cur.execute(
                    """SELECT cohort_key, period_start, contributor_hash, outcome_success
                    FROM catacaci_cil_contributions WHERE event_id=%s""",
                    (event_id,),
                )
                existing = cur.fetchone()
                if existing is not None and existing != (cohort_key, period, contributor_hash, outcome_success):
                    raise GovernanceStoreError("CIL event replay conflicts with prior contribution")
            return inserted
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("CIL contribution persistence failed") from exc


def _laplace(scale: float) -> float:
    # Inverse-CDF sampling from a cryptographically seeded uniform source.
    u = secrets.SystemRandom().random() - 0.5
    return -scale * math.copysign(math.log1p(-2.0 * abs(u)), u)


def release_cil_aggregate(
    *, cohort_key: str, period_start: str, epsilon: float = 0.5,
    minimum_contributors: int = 30, epsilon_limit: float = 1.0,
) -> dict[str, Any]:
    period = _cohort_period(period_start)
    if not isinstance(cohort_key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._:=|/-]{1,127}", cohort_key):
        raise GovernanceStoreError("CIL cohort key is invalid")
    for name, value in (("epsilon", epsilon), ("epsilon_limit", epsilon_limit)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise GovernanceStoreError(f"{name} must be finite and positive")
    if type(minimum_contributors) is not int or minimum_contributors < 30:
        raise GovernanceStoreError("CIL minimum contributor threshold cannot be below 30")
    if epsilon > epsilon_limit:
        raise GovernanceStoreError("CIL per-release epsilon exceeds the configured budget")
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT suppressed, noisy_contributor_count, noisy_success_rate, epsilon
                FROM catacaci_cil_aggregates WHERE cohort_key=%s AND period_start=%s""",
                (cohort_key, period),
            )
            existing = cur.fetchone()
            if existing is not None:
                return {
                    "cohort_key": cohort_key, "period_start": period.isoformat(),
                    "suppressed": existing[0], "contributor_count": existing[1],
                    "success_rate": existing[2], "epsilon": float(existing[3]),
                    "mechanism": "laplace-vector-count-and-successes-v1",
                }
            cur.execute(
                """INSERT INTO catacaci_cil_privacy_budget
                (cohort_key, period_start, epsilon_spent, epsilon_limit)
                VALUES (%s,%s,0,%s) ON CONFLICT DO NOTHING""",
                (cohort_key, period, epsilon_limit),
            )
            cur.execute(
                """SELECT epsilon_spent, epsilon_limit FROM catacaci_cil_privacy_budget
                WHERE cohort_key=%s AND period_start=%s FOR UPDATE""",
                (cohort_key, period),
            )
            spent, limit_value = cur.fetchone()
            # Serialize one release per cohort-month under the locked budget row.
            cur.execute(
                """SELECT suppressed, noisy_contributor_count, noisy_success_rate, epsilon
                FROM catacaci_cil_aggregates WHERE cohort_key=%s AND period_start=%s""",
                (cohort_key, period),
            )
            existing = cur.fetchone()
            if existing is not None:
                return {
                    "cohort_key": cohort_key, "period_start": period.isoformat(),
                    "suppressed": existing[0], "contributor_count": existing[1],
                    "success_rate": existing[2], "epsilon": float(existing[3]),
                    "mechanism": "laplace-vector-count-and-successes-v1",
                }
            if float(spent) + float(epsilon) > min(float(limit_value), float(epsilon_limit)) + 1e-12:
                raise GovernanceStoreError("CIL cohort-period privacy budget is exhausted")
            cur.execute(
                """SELECT COUNT(*), COALESCE(SUM(CASE WHEN outcome_success THEN 1 ELSE 0 END),0)
                FROM catacaci_cil_contributions WHERE cohort_key=%s AND period_start=%s""",
                (cohort_key, period),
            )
            count, successes = cur.fetchone()
            # Each contributor adds one binary record; the vector (count, successes)
            # has L1 sensitivity 2. Independent Laplace noise at 2/epsilon is epsilon-DP.
            scale = 2.0 / float(epsilon)
            noisy_count = max(0.0, float(count) + _laplace(scale))
            noisy_successes = float(successes) + _laplace(scale)
            suppressed = noisy_count < minimum_contributors
            public_count = None if suppressed else int(round(noisy_count))
            public_rate = None if suppressed else min(1.0, max(0.0, noisy_successes / max(noisy_count, 1.0)))
            aggregate_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO catacaci_cil_aggregates
                (aggregate_id, cohort_key, period_start, suppressed, noisy_contributor_count,
                 noisy_success_rate, epsilon, mechanism, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aggregate_id, cohort_key, period, suppressed, public_count, public_rate,
                 float(epsilon), "laplace-vector-count-and-successes-v1", datetime.now(timezone.utc)),
            )
            cur.execute(
                """UPDATE catacaci_cil_privacy_budget SET epsilon_spent=epsilon_spent+%s
                WHERE cohort_key=%s AND period_start=%s""",
                (float(epsilon), cohort_key, period),
            )
            return {
                "aggregate_id": aggregate_id, "cohort_key": cohort_key,
                "period_start": period.isoformat(), "suppressed": suppressed,
                "contributor_count": public_count, "success_rate": public_rate,
                "epsilon": float(epsilon), "mechanism": "laplace-vector-count-and-successes-v1",
            }
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("CIL private aggregation failed") from exc


def current_vsl_profile() -> dict[str, Any]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT version, priority_order, approved_by, approval_event_id FROM catacaci_vsl_profiles WHERE singleton_id=1"
            )
            row = cur.fetchone()
            if row is None:
                raise GovernanceStoreError("VSL baseline profile is not initialized")
            order = row[1] if isinstance(row[1], list) else json.loads(row[1])
            return {"version": row[0], "priority_order": order, "approved_by": row[2], "approval_event_id": row[3]}
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("VSL profile read failed") from exc


def create_vsl_proposal(
    *, proposal_id: str, base_version: str, proposed_version: str,
    proposed_order: list[str], rationale: str, proposer_id: str,
) -> dict[str, Any]:
    try:
        order = tuple(ValueDimension(value) for value in proposed_order)
        profile = current_vsl_profile()
        if profile["version"] != base_version:
            raise GovernanceStoreError("VSL proposal base version is stale")
        proposal = ValueChangeProposal(
            proposal_id=proposal_id, base_version=base_version,
            proposed_version=proposed_version, proposed_order=order,
            rationale=rationale, proposer_id=proposer_id,
        )
        digest = _hash({
            "proposal_id": proposal.proposal_id, "base_version": proposal.base_version,
            "proposed_version": proposal.proposed_version,
            "proposed_order": [x.value for x in proposal.proposed_order],
            "rationale": proposal.rationale, "proposer_id": proposal.proposer_id,
        })
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO catacaci_vsl_proposals
                (proposal_id, base_version, proposed_version, proposed_order, rationale,
                 proposer_id, proposal_sha256, status, created_at)
                VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,'proposed',%s)
                ON CONFLICT (proposal_id) DO NOTHING""",
                (proposal_id, base_version, proposed_version, _json([x.value for x in order]),
                 rationale, proposer_id, digest, datetime.now(timezone.utc)),
            )
            cur.execute("SELECT proposal_sha256,status FROM catacaci_vsl_proposals WHERE proposal_id=%s", (proposal_id,))
            row = cur.fetchone()
            if row is None or row[0] != digest:
                raise GovernanceStoreError("VSL proposal ID replay conflicts with existing proposal")
            return {"proposal_id": proposal_id, "status": row[1], "proposal_sha256": digest}
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("VSL proposal rejected or persistence failed") from exc


def approve_vsl_proposal(*, proposal_id: str, approver_id: str, approval_event_id: str) -> dict[str, Any]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT base_version, proposed_version, proposed_order, rationale, proposer_id, status
                FROM catacaci_vsl_proposals WHERE proposal_id=%s FOR UPDATE""",
                (proposal_id,),
            )
            row = cur.fetchone()
            if row is None or row[5] != "proposed":
                raise GovernanceStoreError("VSL proposal is missing or no longer pending")
            base_version, proposed_version, proposed_order, rationale, proposer_id, _ = row
            cur.execute(
                "SELECT version, priority_order FROM catacaci_vsl_profiles WHERE singleton_id=1 FOR UPDATE"
            )
            current = cur.fetchone()
            if current is None or current[0] != base_version:
                raise GovernanceStoreError("VSL proposal base version is stale")
            order_values = proposed_order if isinstance(proposed_order, list) else json.loads(proposed_order)
            approved = approve_change(
                ValueProfile(
                    version=current[0],
                    priority_order=tuple(ValueDimension(x) for x in (current[1] if isinstance(current[1], list) else json.loads(current[1]))),
                    approved_by="persisted", approval_event_id="persisted",
                ),
                ValueChangeProposal(
                    proposal_id=proposal_id, base_version=base_version,
                    proposed_version=proposed_version,
                    proposed_order=tuple(ValueDimension(x) for x in order_values),
                    rationale=rationale, proposer_id=proposer_id,
                ),
                approver_id=approver_id, approval_event_id=approval_event_id,
            )
            cur.execute(
                """UPDATE catacaci_vsl_profiles SET version=%s, priority_order=%s::jsonb,
                approved_by=%s, approval_event_id=%s, updated_at=%s WHERE singleton_id=1""",
                (approved.version, _json([x.value for x in approved.priority_order]),
                 approved.approved_by, approved.approval_event_id, datetime.now(timezone.utc)),
            )
            cur.execute(
                """UPDATE catacaci_vsl_proposals SET status='approved', approver_id=%s,
                approval_event_id=%s, decided_at=%s WHERE proposal_id=%s AND status='proposed'""",
                (approver_id, approval_event_id, datetime.now(timezone.utc), proposal_id),
            )
            cur.execute(
                """INSERT INTO catacaci_vsl_events
                (event_id, proposal_id, event_type, actor_id, base_version, resulting_version, created_at)
                VALUES (%s,%s,'approved',%s,%s,%s,%s)""",
                (approval_event_id, proposal_id, approver_id, base_version, approved.version, datetime.now(timezone.utc)),
            )
            return {"proposal_id": proposal_id, "status": "approved", "profile_version": approved.version}
    except PermissionError as exc:
        raise GovernanceStoreError("VSL proposer and approver must be different identities") from exc
    except GovernanceStoreError:
        raise
    except Exception as exc:
        raise GovernanceStoreError("VSL approval failed") from exc


def check_governance_store() -> bool:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT to_regclass('catacaci_cam_audits'),
                to_regclass('catacaci_cil_contributions'),
                to_regclass('catacaci_cil_aggregates'),
                to_regclass('catacaci_vsl_profiles'),
                to_regclass('catacaci_vsl_proposals')"""
            )
            row = cur.fetchone()
            return bool(row and all(row))
    except Exception:
        return False

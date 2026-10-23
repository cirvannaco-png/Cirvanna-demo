"""Candidate-bound, fail-closed gateway to Cirvanna's canonical CAL decision service.

The evidence provider must assemble a fresh EligibilityRequest from live, user-scoped
NPL and explicitly declared cultural requirements, plus trusted fit evidence. The BFF
never manufactures evidence and never treats retrieval scores or upstream display flags
as authorization. Only an exactly bound CAL SHOW / may_display=true response is exposed.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from typing import Any

import httpx

MAX_EVIDENCE_AGE_SECONDS = 30
MAX_EVIDENCE_TTL_SECONDS = 60
CLOCK_SKEW_SECONDS = 5
TIMEOUT_SECONDS = 5.0


def _service_config(url_key: str, token_key: str) -> tuple[str, str] | None:
    raw = os.getenv(url_key, "").strip()
    token = os.getenv(token_key, "").strip()
    if not raw or len(token.encode("utf-8")) < 32:
        return None
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        return None
    return raw.rstrip("/"), token


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def candidate_identifier(candidate: Any) -> str | None:
    """Return a stable offer/variant identifier; never use display text or a score."""
    if not isinstance(candidate, dict):
        return None
    for key in ("candidate_id", "variant_id", "offer_id", "product_id", "id"):
        value = candidate.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            value = str(value).strip()
            if value and len(value) <= 128:
                return value
    return None


def _evidence_request_is_bound(
    envelope: dict[str, Any], subject_id: str, candidate_id: str, request_id: str
) -> bool:
    issued_at = _timestamp(envelope.get("issued_at"))
    expires_at = _timestamp(envelope.get("expires_at"))
    now = datetime.now(timezone.utc)
    if issued_at is None or expires_at is None:
        return False
    if issued_at > now + timedelta(seconds=CLOCK_SKEW_SECONDS):
        return False
    if now - issued_at > timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS):
        return False
    if expires_at <= now or expires_at <= issued_at:
        return False
    if expires_at - issued_at > timedelta(seconds=MAX_EVIDENCE_TTL_SECONDS):
        return False

    # A freshly issued envelope is not enough if it merely wraps stale snapshots.
    # The trusted evidence provider must attest when it loaded each authoritative
    # source for this exact request. Each read must be recent and not future-dated.
    freshness = envelope.get("evidence_freshness")
    required_sources = (
        "npl_loaded_at",
        "cultural_requirements_loaded_at",
        "fit_estimate_generated_at",
        "candidate_attributes_loaded_at",
    )
    if not isinstance(freshness, dict):
        return False
    for source in required_sources:
        loaded_at = _timestamp(freshness.get(source))
        if loaded_at is None:
            return False
        if loaded_at > now + timedelta(seconds=CLOCK_SKEW_SECONDS):
            return False
        if now - loaded_at > timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS):
            return False

    payload = envelope.get("decision_request")
    if not isinstance(payload, dict):
        return False
    context = payload.get("context")
    profile = payload.get("usi_profile")
    fit = payload.get("fit_estimate")
    negative = payload.get("negative_preferences")
    cultural = payload.get("cultural_requirements")
    if not (
        envelope.get("request_id") == request_id
        and envelope.get("subject_id") == subject_id
        and envelope.get("candidate_id") == candidate_id
        and payload.get("request_id") == request_id
        and payload.get("candidate_id") == candidate_id
        and isinstance(context, dict)
        and context.get("user_id") == subject_id
        and isinstance(profile, dict)
        and profile.get("user_id") == subject_id
        and isinstance(fit, dict)
        and fit.get("user_id") == subject_id
        and fit.get("candidate_id") == candidate_id
        and isinstance(payload.get("candidate_attributes"), list)
        and all(isinstance(attribute, str) for attribute in payload["candidate_attributes"])
        and isinstance(negative, list)
        and isinstance(cultural, list)
    ):
        return False
    if any(not isinstance(item, dict) or item.get("user_id") != subject_id for item in negative):
        return False
    if any(not isinstance(item, dict) or item.get("user_id") != subject_id for item in cultural):
        return False
    # Signatures are verified cryptographically by the decision service, but reject
    # obviously absent/truncated signatures before spending a decision-service call.
    for field in ("npl_evidence_signature", "cultural_evidence_signature", "fit_estimate_signature"):
        signature = payload.get(field)
        if not isinstance(signature, str) or len(signature) < 64:
            return False
    return True


async def _evaluate_one(
    subject_id: str,
    candidate_id: str,
    catalog_product_id: str,
    evidence_config: tuple[str, str],
    decision_config: tuple[str, str],
) -> dict[str, Any] | None:
    evidence_base, evidence_token = evidence_config
    decision_base, decision_token = decision_config
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            evidence_response = await client.post(
                evidence_base + "/v1/decision-evidence",
                headers={"Authorization": "Bearer " + evidence_token, "Accept": "application/json"},
                json={
                    "request_id": request_id,
                    "subject_id": subject_id,
                    "candidate_id": candidate_id,
                    "catalog_product_id": catalog_product_id,
                    "requested_at": now.isoformat(),
                },
            )
            if evidence_response.status_code != 200:
                return None
            try:
                envelope = evidence_response.json()
            except ValueError:
                return None
            if not isinstance(envelope, dict) or not _evidence_request_is_bound(
                envelope, subject_id, candidate_id, request_id
            ):
                return None

            response = await client.post(
                decision_base + "/v1/eligibility/evaluate",
                headers={"Authorization": "Bearer " + decision_token, "Accept": "application/json"},
                json=envelope["decision_request"],
            )
            if response.status_code != 200:
                return None
            try:
                decision = response.json()
            except ValueError:
                return None
    except (httpx.HTTPError, ValueError, TypeError):
        return None

    arbitration = decision.get("arbitration") if isinstance(decision, dict) else None
    if not isinstance(arbitration, dict):
        return None
    if (
        decision.get("candidate_id") != candidate_id
        or arbitration.get("request_id") != request_id
        or decision.get("decision") != "SHOW"
        or decision.get("may_display") is not True
    ):
        return None
    return {
        "verdict": "SHOW",
        "may_display": True,
        "request_id": request_id,
        "policy_version": arbitration.get("policy_version"),
    }


async def govern_candidates(
    subject_id: str, candidates: list[Any]
) -> dict[str, Any]:
    """Evaluate every candidate independently and expose SHOW-only candidate objects."""
    evidence_config = _service_config("GOVERNANCE_EVIDENCE_API_URL", "GOVERNANCE_EVIDENCE_API_TOKEN")
    decision_config = _service_config("DECISION_SERVICE_API_URL", "DECISION_SERVICE_TOKEN")
    if not subject_id.strip() or evidence_config is None or decision_config is None:
        return {
            "candidate_count": 0,
            "candidates": [],
            "display_authorized": False,
            "decision_status": "PENDING_CAL",
            "governance_status": "CAL_GATE_NOT_CONNECTED",
            "scores_are_probabilities": False,
        }

    shown: list[dict[str, Any]] = []
    failed = False
    for candidate in candidates:
        candidate_id = candidate_identifier(candidate)
        if candidate_id is None or not isinstance(candidate, dict):
            failed = True
            continue
        catalog_product_id = candidate.get("catalog_product_id") or candidate.get("product_id") or candidate_id
        if not isinstance(catalog_product_id, str) or not catalog_product_id.strip() or len(catalog_product_id) > 128:
            failed = True
            continue
        approval = await _evaluate_one(subject_id, candidate_id, catalog_product_id.strip(), evidence_config, decision_config)
        if approval is None:
            # This covers BLOCK/REVIEW as well as absent, stale, mismatched, malformed,
            # timed-out or unauthenticated evidence/decision responses. None are shown.
            failed = True
            continue
        # Remove any upstream decision/authorization claims before setting values that
        # are derived solely from the verified canonical CAL response.
        safe_candidate = {
            key: value for key, value in candidate.items()
            if key not in {"display_authorized", "decision_status", "governance_status", "decision", "may_display", "cal_decision"}
        }
        safe_candidate["display_authorized"] = True
        safe_candidate["decision_status"] = "SHOW"
        safe_candidate["cal_decision"] = approval
        shown.append(safe_candidate)

    return {
        "candidate_count": len(shown),
        "candidates": shown,
        "display_authorized": bool(shown),
        "decision_status": "SHOW" if shown else "NO_SHOW",
        "governance_status": "CAL_PARTIAL_FAIL_CLOSED" if failed else "CAL_ENFORCED",
        "scores_are_probabilities": False,
    }

"""Consent-checked Wardrobe feedback delivery to canonical identity and preference services.

NPL is the only negative-preference authority. USI/TAL remains the owner of
consented positive preferences and temporal learning. CFRP/CRFP candidate code
is intentionally not imported or executed here.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx


class LearningIntegrationError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _base_url(name: str) -> str:
    raw = os.getenv(name, "").strip().rstrip("/")
    if not raw:
        raise LearningIntegrationError(f"{name}_NOT_CONFIGURED")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise LearningIntegrationError(f"{name}_INVALID") from exc
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not host or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
    ):
        raise LearningIntegrationError(f"{name}_MUST_BE_TRUSTED_HTTPS")
    return raw


def _token(name: str) -> str:
    value = os.getenv(name, "").strip()
    if len(value.encode("utf-8")) < 32:
        raise LearningIntegrationError(f"{name}_NOT_CONFIGURED")
    return value


def _request_json(
    client: httpx.Client, method: str, url: str, token: str, *,
    params: dict | None = None, payload: dict | None = None,
):
    try:
        response = client.request(
            method, url,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            params=params,
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise LearningIntegrationError("LEARNING_UPSTREAM_TIMEOUT", 504) from exc
    except httpx.HTTPError as exc:
        raise LearningIntegrationError("LEARNING_UPSTREAM_UNAVAILABLE", 503) from exc
    try:
        data = response.json() if response.content else {}
    except ValueError as exc:
        raise LearningIntegrationError("LEARNING_UPSTREAM_INVALID_RESPONSE", 502) from exc
    if response.status_code < 200 or response.status_code >= 300:
        code = "LEARNING_UPSTREAM_REJECTED" if response.status_code in {400, 401, 403, 404, 409, 422} else "LEARNING_UPSTREAM_UNAVAILABLE"
        safe_status = response.status_code if response.status_code in {403, 404, 409, 422} else 503
        raise LearningIntegrationError(code, safe_status)
    if not isinstance(data, (dict, list)):
        raise LearningIntegrationError("LEARNING_UPSTREAM_INVALID_RESPONSE", 502)
    return data


def deliver_learning_event(
    *,
    owner_user_id: str,
    item_id: str,
    item_version: int,
    display_name: str,
    category: str,
    attributes: list[str],
    event_id: str,
    signal: str,
    target_type: str | None,
    target_value: str | None,
    consent_receipt_id: str,
    observed_at: datetime,
) -> dict:
    """Write one feedback event to TAL and, for negative signals, NPL.

    The TAL event ID and NPL rejection ID are both the caller's event_id.
    Repeating a partially completed operation is therefore safe and idempotent.
    """
    identity_base = _base_url("IDENTITY_SERVICE_URL")
    identity_token = _token("IDENTITY_SERVICE_TOKEN")
    observed = observed_at.astimezone(timezone.utc)
    current = datetime.now(timezone.utc)
    if observed > current + timedelta(minutes=5) or observed < current - timedelta(days=30):
        raise LearningIntegrationError("WARDROBE_FEEDBACK_TIMESTAMP_OUT_OF_RANGE", 422)

    with httpx.Client(
        timeout=httpx.Timeout(5.0, connect=1.5),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        receipts = _request_json(
            client, "GET", f"{identity_base}/v1/tal/consents/{owner_user_id}", identity_token
        )
        if not isinstance(receipts, list):
            raise LearningIntegrationError("IDENTITY_CONSENT_RESPONSE_INVALID", 502)
        receipt = next(
            (item for item in receipts if isinstance(item, dict) and item.get("receipt_id") == consent_receipt_id),
            None,
        )
        if (
            receipt is None
            or receipt.get("scope") not in {"style_learning", "personalization"}
            or receipt.get("granted") is not True
            or receipt.get("revoked_at") is not None
        ):
            raise LearningIntegrationError("ACTIVE_STYLE_LEARNING_CONSENT_REQUIRED", 403)

        event_value = json.dumps({
            "wardrobe_item_id": item_id,
            "wardrobe_item_version": item_version,
            "display_name": display_name,
            "category": category,
            "attributes": sorted(set(attributes), key=str.casefold),
            "signal": signal,
            "target_type": target_type,
            "target_value": target_value,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        tal = _request_json(
            client, "POST", f"{identity_base}/v1/tal/events", identity_token,
            params={"subject_id": owner_user_id},
            payload={
                "event_id": event_id,
                "idempotency_key": "wardrobe:" + event_id,
                "consent_receipt_id": consent_receipt_id,
                "feature_key": "wardrobe.feedback." + signal,
                "value": event_value,
                "observed_at": observed.isoformat().replace("+00:00", "Z"),
                "expires_at": (observed + timedelta(days=180)).isoformat().replace("+00:00", "Z"),
            },
        )

        npl_result = None
        if signal in {"dislike", "avoid"} and target_type and target_value:
            npl_base = _base_url("NPL_SERVICE_URL")
            npl_token = _token("NPL_SERVICE_TOKEN")
            prefs_result = _request_json(
                client, "GET", f"{npl_base}/v1/preferences", npl_token,
                params={"user_id": owner_user_id},
            )
            if not isinstance(prefs_result, dict) or not isinstance(prefs_result.get("preferences"), list):
                raise LearningIntegrationError("NPL_PREFERENCE_RESPONSE_INVALID", 502)

            preference_id = "wardrobe-" + hashlib.sha256(
                f"{owner_user_id}|{target_type}|{target_value.strip().casefold()}".encode()
            ).hexdigest()[:32]
            expected_source = "user_declared" if signal == "avoid" else "learned_rejection"
            existing = next(
                (item for item in prefs_result["preferences"]
                 if isinstance(item, dict) and item.get("preference_id") == preference_id),
                None,
            )
            if existing is not None:
                if (
                    existing.get("target_type") != target_type
                    or str(existing.get("target_value", "")).casefold() != target_value.casefold()
                    or existing.get("source") != expected_source
                ):
                    raise LearningIntegrationError("NPL_PREFERENCE_ID_COLLISION", 409)
                if existing.get("active") is not True:
                    raise LearningIntegrationError("NPL_PREFERENCE_WAS_RETRACTED", 409)
            else:
                try:
                    npl_result = _request_json(
                        client, "POST", f"{npl_base}/v1/preferences", npl_token,
                        payload={
                            "user_id": owner_user_id,
                            "preference_id": preference_id,
                            "target_type": target_type,
                            "target_value": target_value,
                            "source": expected_source,
                            "rejection_threshold": 3,
                        },
                    )
                except LearningIntegrationError as exc:
                    if exc.status_code != 409:
                        raise
                    refreshed = _request_json(
                        client, "GET", f"{npl_base}/v1/preferences", npl_token,
                        params={"user_id": owner_user_id},
                    )
                    if not any(
                        isinstance(item, dict)
                        and item.get("preference_id") == preference_id
                        and item.get("target_type") == target_type
                        and str(item.get("target_value", "")).casefold() == target_value.casefold()
                        and item.get("source") == expected_source
                        and item.get("active") is True
                        for item in refreshed.get("preferences", [])
                    ):
                        raise

            if signal == "dislike":
                npl_result = _request_json(
                    client, "POST", f"{npl_base}/v1/preferences/{preference_id}/rejections", npl_token,
                    payload={"user_id": owner_user_id, "rejection_event_id": event_id},
                )
            else:
                npl_result = {
                    "status": "recorded",
                    "source": "user_declared",
                    "hard_veto": True,
                    "preference_id": preference_id,
                }

    return {
        "tal_event_id": tal.get("event_id", event_id),
        "tal_status": tal.get("status", "recorded"),
        "npl": npl_result,
        "positive_feedback_is_advisory": signal in {"like", "wear", "modify"},
        "cfrp_or_crfp_applied": False,
    }

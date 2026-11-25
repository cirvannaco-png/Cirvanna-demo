"""Yoti AVS threshold-only client. No webhook payload is trusted as an outcome."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

SESSION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class YotiProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class YotiSession:
    session_id: str
    expires_at: str
    user_view_url: str
    reference_id: str


@dataclass(frozen=True)
class YotiThresholdResult:
    state: str
    threshold_met: bool | None
    evidence_id: str | None
    method: str | None
    updated_at: str | None


class YotiAVSClient:
    """Server-side Yoti AVS adapter with Digital ID only and no age-estimation fallback."""

    def __init__(
        self,
        api_key: str,
        sdk_id: str,
        *,
        base_url: str = "https://age.yoti.com",
        timeout_seconds: float = 8.0,
        client: httpx.Client | None = None,
    ) -> None:
        if len(api_key.encode("utf-8")) < 32:
            raise ValueError("Yoti API key is not configured")
        if not re.fullmatch(r"[A-Za-z0-9_-]{14,40}", sdk_id):
            raise ValueError("Yoti SDK ID is invalid")
        parsed = httpx.URL(base_url)
        if (
            parsed.scheme != "https"
            or parsed.host != "age.yoti.com"
            or parsed.port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Yoti API base URL must be the pinned official HTTPS origin")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 60:
            raise ValueError("Yoti request timeout must be greater than zero and at most 60 seconds")
        self._api_key = api_key
        self._sdk_id = sdk_id
        self._base_url = str(parsed).rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False, follow_redirects=False)

    def create_over_session(
        self,
        *,
        threshold: int,
        reference_id: str,
        redirect_url: str,
        cancel_url: str,
        privacy_policy_url: str,
        terms_url: str,
        ttl_seconds: int = 900,
    ) -> YotiSession:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 13 <= threshold <= 125:
            raise ValueError("age threshold must be between 13 and 125")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,96}", reference_id):
            raise ValueError("reference_id must be a random opaque token, not personal data")
        for value in (redirect_url, cancel_url, privacy_policy_url, terms_url):
            parsed = httpx.URL(value)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                raise ValueError("Yoti callback and policy URLs must use HTTPS")
        if not 60 <= ttl_seconds <= 86400:
            raise ValueError("session TTL is outside the approved range")
        body = {
            "type": "OVER",
            "digital_id": {
                "allowed": True,
                "threshold": threshold,
                "age_estimation_allowed": False,
                "retry_enabled": False,
                "retry_limit": 1,
            },
            "age_estimation": {"allowed": False},
            "doc_scan": {"allowed": False},
            "ttl": ttl_seconds,
            "reference_id": reference_id,
            "callback": {"url": redirect_url, "auto": True},
            "cancel_url": cancel_url,
            "privacy_policy": privacy_policy_url,
            "terms_and_conditions": terms_url,
            "block_biometric_consent": False,
            "synchronous_checks": True,
        }
        response = self._request("POST", "/api/v1/sessions", json=body)
        session_id = response.get("id")
        expires_at = response.get("expires_at")
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise YotiProviderError("Yoti returned an invalid session identifier")
        if not isinstance(expires_at, str):
            raise YotiProviderError("Yoti session expiry is missing")
        try:
            session_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise YotiProviderError("Yoti session expiry is invalid") from exc
        if session_expiry.tzinfo is None or session_expiry <= datetime.now(timezone.utc):
            raise YotiProviderError("Yoti session expiry must be a future timezone-aware timestamp")
        return YotiSession(
            session_id=session_id,
            expires_at=expires_at,
            user_view_url=f"https://age.yoti.com?sessionId={quote(session_id)}&sdkId={quote(self._sdk_id)}",
            reference_id=reference_id,
        )

    def get_threshold_result(
        self, *, session_id: str, expected_reference_id: str, threshold: int,
    ) -> YotiThresholdResult:
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise ValueError("invalid Yoti session identifier")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,96}", expected_reference_id):
            raise ValueError("invalid expected Yoti reference identifier")
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 13 <= threshold <= 125:
            raise ValueError("invalid Yoti age threshold")
        response = self._request("GET", f"/api/v1/sessions/{session_id}/result")
        if response.get("id") != session_id or response.get("sdk_id") != self._sdk_id:
            raise YotiProviderError("Yoti result session or SDK binding mismatch")
        if response.get("reference_id") != expected_reference_id or response.get("type") != "OVER":
            raise YotiProviderError("Yoti result reference or threshold-check type mismatch")
        digital_id = response.get("digital_id")
        if not isinstance(digital_id, dict):
            raise YotiProviderError("Yoti result does not contain the configured Digital ID method")
        if digital_id.get("allowed") is not True or digital_id.get("threshold") != threshold:
            raise YotiProviderError("Yoti result threshold or method configuration mismatch")
        expires_at = response.get("expires_at")
        if not isinstance(expires_at, str):
            raise YotiProviderError("Yoti result expiry is missing")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise YotiProviderError("Yoti result expiry is invalid") from exc
        if expiry.tzinfo is None:
            raise YotiProviderError("Yoti result expiry must include a timezone")
        if datetime.now(timezone.utc) >= expiry.astimezone(timezone.utc):
            state = "EXPIRED"
        else:
            state = response.get("status")
        if not isinstance(state, str):
            raise YotiProviderError("Yoti result status is missing or invalid")
        if state in {"COMPLETE", "FAIL"}:
            if response.get("method") != "DIGITAL_ID":
                raise YotiProviderError("Yoti did not complete the approved Digital ID method")
            if response.get("age") != threshold:
                raise YotiProviderError("Yoti threshold result does not match the configured OVER threshold")
            threshold_met: bool | None = state == "COMPLETE"
        elif state in {"PENDING", "IN_PROGRESS", "PROCESSING", "ERROR", "CANCELLED", "EXPIRED"}:
            threshold_met = None
        else:
            threshold_met = None
        evidence_id = response.get("evidence_id")
        if state in {"COMPLETE", "FAIL"} and (
            not isinstance(evidence_id, str) or not evidence_id.strip()
        ):
            raise YotiProviderError("Yoti terminal result is missing its evidence identifier")
        return YotiThresholdResult(
            state=state if isinstance(state, str) else "UNKNOWN",
            threshold_met=threshold_met,
            evidence_id=evidence_id if isinstance(evidence_id, str) else None,
            method=response.get("method") if isinstance(response.get("method"), str) else None,
            updated_at=response.get("updated_at") if isinstance(response.get("updated_at"), str) else None,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, *, json: dict | None = None) -> dict:
        try:
            response = self._client.request(
                method,
                self._base_url + path,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Yoti-Sdk-Id": self._sdk_id,
                    "Content-Type": "application/json",
                },
                json=json,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Do not forward provider bodies, credentials or document-related error detail.
            raise YotiProviderError("Yoti AVS request failed or returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise YotiProviderError("Yoti AVS returned an invalid response object")
        return result

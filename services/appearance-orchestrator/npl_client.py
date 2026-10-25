"""Authenticated read-only adapter for the canonical NPL preference ledger."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit
import httpx

from npl import NegativePreference, PreferenceSource, TargetType
from client_security import validate_internal_service_credentials


class NPLUnavailable(RuntimeError):
    """The authenticated preference service could not provide valid user state."""


class NPLClient:
    """Read canonical preferences through the internal, authenticated NPL API."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_seconds: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = validate_internal_service_credentials(
            base_url, service_token, service_name="NPL service", token_name="NPL_SERVICE_TOKEN"
        )
        self._token = service_token
        self._timeout = float(timeout_seconds)
        self._client = client

    @classmethod
    def from_env(cls) -> "NPLClient":
        import os
        return cls(os.getenv("NPL_BASE_URL", ""), os.getenv("NPL_SERVICE_TOKEN", ""))

    @staticmethod
    def _parse_preference(raw: Any, expected_user_id: str) -> NegativePreference:
        required = {
            "preference_id", "user_id", "target_type", "target_value", "source",
            "rejection_event_ids", "rejection_threshold", "active", "correction_event_id",
        }
        if not isinstance(raw, dict) or not required.issubset(raw):
            raise NPLUnavailable("NPL service returned an incomplete preference record")
        if not isinstance(raw["user_id"], str) or raw["user_id"].strip() != expected_user_id:
            raise NPLUnavailable("NPL service returned preferences outside the requested user scope")
        event_ids = raw["rejection_event_ids"]
        if not isinstance(event_ids, list) or any(not isinstance(item, str) or not item.strip() for item in event_ids):
            raise NPLUnavailable("NPL service returned invalid rejection-event identifiers")
        threshold = raw["rejection_threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise NPLUnavailable("NPL service returned an invalid rejection threshold")
        if not isinstance(raw["active"], bool):
            raise NPLUnavailable("NPL service returned an invalid active flag")
        correction_id = raw["correction_event_id"]
        if correction_id is not None and not isinstance(correction_id, str):
            raise NPLUnavailable("NPL service returned an invalid correction identifier")
        try:
            return NegativePreference(
                preference_id=raw["preference_id"],
                user_id=raw["user_id"].strip(),
                target_type=TargetType(raw["target_type"]),
                target_value=raw["target_value"],
                source=PreferenceSource(raw["source"]),
                rejection_event_ids=tuple(event_ids),
                rejection_threshold=threshold,
                active=raw["active"],
                correction_event_id=correction_id,
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise NPLUnavailable("NPL service returned an invalid preference record") from exc

    def fetch_preferences(self, user_id: str) -> tuple[NegativePreference, ...]:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be non-empty")
        requested_user = user_id.strip()
        owned = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(self._timeout, connect=min(2.0, self._timeout)),
            trust_env=False,
            follow_redirects=False,
        )
        try:
            try:
                response = client.get(
                    self.base_url + "/v1/preferences",
                    params={"user_id": requested_user},
                    headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise NPLUnavailable("canonical NPL preference request failed") from exc
            if response.status_code != 200:
                raise NPLUnavailable(f"canonical NPL service returned HTTP {response.status_code}")
            try:
                payload: Any = response.json()
            except ValueError as exc:
                raise NPLUnavailable("canonical NPL service returned invalid JSON") from exc
            if not isinstance(payload, dict) or payload.get("user_id") != requested_user:
                raise NPLUnavailable("canonical NPL response user scope does not match the request")
            rows = payload.get("preferences")
            if not isinstance(rows, list):
                raise NPLUnavailable("canonical NPL response must include a preferences array")
            preferences = tuple(self._parse_preference(row, requested_user) for row in rows)
            ids = [item.preference_id for item in preferences]
            if len(ids) != len(set(ids)):
                raise NPLUnavailable("canonical NPL response contains duplicate preference IDs")
            return preferences
        finally:
            if owned:
                client.close()

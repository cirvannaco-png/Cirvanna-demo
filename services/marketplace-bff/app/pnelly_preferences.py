"""Typed, consent-bound PNELLY preference persistence through canonical USI."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PnellyStylePreferenceIn(BaseModel):
    """A user-confirmed, bounded aesthetic preference from one PNELLY advisory."""
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    attribute: Literal[
        "style:minimalist", "style:elegant", "style:romantic", "style:bold",
        "style:streetwear", "style:classic", "style:editorial",
        "color:teal", "color:navy", "color:earthy", "color:monochrome", "color:pastel",
        "silhouette:relaxed", "silhouette:tailored", "silhouette:oversized", "silhouette:structured",
        "material:linen", "material:cotton", "material:denim", "material:silk",
        "pattern:solid", "pattern:floral", "pattern:striped", "pattern:geometric",
    ]

    @field_validator("request_id", "consent_receipt_id")
    @classmethod
    def valid_preference_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", normalized):
            raise ValueError("preference identifiers must use the controlled opaque ID format")
        return normalized


def _preference_id(subject: str, payload: PnellyStylePreferenceIn) -> str:
    digest = hashlib.sha256(
        f"{subject}|{payload.request_id}|{payload.attribute}".encode("utf-8")
    ).hexdigest()[:32]
    return "pnelly-" + digest


async def _require_exact_active_profile_receipt(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str, receipt_id: str,
) -> None:
    try:
        response = await client.get(
            base + f"/v1/tal/consents/{subject}",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_CONSENT_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_CONSENT_UNAVAILABLE"})
    try:
        receipts = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "PNELLY_PROFILE_CONSENT_RESPONSE_INVALID"}) from exc
    receipt = next((item for item in receipts if isinstance(item, dict) and item.get("receipt_id") == receipt_id), None) if isinstance(receipts, list) else None
    if (
        receipt is None or receipt.get("scope") != "profile_storage"
        or receipt.get("granted") is not True or receipt.get("revoked_at") is not None
    ):
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    expiry_raw = receipt.get("expires_at")
    if expiry_raw:
        try:
            expiry = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "PNELLY_PROFILE_CONSENT_EXPIRY_INVALID"}) from exc
        if expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})


async def _read_usi_profile(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
) -> dict:
    try:
        response = await client.get(
            base + f"/v1/profiles/{subject}",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_READ_UNAVAILABLE"}) from exc
    if response.status_code == 403:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_READ_UNAVAILABLE"})
    try:
        profile = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "PNELLY_PROFILE_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(profile, dict) or profile.get("subject_id") != subject
        or not isinstance(profile.get("preferences"), list)
        or type(profile.get("profile_version")) is not int or profile["profile_version"] < 0
    ):
        raise HTTPException(502, detail={"code": "PNELLY_PROFILE_SCOPE_OR_SCHEMA_MISMATCH"})
    return profile


def _build_preference_update(
    *, subject: str, profile: dict, payload: PnellyStylePreferenceIn,
) -> tuple[str, list[dict] | None, str | None]:
    preference_id = _preference_id(subject, payload)
    preferences = list(profile["preferences"])
    existing = next((item for item in preferences if isinstance(item, dict) and item.get("preference_id") == preference_id), None)
    if existing is not None:
        if (
            existing.get("attribute") != payload.attribute
            or existing.get("source") != "pnelly_user_confirmed"
            or existing.get("source_request_id") != payload.request_id
        ):
            raise HTTPException(409, detail={"code": "PNELLY_PREFERENCE_ID_CONFLICT"})
        return preference_id, None, "replayed"
    if any(
        isinstance(item, dict) and item.get("attribute") == payload.attribute
        and item.get("active", True) is True
        for item in preferences
    ):
        return preference_id, None, "already_present"
    if len(preferences) >= 100:
        raise HTTPException(409, detail={"code": "USI_PROFILE_PREFERENCE_LIMIT_REACHED"})
    preferences.append({
        "preference_id": preference_id,
        "attribute": payload.attribute,
        "weight": 0.8,
        "active": True,
        "source": "pnelly_user_confirmed",
        "source_request_id": payload.request_id,
    })
    return preference_id, preferences, None


async def _write_usi_profile(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    profile: dict, payload: PnellyStylePreferenceIn, preferences: list[dict],
    preference_id: str,
) -> dict:
    try:
        response = await client.put(
            base + f"/v1/profiles/{subject}",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            json={
                "expected_version": profile["profile_version"],
                "consent_receipt_id": payload.consent_receipt_id,
                "preferences": preferences,
            },
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_SAVE_UNAVAILABLE"}) from exc
    if response.status_code == 409:
        raise HTTPException(409, detail={"code": "USI_PROFILE_VERSION_CONFLICT"})
    if response.status_code == 403:
        raise HTTPException(403, detail={"code": "ACTIVE_PROFILE_STORAGE_CONSENT_REQUIRED"})
    if response.status_code == 422:
        raise HTTPException(422, detail={"code": "PNELLY_PROFILE_SAVE_REJECTED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "PNELLY_PROFILE_SAVE_UNAVAILABLE"})
    try:
        saved = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "PNELLY_PROFILE_SAVE_RESPONSE_INVALID"}) from exc
    saved_preferences = saved.get("preferences") if isinstance(saved, dict) else None
    if (
        not isinstance(saved, dict) or saved.get("subject_id") != subject
        or type(saved.get("profile_version")) is not int
        or not isinstance(saved_preferences, list)
        or not any(
            isinstance(item, dict) and item.get("preference_id") == preference_id
            and item.get("attribute") == payload.attribute
            and item.get("source") == "pnelly_user_confirmed"
            and item.get("source_request_id") == payload.request_id
            for item in saved_preferences
        )
    ):
        raise HTTPException(502, detail={"code": "PNELLY_PROFILE_SAVE_PERSISTENCE_UNCONFIRMED"})
    return {
        "status": "recorded", "preference_id": preference_id,
        "profile_version": saved["profile_version"],
        "durable_persistence": True, "learning_owner": "USI",
    }


async def save_pnelly_style_preference(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    payload: PnellyStylePreferenceIn,
) -> dict:
    """Persist one explicit preference with exact consent and optimistic versioning."""
    await _require_exact_active_profile_receipt(
        client, base=base, token=token, subject=subject,
        receipt_id=payload.consent_receipt_id,
    )
    profile = await _read_usi_profile(client, base=base, token=token, subject=subject)
    preference_id, preferences, existing_status = _build_preference_update(
        subject=subject, profile=profile, payload=payload,
    )
    if existing_status is not None:
        return {
            "status": existing_status, "preference_id": preference_id,
            "profile_version": profile["profile_version"],
            "durable_persistence": True, "learning_owner": "USI",
        }
    return await _write_usi_profile(
        client, base=base, token=token, subject=subject, profile=profile,
        payload=payload, preferences=preferences or [], preference_id=preference_id,
    )

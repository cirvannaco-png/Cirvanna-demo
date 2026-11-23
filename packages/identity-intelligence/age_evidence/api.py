"""Private Identity Learning endpoints for durable Yoti age assurance."""
from __future__ import annotations

import hmac
import os
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .core import AgeEvidenceError
from .policy import PolicyRegistryError, resolve_active_policy
from .service import AgeEvidenceService
from .store import AgeEvidenceConflict, AgeEvidenceStore
from .yoti import YotiAVSClient

router = APIRouter(prefix="/internal/v1/age-evidence", tags=["internal-age-evidence"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionStart(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="shopper_eligibility", pattern=r"^shopper_eligibility$")


class SessionOwner(StrictModel):
    subject_id: str = Field(min_length=1, max_length=128)


class AttestationRedeem(StrictModel):
    jti: str = Field(min_length=36, max_length=36)
    subject_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=80)
    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=64)
    threshold: int = Field(ge=13, le=125)
    signature: str = Field(min_length=64, max_length=128)


def _require_token(credentials: str | None, env_name: str, code: str) -> None:
    expected = os.getenv(env_name, "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": code + "_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials, expected):
        raise HTTPException(401, detail={"code": code + "_AUTH_REQUIRED"})


def require_orchestrator(authorization: Annotated[str | None, Header()] = None) -> None:
    token = authorization[7:] if isinstance(authorization, str) and authorization.startswith("Bearer ") else None
    _require_token(token, "AGE_EVIDENCE_ORCHESTRATOR_TOKEN", "AGE_EVIDENCE_ORCHESTRATOR")


def require_redemption(authorization: Annotated[str | None, Header()] = None) -> None:
    token = authorization[7:] if isinstance(authorization, str) and authorization.startswith("Bearer ") else None
    _require_token(token, "AGE_EVIDENCE_REDEMPTION_TOKEN", "AGE_EVIDENCE_REDEMPTION")


def _store() -> AgeEvidenceStore:
    url = os.getenv("IDENTITY_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "IDENTITY_DATABASE_NOT_CONFIGURED"})
    return AgeEvidenceStore(url)


def _service() -> AgeEvidenceService:
    required = {
        "YOTI_AVS_API_KEY": os.getenv("YOTI_AVS_API_KEY", ""),
        "YOTI_AVS_SDK_ID": os.getenv("YOTI_AVS_SDK_ID", ""),
        "AGE_EVIDENCE_HMAC_SECRET": os.getenv("AGE_EVIDENCE_HMAC_SECRET", ""),
        "YOTI_AVS_CALLBACK_URL": os.getenv("YOTI_AVS_CALLBACK_URL", ""),
        "YOTI_AVS_CANCEL_URL": os.getenv("YOTI_AVS_CANCEL_URL", ""),
        "YOTI_AVS_PRIVACY_POLICY_URL": os.getenv("YOTI_AVS_PRIVACY_POLICY_URL", ""),
        "YOTI_AVS_TERMS_URL": os.getenv("YOTI_AVS_TERMS_URL", ""),
    }
    if any(not value for value in required.values()):
        raise HTTPException(503, detail={"code": "AGE_EVIDENCE_PROVIDER_NOT_CONFIGURED"})
    store = _store()
    try:
        yoti = YotiAVSClient(required["YOTI_AVS_API_KEY"], required["YOTI_AVS_SDK_ID"])
        return AgeEvidenceService(
            store=store, yoti=yoti,
            signing_secret=required["AGE_EVIDENCE_HMAC_SECRET"],
            redirect_url=required["YOTI_AVS_CALLBACK_URL"],
            cancel_url=required["YOTI_AVS_CANCEL_URL"],
            privacy_policy_url=required["YOTI_AVS_PRIVACY_POLICY_URL"],
            terms_url=required["YOTI_AVS_TERMS_URL"],
        )
    except (ValueError, AgeEvidenceError) as exc:
        store.engine.dispose()
        raise HTTPException(503, detail={"code": "AGE_EVIDENCE_PROVIDER_CONFIGURATION_INVALID"}) from exc


@router.post("/sessions", dependencies=[Depends(require_orchestrator)])
def start_session(payload: SessionStart) -> dict:
    service = None
    try:
        policy = resolve_active_policy()
        threshold = policy.get("minimum_age")
        if type(threshold) is not int or policy.get("maximum_age") is not None:
            raise HTTPException(422, detail={"code": "AGE_EVIDENCE_POLICY_UNSUPPORTED"})
        service = _service()
        return service.start(
            **payload.model_dump(),
            policy_id=policy["policy_id"],
            policy_version=policy["policy_version"],
            threshold=threshold,
        )
    except HTTPException:
        raise
    except AgeEvidenceConflict as exc:
        raise HTTPException(409, detail={"code": "AGE_EVIDENCE_SESSION_ALREADY_EXISTS"}) from exc
    except (PolicyRegistryError, ValueError) as exc:
        raise HTTPException(503, detail={"code": "SERVER_POLICY_UNAVAILABLE"}) from exc
    except Exception as exc:
        raise HTTPException(502, detail={"code": "AGE_EVIDENCE_SESSION_START_FAILED"}) from exc
    finally:
        if service is not None:
            service.close()


def _require_session_owner(store: AgeEvidenceStore, session_id: str, subject_id: str) -> None:
    row = store.get_session(session_id)
    if row is None or not hmac.compare_digest(str(row["subject_id"]), subject_id):
        raise HTTPException(404, detail={"code": "AGE_EVIDENCE_SESSION_NOT_FOUND"})


@router.post("/sessions/{session_id}/poll", dependencies=[Depends(require_orchestrator)])
def poll_session(session_id: str, payload: SessionOwner) -> dict:
    service = None
    store = _store()
    try:
        _require_session_owner(store, session_id, payload.subject_id)
        service = _service()
        return service.poll(session_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "AGE_EVIDENCE_SESSION_NOT_READY"}) from exc
    except Exception as exc:
        raise HTTPException(502, detail={"code": "AGE_EVIDENCE_PROVIDER_RESULT_UNAVAILABLE"}) from exc
    finally:
        if service is not None:
            service.close()
        store.engine.dispose()


@router.post("/sessions/{session_id}/revoke", dependencies=[Depends(require_orchestrator)])
def revoke_session(session_id: str, payload: SessionOwner) -> dict:
    store = _store()
    try:
        _require_session_owner(store, session_id, payload.subject_id)
        return {"revoked": store.revoke_session(session_id)}
    finally:
        store.engine.dispose()


@router.post("/attestations/redeem", dependencies=[Depends(require_redemption)])
def redeem_attestation(payload: AttestationRedeem) -> dict:
    store = _store()
    try:
        redeemed = store.consume_attestation(**payload.model_dump())
    finally:
        store.engine.dispose()
    if not redeemed:
        raise HTTPException(409, detail={"code": "AGE_EVIDENCE_REPLAY_REVOKED_OR_EXPIRED"})
    return {"redeemed": True}

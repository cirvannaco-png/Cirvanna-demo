"""Authenticated NPL service API over a durable, transactionally guarded ledger."""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "preferences"))

from npl import (  # noqa: E402
    NegativePreference, PreferenceSource, TargetType, canonical_npl_evidence_payload,
    evaluate as evaluate_npl, preference_payload,
)
from app.store import (  # noqa: E402
    Base, NPLStore, PreferenceConflict, PreferenceNotFound, engine_for_url,
)

SERVICE = "cirvanna-npl-service"
bearer = HTTPBearer(auto_error=False)
app = FastAPI(
    title="Cirvanna NPL Service",
    version="0.1.0",
    description="Persistent negative-preference ledger and signed decision evidence.",
)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PreferenceCreate(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    preference_id: str = Field(min_length=1, max_length=128)
    target_type: Literal["item", "attribute"]
    target_value: str = Field(min_length=1, max_length=160)
    source: Literal["user_declared", "learned_rejection"]
    rejection_threshold: int = Field(default=3, ge=1, le=500)

class RejectionCreate(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    rejection_event_id: str = Field(min_length=1, max_length=128)

class CorrectionCreate(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    correction_event_id: str = Field(min_length=1, max_length=128)

class EvaluationRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    candidate_attributes: list[str] = Field(max_length=250)

def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("NPL_SERVICE_TOKEN", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "NPL_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail="Valid internal bearer authentication is required.", headers={"WWW-Authenticate": "Bearer"})

def _engine():
    url = os.getenv("NPL_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(503, detail={"code": "NPL_DATABASE_NOT_CONFIGURED"})
    if url.startswith("sqlite:///") and os.getenv("NPL_ALLOW_SQLITE_TESTS") != "1":
        raise HTTPException(503, detail={"code": "NPL_SQLITE_TEST_MODE_REQUIRED"})
    try:
        return engine_for_url(url)
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "NPL_DATABASE_CONFIGURATION_INVALID"}) from exc

def _store() -> NPLStore:
    return NPLStore(_engine())

def _preference_json(value: NegativePreference) -> dict[str, object]:
    return preference_payload(value)

def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, PreferenceNotFound):
        raise HTTPException(404, detail={"code": "NPL_PREFERENCE_NOT_FOUND"}) from exc
    if isinstance(exc, PreferenceConflict):
        raise HTTPException(409, detail={"code": "NPL_EVENT_OR_PREFERENCE_CONFLICT"}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(422, detail={"code": "INVALID_NPL_COMMAND"}) from exc
    raise exc

@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}

@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, object]:
    token_ready = len(os.getenv("NPL_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    signing_ready = len(os.getenv("NPL_EVIDENCE_HMAC_SECRET", "").encode("utf-8")) >= 32
    database_ready = False
    schema_ready = False
    try:
        engine = _engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        tables = set(inspect(engine).get_table_names())
        schema_ready = {"npl_preferences", "npl_rejection_events", "npl_correction_events", "npl_deletion_receipts"}.issubset(tables)
        database_ready = schema_ready
    except Exception:
        database_ready = False
    ready = token_ready and signing_ready and database_ready
    data = {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE,
        "api_authentication_configured": token_ready,
        "evidence_signing_configured": signing_ready,
        "database_connected": database_ready,
        "schema_ready": schema_ready,
        "ready": ready,
    }
    if not ready:
        raise HTTPException(503, detail=data)
    return data

@app.get("/v1/preferences", dependencies=[Depends(require_internal_token)], tags=["preferences"])
def list_preferences(user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    try:
        values = _store().list_preferences(user_id.strip())
        return {"user_id": user_id.strip(), "preferences": [_preference_json(value) for value in values]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc

@app.get("/v1/users/{user_id}/export", dependencies=[Depends(require_internal_token)], tags=["privacy and data rights"])
def export_user_data(user_id: str) -> dict[str, object]:
    """Export one user's NPL ledger; caller must have verified the subject."""
    normalized = user_id.strip()
    if not normalized:
        raise HTTPException(422, detail={"code": "INVALID_NPL_USER_ID"})
    try:
        exported = _store().export_user_data(normalized)
        return {
            "user_id": normalized,
            "export_version": 1,
            "preferences": [_preference_json(value) for value in exported["preferences"]],
            "rejection_events": exported["rejection_events"],
            "correction_events": exported["correction_events"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc


@app.delete("/v1/users/{user_id}", dependencies=[Depends(require_internal_token)], tags=["privacy and data rights"])
def delete_user_data(user_id: str) -> dict[str, object]:
    """Delete one user's complete NPL record and retain a non-identifying receipt."""
    try:
        return _store().delete_user_data(user_id)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_NPL_USER_ID"}) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/preferences", status_code=201, dependencies=[Depends(require_internal_token)], tags=["preferences"])
def create_preference(payload: PreferenceCreate) -> dict[str, object]:
    try:
        value = _store().create_preference(
            user_id=payload.user_id.strip(),
            preference_id=payload.preference_id.strip(),
            target_type=TargetType(payload.target_type),
            target_value=payload.target_value.strip(),
            source=PreferenceSource(payload.source),
            rejection_threshold=payload.rejection_threshold,
        )
        return {"preference": _preference_json(value)}
    except (ValueError, PreferenceConflict, PreferenceNotFound) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/preferences/{preference_id}/rejections", dependencies=[Depends(require_internal_token)], tags=["preferences"])
def record_rejection(preference_id: str, payload: RejectionCreate) -> dict[str, object]:
    try:
        value = _store().record_rejection(
            user_id=payload.user_id.strip(),
            preference_id=preference_id,
            rejection_event_id=payload.rejection_event_id.strip(),
        )
        return {"preference": _preference_json(value), "rejection_count": value.rejection_count, "hard_veto": value.is_hard_veto}
    except (ValueError, PreferenceConflict, PreferenceNotFound) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/preferences/{preference_id}/retract", dependencies=[Depends(require_internal_token)], tags=["preferences"])
def retract(preference_id: str, payload: CorrectionCreate) -> dict[str, object]:
    try:
        value = _store().retract_preference(
            user_id=payload.user_id.strip(),
            preference_id=preference_id,
            correction_event_id=payload.correction_event_id.strip(),
        )
        return {"preference": _preference_json(value), "retracted": not value.active, "correction_event_id": value.correction_event_id}
    except (ValueError, PreferenceConflict, PreferenceNotFound) as exc:
        _raise_domain_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/evaluate", dependencies=[Depends(require_internal_token)], tags=["evaluation"])
def evaluate(payload: EvaluationRequest) -> dict[str, object]:
    secret = os.getenv("NPL_EVIDENCE_HMAC_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "NPL_EVIDENCE_SIGNING_NOT_CONFIGURED"})
    try:
        values = _store().list_preferences(payload.user_id.strip())
        decision = evaluate_npl(payload.user_id.strip(), payload.candidate_id.strip(), tuple(payload.candidate_attributes), values)
        evidence = canonical_npl_evidence_payload(payload.request_id, payload.user_id, payload.candidate_id, payload.candidate_attributes, values)
        signature = hmac.new(secret.encode("utf-8"), evidence, "sha256").hexdigest()
        return {
            "request_id": payload.request_id,
            "user_id": payload.user_id,
            "candidate_id": decision.candidate_id,
            "contract_version": decision.contract_version,
            "blocked": decision.blocked,
            "reason_code": decision.reason_code,
            "hard_veto_preference_ids": list(decision.hard_veto_preference_ids),
            "soft_negative_preference_ids": list(decision.soft_negative_preference_ids),
            "negative_preferences": [_preference_json(value) for value in values],
            "npl_evidence_signature": signature,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "NPL_STORE_UNAVAILABLE"}) from exc

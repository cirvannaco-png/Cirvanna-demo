"""Authenticated API adapter for Cirvanna's existing deterministic eligibility pipeline.

This service runs the repository's EEPL, NPL, USI, FCI evidence contract and CAL
arbitration in-process. It is not an FCI prediction model. Signed fit evidence
must come from a separately trusted provider; missing/untrusted evidence fails
closed, and only the real CAL SHOW verdict authorizes display.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[3]
for package in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "packages" / "fit-intelligence",
):
    sys.path.insert(0, str(package))

from catacaci import DecisionSignal, DecisionVerdict, SignalKind, SignalState  # noqa: E402
from catacaci.pipeline import evaluate_candidate  # noqa: E402
from eepl import ContextField, EEPLContext, EEPLPolicy  # noqa: E402
from fci import FitConfidenceEstimate  # noqa: E402
from npl import NegativePreference, PreferenceSource, TargetType  # noqa: E402
from usi import StylePreference, USIProfile  # noqa: E402


SERVICE = "cirvanna-decision-service"
bearer = HTTPBearer(auto_error=False)


def _required_env(name: str, minimum_bytes: int = 32) -> str:
    value = os.getenv(name, "")
    if len(value.encode("utf-8")) < minimum_bytes:
        raise HTTPException(status_code=503, detail={"code": f"{name}_NOT_CONFIGURED"})
    return value


def require_internal_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    expected = _required_env("DECISION_SERVICE_TOKEN")
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, detail="Valid internal bearer authentication is required.", headers={"WWW-Authenticate": "Bearer"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextIn(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    age_years: int | None = Field(default=None, ge=0, le=125)
    location: str | None = Field(default=None, max_length=120)
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=120)

    @field_validator("user_id")
    @classmethod
    def user_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("user_id must not be blank")
        return value


class PolicyIn(StrictModel):
    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(default="1.0.0", min_length=1, max_length=64)
    minimum_age: int | None = Field(default=None, ge=0, le=125)
    maximum_age: int | None = Field(default=None, ge=0, le=125)
    allowed_locations: list[str] = Field(default_factory=list, max_length=100)
    allowed_occasions: list[str] = Field(default_factory=list, max_length=100)
    allowed_climates: list[str] = Field(default_factory=list, max_length=100)
    required_context: list[Literal["age", "location", "occasion", "climate"]] = Field(default_factory=list, max_length=4)


class StylePreferenceIn(StrictModel):
    preference_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0, le=1)
    active: bool = True


class USIProfileIn(StrictModel):
    profile_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    preferences: list[StylePreferenceIn] = Field(min_length=1, max_length=250)


class NegativePreferenceIn(StrictModel):
    preference_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    target_type: Literal["item", "attribute"]
    target_value: str = Field(min_length=1, max_length=160)
    source: Literal["user_declared", "learned_rejection"]
    rejection_event_ids: list[str] = Field(default_factory=list, max_length=500)
    rejection_threshold: int = Field(default=3, ge=1, le=500)
    active: bool = True
    correction_event_id: str | None = Field(default=None, max_length=128)


class FitEvidenceIn(StrictModel):
    estimate_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    calibrated: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    lower_bound: float | None = Field(default=None, ge=0, le=1)
    upper_bound: float | None = Field(default=None, ge=0, le=1)
    calibration_version: str | None = Field(default=None, max_length=128)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    interval_level: float = Field(default=0.95, gt=0, lt=1)


class UpstreamSignalIn(StrictModel):
    signal_id: str = Field(min_length=1, max_length=200)
    kind: Literal["safety", "legal_eligibility", "user_hard_constraint", "cultural_requirement", "other"]
    state: Literal["pass", "block", "unknown"]
    reason_code: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=1000)
    required: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_version: str = Field(default="unspecified", min_length=1, max_length=120)


class EligibilityRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(default="decision-pipeline-1.0.0", min_length=1, max_length=100)
    context: ContextIn
    eepl_policy: PolicyIn
    usi_profile: USIProfileIn
    candidate_attributes: list[str] = Field(max_length=250)
    candidate_attributes_complete: bool
    negative_preferences: list[NegativePreferenceIn] = Field(default_factory=list, max_length=500)
    fit_estimate: FitEvidenceIn
    fit_estimate_signature: str = Field(min_length=64, max_length=128)
    upstream_signals: list[UpstreamSignalIn] = Field(default_factory=list, max_length=64)
    minimum_fit_confidence: float = Field(default=0.70, ge=0, le=1)
    minimum_alignment_score: float = Field(default=0.60, ge=0, le=1)


def canonical_fit_payload(fit: FitEvidenceIn) -> bytes:
    normalized = fit.model_dump(mode="json", exclude_none=False)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def verify_fit_signature(fit: FitEvidenceIn, signature: str) -> None:
    secret = _required_env("FCI_EVIDENCE_HMAC_SECRET")
    expected = hmac.new(secret.encode("utf-8"), canonical_fit_payload(fit), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(401, detail={"code": "UNTRUSTED_FIT_EVIDENCE"})


def _result_json(result, payload: "EligibilityRequest") -> dict:
    arbitration = result.arbitration
    return {
        "service": SERVICE,
        "pipeline_contract_version": result.contract_version,
        "candidate_id": arbitration.candidate_id,
        "decision": arbitration.verdict.value.upper(),
        "may_display": arbitration.may_display,
        "arbitration": {
            "contract_version": arbitration.contract_version,
            "request_id": arbitration.request_id,
            "policy_version": arbitration.policy_version,
            "evaluated_signal_ids": list(arbitration.evaluated_signal_ids),
            "reasons": [{"code": reason.code, "signal_id": reason.signal_id, "explanation": reason.explanation} for reason in arbitration.reasons],
        },
        "gates": {
            "eepl": {"verdict": result.eepl.verdict.value, "reason_codes": list(result.eepl.reason_codes), "explanations": list(result.eepl.explanations)},
            "npl": {"blocked": result.npl.blocked, "reason_code": result.npl.reason_code,
                "hard_veto_preference_ids": list(result.npl.hard_veto_preference_ids),
                "soft_negative_preference_ids": list(result.npl.soft_negative_preference_ids)},
            "usi": {"verdict": result.usi.verdict.value, "alignment_score": result.usi.alignment_score,
                "reason_code": result.usi.reason_code, "matched_preference_ids": list(result.usi.matched_preference_ids),
                "unmatched_preference_ids": list(result.usi.unmatched_preference_ids)},
            "fci": {"estimate_id": result.fit_estimate.estimate_id, "calibrated": result.fit_estimate.calibrated,
                "confidence": result.fit_estimate.confidence, "interval_width": result.fit_estimate.interval_width,
                "model_version": result.fit_estimate.model_version, "calibration_version": result.fit_estimate.calibration_version,
                "evidence_ids": list(result.fit_estimate.evidence_ids)},
        },
        "policy": {"version": result.arbitration.policy_version,
            "minimum_fit_confidence": payload.minimum_fit_confidence,
            "minimum_alignment_score": payload.minimum_alignment_score,
            "fci_model_version": result.fit_estimate.model_version,
            "fci_calibration_version": result.fit_estimate.calibration_version},
    }


app = FastAPI(title="Cirvanna Decision Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def readiness() -> dict:
    internal_configured = len(os.getenv("DECISION_SERVICE_TOKEN", "").encode("utf-8")) >= 32
    fit_key_configured = len(os.getenv("FCI_EVIDENCE_HMAC_SECRET", "").encode("utf-8")) >= 32
    ready = internal_configured and fit_key_configured
    response = {"status": "ready" if ready else "not_ready", "service": SERVICE,
        "internal_auth_configured": internal_configured, "trusted_fit_evidence_configured": fit_key_configured,
        "fci_prediction_model_available": False, "ready": ready}
    if not ready:
        raise HTTPException(503, detail=response)
    return response


@app.get("/capabilities")
def capabilities() -> dict:
    return {"service": SERVICE, "eepl_policy_evaluation": True, "npl_hard_veto": True,
        "usi_explicit_preference_alignment": True, "fci_calibrated_evidence_contract": True,
        "catacaci_cal_arbitration": True, "decision_explanations": True,
        "fci_prediction_model_available": False, "persisted_user_preference_store": False,
        "decision_audit_persistence": False, "click_it_reconstruction": False,
        "virtual_twin_generation": False, "virtual_try_on": False}


@app.post("/v1/eligibility/evaluate", dependencies=[Depends(require_internal_token)])
def evaluate_eligibility(payload: EligibilityRequest) -> dict:
    # The fit provider signs the canonical estimate object with a separate secret.
    # API clients cannot elevate an untrusted self-asserted confidence to a CAL pass.
    verify_fit_signature(payload.fit_estimate, payload.fit_estimate_signature)
    try:
        policy = EEPLPolicy(
            policy_id=payload.eepl_policy.policy_id,
            policy_version=payload.eepl_policy.policy_version,
            minimum_age=payload.eepl_policy.minimum_age,
            maximum_age=payload.eepl_policy.maximum_age,
            allowed_locations=tuple(payload.eepl_policy.allowed_locations),
            allowed_occasions=tuple(payload.eepl_policy.allowed_occasions),
            allowed_climates=tuple(payload.eepl_policy.allowed_climates),
            required_context=tuple(ContextField(x) for x in payload.eepl_policy.required_context),
        )
        context = EEPLContext(
            user_id=payload.context.user_id,
            age_years=payload.context.age_years,
            location=payload.context.location,
            occasion=payload.context.occasion,
            climate=payload.context.climate,
        )
        profile = USIProfile(
            profile_id=payload.usi_profile.profile_id,
            user_id=payload.usi_profile.user_id,
            version=payload.usi_profile.version,
            preferences=tuple(StylePreference(**item.model_dump()) for item in payload.usi_profile.preferences),
        )
        negative = tuple(NegativePreference(
            preference_id=item.preference_id, user_id=item.user_id,
            target_type=TargetType(item.target_type), target_value=item.target_value,
            source=PreferenceSource(item.source), rejection_event_ids=tuple(item.rejection_event_ids),
            rejection_threshold=item.rejection_threshold, active=item.active, correction_event_id=item.correction_event_id,
        ) for item in payload.negative_preferences)
        fit = FitConfidenceEstimate(
            estimate_id=payload.fit_estimate.estimate_id, user_id=payload.fit_estimate.user_id,
            candidate_id=payload.fit_estimate.candidate_id, model_version=payload.fit_estimate.model_version,
            calibrated=payload.fit_estimate.calibrated, confidence=payload.fit_estimate.confidence,
            lower_bound=payload.fit_estimate.lower_bound, upper_bound=payload.fit_estimate.upper_bound,
            calibration_version=payload.fit_estimate.calibration_version,
            evidence_ids=tuple(payload.fit_estimate.evidence_ids), interval_level=payload.fit_estimate.interval_level,
        )
        signals = tuple(DecisionSignal(
            signal_id=item.signal_id, kind=SignalKind(item.kind), state=SignalState(item.state),
            reason_code=item.reason_code, explanation=item.explanation, required=item.required,
            confidence=item.confidence, source_version=item.source_version,
        ) for item in payload.upstream_signals)
        result = evaluate_candidate(
            request_id=payload.request_id, candidate_id=payload.candidate_id,
            eepl_policy=policy, context=context, usi_profile=profile,
            candidate_attributes=tuple(payload.candidate_attributes),
            candidate_attributes_complete=payload.candidate_attributes_complete,
            negative_preferences=negative, fit_estimate=fit, upstream_signals=signals,
            minimum_fit_confidence=payload.minimum_fit_confidence,
            minimum_alignment_score=payload.minimum_alignment_score, policy_version=payload.policy_version,
        )
        return _result_json(result, payload)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_DECISION_EVIDENCE", "detail": str(exc)}) from exc

"""Cirvanna purchase-decision HTTP boundary.

This gateway composes canonical domain contracts and the catalog service. It
never manufactures a fit score or claims an unconfigured safety gate passed.
Only a CAL SHOW verdict authorizes the response to mark a candidate displayable.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[3]
for package_path in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "packages" / "fit-intelligence",
):
    resolved = str(package_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

from catacaci import DecisionSignal, SignalKind, SignalState  # noqa: E402
from catacaci.pipeline import evaluate_candidate  # noqa: E402
from cultural_identity import (  # noqa: E402
    CulturalRequirement,
    RequirementKind,
    canonical_cultural_evidence_payload,
)
from eepl import ContextField, EEPLContext, EEPLPolicy  # noqa: E402
from fci import FitConfidenceEstimate  # noqa: E402
from npl import NegativePreference, PreferenceSource, TargetType, canonical_npl_evidence_payload  # noqa: E402
from usi import StylePreference, USIProfile  # noqa: E402

SERVICE_NAME = "cirvanna-decision-gateway"
API_VERSION = "1.0.0"
POLICY_VERSION = os.getenv("CIRVANNA_POLICY_VERSION", "cirvanna-demo-policy-1")
bearer = HTTPBearer(auto_error=False)


class ContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age_years: int | None = Field(default=None, ge=0, le=120)
    location: str | None = Field(default=None, max_length=120)
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=120)


class StylePreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0.0, le=1.0)


class NegativePreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preference_id: str = Field(min_length=1, max_length=128)
    target_type: Literal["item", "attribute"]
    target_value: str = Field(min_length=1, max_length=180)


class CulturalRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1, max_length=128)
    declaration_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    kind: Literal["required_attribute", "forbidden_attribute"]
    hard: bool = True


class HardConstraintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constraint_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    kind: Literal["required_attribute", "forbidden_attribute"]


class DecisionRequest(BaseModel):
    """Explicit user inputs for one request; profile persistence is not implied."""
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=128)
    product_ids: list[str] = Field(min_length=1, max_length=25)
    context: ContextInput = Field(default_factory=ContextInput)
    style_preferences: list[StylePreferenceInput] = Field(default_factory=list, max_length=40)
    negative_preferences: list[NegativePreferenceInput] = Field(default_factory=list, max_length=100)
    cultural_requirements: list[CulturalRequirementInput] = Field(default_factory=list, max_length=60)
    hard_constraints: list[HardConstraintInput] = Field(default_factory=list, max_length=60)

    @field_validator("user_id")
    @classmethod
    def trim_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_id must not be blank")
        return normalized

    @field_validator("product_ids")
    @classmethod
    def validate_product_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(uuid.UUID(value)))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("product_ids must contain valid catalog UUIDs") from exc
        if len(normalized) != len(set(normalized)):
            raise ValueError("product_ids must be unique")
        return normalized


class ComplementerAdvisoryRequest(BaseModel):
    """Request-scoped style advisory; this is not a persisted identity profile."""
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    preferences: dict[str, Any] = Field(default_factory=dict, max_length=64)
    look: dict[str, Any] = Field(default_factory=dict, max_length=32)

    @field_validator("request_id", "user_id")
    @classmethod
    def trim_advisory_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifier must not be blank")
        return normalized


class ReasonOutput(BaseModel):
    code: str
    explanation: str
    signal_id: str | None = None


class CandidateDecisionOutput(BaseModel):
    product_id: str
    sku: str
    name: str
    category: str
    brand: str | None = None
    price_minor: int
    currency: str
    image_urls: list[str]
    catalog_version: int
    verdict: Literal["show", "block", "review"]
    may_display: bool
    reasons: list[ReasonOutput]
    policy_version: str
    arbitration_contract_version: str
    decision_pipeline_contract_version: str


class DecisionResponse(BaseModel):
    schema_version: Literal["1.0"]
    request_id: str
    created_at: str
    candidates: list[CandidateDecisionOutput]


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _optional_age(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        age = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number") from exc
    if not 0 <= age <= 120:
        raise RuntimeError(f"{name} must be between 0 and 120")
    return age


def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = os.getenv("CIRVANNA_API_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GATEWAY_AUTH_NOT_CONFIGURED", "message": "Decision API is not accepting traffic until gateway authentication is configured."},
        )
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def fetch_product(product_id: str) -> dict[str, Any]:
    """Fetch canonical metadata; there is deliberately no fallback/mock catalog."""
    base_url = os.getenv("CATALOG_SERVICE_URL", "").strip().rstrip("/")
    catalog_token = os.getenv("CATALOG_API_TOKEN", "")
    if not base_url or not catalog_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CATALOG_NOT_CONFIGURED", "message": "Catalog URL and service token must be configured."},
        )
    try:
        with httpx.Client(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
            response = client.get(
                f"{base_url}/products/{product_id}",
                headers={"Authorization": f"Bearer {catalog_token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CATALOG_UNAVAILABLE", "message": "Catalog service could not be reached."},
        ) from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "CATALOG_PRODUCT_NOT_FOUND", "product_id": product_id})
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "CATALOG_AUTH_FAILED", "message": "Gateway-to-catalog authentication failed; contact the operator."},
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "CATALOG_REQUEST_FAILED", "upstream_status": response.status_code},
        )
    try:
        product = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "CATALOG_INVALID_RESPONSE"}) from exc
    required = ("product_id", "sku", "name", "category", "price_minor", "currency", "attributes", "status", "catalog_version")
    if not isinstance(product, dict) or any(key not in product for key in required) or not isinstance(product.get("attributes"), dict):
        raise HTTPException(status_code=502, detail={"code": "CATALOG_SCHEMA_MISMATCH"})
    if product["status"] != "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "CATALOG_PRODUCT_NOT_ACTIVE", "product_id": product_id},
        )
    return product


def _catalog_attributes(product: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    category = product.get("category")
    brand = product.get("brand")
    if isinstance(category, str) and category.strip():
        values.append(category.strip())
    if isinstance(brand, str) and brand.strip():
        values.append(brand.strip())

    def add_leaf(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, list):
            for child in value:
                add_leaf(child)
        elif isinstance(value, dict):
            for child in value.values():
                add_leaf(child)

    add_leaf(product.get("attributes", {}))
    # Stable ordering prevents input ordering from changing domain behavior.
    return tuple(sorted(set(values), key=str.casefold))


def _catalog_attributes_complete(product: dict[str, Any]) -> bool:
    attrs = product.get("attributes")
    required_keys = _env_csv("CIRVANNA_REQUIRED_PRODUCT_ATTRIBUTES", "style,material,color")
    if not isinstance(attrs, dict) or not required_keys:
        return False
    normalized = {
        key.strip().casefold(): value
        for key, value in attrs.items()
        if isinstance(key, str) and key.strip()
    }
    return all(
        isinstance(normalized.get(key.casefold()), str)
        and bool(normalized[key.casefold()].strip())
        for key in required_keys
    )


def _policy() -> EEPLPolicy:
    required = _env_csv("CIRVANNA_REQUIRED_CONTEXT_FIELDS", "location,occasion,climate")
    field_map = {field.value: field for field in ContextField}
    unknown = sorted(set(required) - set(field_map))
    if unknown:
        raise RuntimeError(f"Unknown values in CIRVANNA_REQUIRED_CONTEXT_FIELDS: {', '.join(unknown)}")
    return EEPLPolicy(
        policy_id=os.getenv("CIRVANNA_EEPL_POLICY_ID", "cirvanna-context-v1"),
        policy_version=os.getenv("CIRVANNA_EEPL_POLICY_VERSION", "1.0.0"),
        minimum_age=_optional_age("CIRVANNA_MINIMUM_AGE"),
        maximum_age=_optional_age("CIRVANNA_MAXIMUM_AGE"),
        allowed_locations=_env_csv("CIRVANNA_ALLOWED_LOCATIONS"),
        allowed_occasions=_env_csv("CIRVANNA_ALLOWED_OCCASIONS"),
        allowed_climates=_env_csv("CIRVANNA_ALLOWED_CLIMATES"),
        required_context=tuple(field_map[name] for name in required),
    )


def _safety_signal(product: dict[str, Any]) -> DecisionSignal:
    """Fail closed until an independent, validated safety policy provider exists."""
    return DecisionSignal(
        signal_id=f"safety:not-configured:{product['product_id']}",
        kind=SignalKind.SAFETY,
        state=SignalState.UNKNOWN,
        reason_code="SAFETY_POLICY_NOT_CONFIGURED",
        explanation="No independent product-safety policy provider is configured; safety clearance cannot be asserted.",
        required=True,
        source_version="unavailable",
    )


def _legal_signal(context: ContextInput, product: dict[str, Any]) -> DecisionSignal:
    minimum_age = _optional_age("CIRVANNA_MINIMUM_AGE")
    maximum_age = _optional_age("CIRVANNA_MAXIMUM_AGE")
    raw_product_min = product.get("attributes", {}).get("minimum_age")
    raw_product_max = product.get("attributes", {}).get("maximum_age")
    if isinstance(raw_product_min, int) and not isinstance(raw_product_min, bool):
        minimum_age = max(minimum_age or 0, raw_product_min)
    if isinstance(raw_product_max, int) and not isinstance(raw_product_max, bool):
        maximum_age = min(maximum_age, raw_product_max) if maximum_age is not None else raw_product_max

    if minimum_age is None and maximum_age is None:
        state, code, explanation = (
            SignalState.PASS,
            "LEGAL_AGE_GATE_NO_ADDITIONAL_RULES",
            "No additional age restriction is configured for this candidate.",
        )
    elif context.age_years is None:
        state, code, explanation = (
            SignalState.UNKNOWN,
            "LEGAL_AGE_EVIDENCE_MISSING",
            "An age-dependent eligibility rule applies, but age was not supplied.",
        )
    elif context.age_years < (minimum_age or 0) or (maximum_age is not None and context.age_years > maximum_age):
        state, code, explanation = (
            SignalState.BLOCK,
            "LEGAL_AGE_RESTRICTION_VIOLATION",
            "The supplied age conflicts with the configured age restriction.",
        )
    else:
        state, code, explanation = (
            SignalState.PASS,
            "LEGAL_AGE_RESTRICTION_PASSED",
            "The supplied age satisfies configured age restrictions.",
        )
    return DecisionSignal(
        signal_id=f"legal-age:{product['product_id']}",
        kind=SignalKind.LEGAL_ELIGIBILITY,
        state=state,
        reason_code=code,
        explanation=explanation,
        required=True,
        source_version=POLICY_VERSION,
    )


def _user_constraint_signals(
    user_id: str,
    product_id: str,
    attributes: tuple[str, ...],
    complete: bool,
    constraints: list[HardConstraintInput],
) -> tuple[DecisionSignal, ...]:
    if not constraints:
        return (DecisionSignal(
            signal_id=f"user-hard:none:{product_id}",
            kind=SignalKind.USER_HARD_CONSTRAINT,
            state=SignalState.PASS,
            reason_code="USER_HARD_CONSTRAINTS_NONE_DECLARED",
            explanation="No additional generic hard constraints were declared in this request.",
            required=True,
            source_version="user-input-v1",
        ),)
    actual = {value.strip().casefold() for value in attributes}
    signals: list[DecisionSignal] = []
    for item in sorted(constraints, key=lambda c: c.constraint_id):
        present = item.attribute.strip().casefold() in actual
        if item.kind == "required_attribute" and not present:
            state = SignalState.BLOCK if complete else SignalState.UNKNOWN
            code = "USER_REQUIRED_ATTRIBUTE_MISSING" if complete else "USER_REQUIRED_ATTRIBUTE_UNVERIFIED"
            explanation = f"Explicit constraint '{item.constraint_id}' requires an attribute that is not confirmed."
        elif item.kind == "forbidden_attribute" and present:
            state, code, explanation = (
                SignalState.BLOCK,
                "USER_FORBIDDEN_ATTRIBUTE_PRESENT",
                f"Explicit constraint '{item.constraint_id}' forbids an attribute present on this candidate.",
            )
        elif item.kind == "forbidden_attribute" and not complete:
            state, code, explanation = (
                SignalState.UNKNOWN,
                "USER_FORBIDDEN_ATTRIBUTE_UNVERIFIED",
                f"Catalog metadata is incomplete, so forbidden attribute '{item.attribute}' cannot be ruled out.",
            )
        else:
            state, code, explanation = (
                SignalState.PASS,
                "USER_HARD_CONSTRAINT_PASSED",
                f"Explicit constraint '{item.constraint_id}' was checked against current catalog metadata.",
            )
        signals.append(DecisionSignal(
            signal_id=f"user-hard:{item.constraint_id}:{product_id}",
            kind=SignalKind.USER_HARD_CONSTRAINT,
            state=state,
            reason_code=code,
            explanation=explanation,
            required=True,
            source_version="user-input-v1",
        ))
    return tuple(signals)


def _trusted_internal_base_url(value: str) -> bool:
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        return bool(
            host and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment
            and (parts.scheme == "https" or (parts.scheme == "http" and local))
        )
    except ValueError:
        return False


def _complementer_advisory(
    payload: ComplementerAdvisoryRequest,
) -> dict[str, Any]:
    """Call the stateless Complementer API without granting product-display authority."""
    base = os.getenv("COMPLEMENTER_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("COMPLEMENTER_SERVICE_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32 or not _trusted_internal_base_url(base):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "COMPLEMENTER_PROVIDER_CONFIGURATION_INVALID"},
        )

    request_body = payload.model_dump(mode="json")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.post(
                f"{base}/v1/complementer/recommend",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "COMPLEMENTER_PROVIDER_TIMEOUT"},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "COMPLEMENTER_PROVIDER_UNAVAILABLE"},
        ) from exc

    if response.status_code == 422:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "COMPLEMENTER_REQUEST_REJECTED"},
        )
    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "COMPLEMENTER_PROVIDER_AUTH_FAILED"},
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "COMPLEMENTER_PROVIDER_UNAVAILABLE"},
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "COMPLEMENTER_INVALID_RESPONSE"},
        ) from exc

    if (
        not isinstance(result, dict)
        or result.get("schema_version") != "2.0"
        or not isinstance(result.get("contract_version"), str)
        or result.get("request_id") != payload.request_id
        or result.get("user_id") != payload.user_id
        or result.get("status") not in {"ready", "needs_input"}
        or result.get("persistence") != "stateless_request_only"
        or not isinstance(result.get("limits"), list)
        or not all(isinstance(item, str) for item in result.get("limits", []))
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "COMPLEMENTER_SCHEMA_OR_SCOPE_MISMATCH"},
        )

    return {
        "schema_version": "1.0",
        "request_id": payload.request_id,
        "mode": "advisory_only",
        "display_authorized": False,
        "durable_personal_memory": False,
        "recommendation": result,
    }


def _load_persisted_npl_preferences(
    *, request_id: str, user_id: str, product_id: str, attributes: tuple[str, ...],
) -> tuple[NegativePreference, ...]:
    """Fetch and authenticate a candidate-bound snapshot from the durable NPL service."""
    base = os.getenv("NPL_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("NPL_SERVICE_TOKEN", "")
    secret = os.getenv("NPL_EVIDENCE_HMAC_SECRET", "")
    configured = (bool(base), len(token.encode("utf-8")) >= 32, len(secret.encode("utf-8")) >= 32)
    if not any(configured):
        return ()
    if not all(configured) or not _trusted_internal_base_url(base):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NPL_PROVIDER_CONFIGURATION_INVALID"},
        )
    body = {
        "request_id": request_id,
        "user_id": user_id,
        "candidate_id": product_id,
        "candidate_attributes": list(attributes),
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(3.5, connect=1.0)) as client:
            response = client.post(
                f"{base}/v1/evaluate",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "NPL_PROVIDER_UNAVAILABLE"},
            )
        result = response.json()
        if (
            result.get("request_id") != request_id
            or result.get("user_id") != user_id
            or result.get("candidate_id") != product_id
            or not isinstance(result.get("negative_preferences"), list)
            or not isinstance(result.get("npl_evidence_signature"), str)
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "NPL_PROVIDER_RESPONSE_INVALID"},
            )
        canonical = canonical_npl_evidence_payload(
            request_id, user_id, product_id, attributes, result["negative_preferences"]
        )
        expected = hmac.new(secret.encode("utf-8"), canonical, "sha256").hexdigest()
        if not hmac.compare_digest(expected, result["npl_evidence_signature"].lower()):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "NPL_PROVIDER_EVIDENCE_UNTRUSTED"},
            )
        parsed: list[NegativePreference] = []
        for item in result["negative_preferences"]:
            parsed.append(NegativePreference(
                preference_id=item["preference_id"],
                user_id=item["user_id"],
                target_type=TargetType(item["target_type"]),
                target_value=item["target_value"],
                source=PreferenceSource(item["source"]),
                rejection_event_ids=tuple(item.get("rejection_event_ids", ())),
                rejection_threshold=item.get("rejection_threshold", 3),
                active=item.get("active", True),
                correction_event_id=item.get("correction_event_id"),
            ))
        return tuple(parsed)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NPL_PROVIDER_UNAVAILABLE"},
        ) from exc


def _load_persisted_cultural_requirements(
    *, request_id: str, user_id: str, product_id: str, attributes: tuple[str, ...],
    attributes_complete: bool,
) -> tuple[CulturalRequirement, ...]:
    """Fetch candidate-bound explicit declarations and authenticate their provenance."""
    base = os.getenv("CULTURAL_IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("CULTURAL_IDENTITY_SERVICE_TOKEN", "")
    secret = os.getenv("CULTURAL_IDENTITY_HMAC_SECRET", "")
    configured = (bool(base), len(token.encode("utf-8")) >= 32, len(secret.encode("utf-8")) >= 32)
    if not any(configured):
        return ()
    if not all(configured) or not _trusted_internal_base_url(base):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CULTURAL_IDENTITY_PROVIDER_CONFIGURATION_INVALID"},
        )
    body = {
        "request_id": request_id, "user_id": user_id, "candidate_id": product_id,
        "candidate_attributes": list(attributes),
        "candidate_attributes_complete": attributes_complete,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(3.5, connect=1.0)) as client:
            response = client.post(
                f"{base}/v1/evaluate",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "CULTURAL_IDENTITY_PROVIDER_UNAVAILABLE"},
            )
        result = response.json()
        if (
            result.get("request_id") != request_id
            or result.get("user_id") != user_id
            or result.get("candidate_id") != product_id
            or not isinstance(result.get("cultural_requirements"), list)
            or not isinstance(result.get("cultural_evidence_signature"), str)
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "CULTURAL_IDENTITY_PROVIDER_RESPONSE_INVALID"},
            )
        canonical = canonical_cultural_evidence_payload(
            request_id, user_id, product_id, attributes, attributes_complete,
            result["cultural_requirements"],
        )
        expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, result["cultural_evidence_signature"].lower()):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "CULTURAL_IDENTITY_EVIDENCE_UNTRUSTED"},
            )
        parsed=[]
        for item in result["cultural_requirements"]:
            parsed.append(CulturalRequirement(
                requirement_id=item["requirement_id"],
                declaration_id=item["declaration_id"],
                user_id=item["user_id"],
                attribute=item["attribute"],
                kind=RequirementKind(item["kind"]),
                hard=item["hard"],
                active=item.get("active", True),
            ))
        return tuple(parsed)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CULTURAL_IDENTITY_PROVIDER_UNAVAILABLE"},
        ) from exc



def _verified_identity_required() -> bool:
    return os.getenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "false").strip().lower() == "true"


def _resolve_verified_subject(end_user_authorization: str | None) -> str:
    """Resolve the subject through Commerce's verified-token /me contract."""
    if not end_user_authorization:
        raise HTTPException(401, detail={"code": "END_USER_BEARER_REQUIRED"})
    scheme, _, token = end_user_authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, detail={"code": "END_USER_BEARER_INVALID"})
    base = os.getenv("COMMERCE_API_URL", "").strip().rstrip("/")
    if not base or not _trusted_internal_base_url(base):
        raise HTTPException(503, detail={"code": "COMMERCE_IDENTITY_PROVIDER_NOT_CONFIGURED"})
    try:
        with httpx.Client(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = client.get(
                f"{base}/me",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "COMMERCE_IDENTITY_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code in {401, 403}:
        raise HTTPException(401, detail={"code": "END_USER_AUTHENTICATION_FAILED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "COMMERCE_IDENTITY_PROVIDER_UNAVAILABLE"})
    try:
        actor = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "COMMERCE_IDENTITY_RESPONSE_INVALID"}) from exc
    subject = actor.get("user_id") if isinstance(actor, dict) else None
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 128:
        raise HTTPException(502, detail={"code": "COMMERCE_IDENTITY_SUBJECT_INVALID"})
    return subject.strip()


def _load_verified_usi_profile(subject_id: str) -> USIProfile:
    """Hydrate only the profile belonging to a Commerce-verified subject."""
    base = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "USI_PROFILE_PROVIDER_NOT_CONFIGURED"})
    try:
        with httpx.Client(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = client.get(
                f"{base}/v1/profiles/{subject_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "USI_PROFILE_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code == 403:
        raise HTTPException(403, detail={"code": "USI_PROFILE_CONSENT_REQUIRED"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "USI_PROFILE_PROVIDER_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "USI_PROFILE_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(data, dict)
        or data.get("subject_id") != subject_id
        or not isinstance(data.get("profile_version"), int)
        or not isinstance(data.get("preferences"), list)
    ):
        raise HTTPException(502, detail={"code": "USI_PROFILE_SCOPE_OR_SCHEMA_MISMATCH"})
    preferences = []
    for item in data["preferences"]:
        if not isinstance(item, dict):
            raise HTTPException(502, detail={"code": "USI_PROFILE_SCHEMA_INVALID"})
        try:
            preferences.append(StylePreference(
                preference_id=item["preference_id"],
                user_id=subject_id,
                attribute=item["attribute"],
                weight=float(item.get("weight", 1.0)),
                active=bool(item.get("active", True)),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(502, detail={"code": "USI_PROFILE_SCHEMA_INVALID"}) from exc
    return USIProfile(
        profile_id=f"usi:{subject_id}",
        user_id=subject_id,
        version=str(data["profile_version"]),
        preferences=tuple(preferences),
    )

def _fit_evidence_fields(estimate: FitConfidenceEstimate) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return trusted field coverage from the fit provider; none is registered yet."""
    del estimate
    return (), ()


def _fit_estimate(user_id: str, product_id: str) -> FitConfidenceEstimate:
    """No trained/calibrated FCI provider is registered in this build."""
    return FitConfidenceEstimate(
        estimate_id=f"fci-unavailable:{product_id}",
        user_id=user_id,
        candidate_id=product_id,
        model_version="not-configured",
        calibrated=False,
        confidence=None,
        lower_bound=None,
        upper_bound=None,
        calibration_version=None,
        evidence_ids=(),
    )


def _audit_path() -> Path:
    configured = os.getenv("CIRVANNA_AUDIT_DB", "./.cirvanna/audit.sqlite3").strip()
    if not configured or configured == ":memory:":
        raise RuntimeError("CIRVANNA_AUDIT_DB must identify a durable file path, not an in-memory database.")
    return Path(configured).expanduser()


def _record_audit(
    *,
    request_id: str,
    product_id: str,
    verdict: str,
    reasons: list[dict[str, Any]],
    catalog_version: int,
    arbitration_contract_version: str,
    pipeline_contract_version: str,
    policy_version: str,
) -> None:
    """Append minimal decision metadata; omit user IDs, measurements and images."""
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(str(path), timeout=5.0) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK (verdict IN ('show', 'block', 'review')),
                    reason_codes_json TEXT NOT NULL,
                    catalog_version INTEGER NOT NULL,
                    arbitration_contract_version TEXT NOT NULL,
                    pipeline_contract_version TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, product_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO decision_audit (
                    request_id, product_id, verdict, reason_codes_json,
                    catalog_version, arbitration_contract_version,
                    pipeline_contract_version, policy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id, product_id, verdict,
                    json.dumps([reason["code"] for reason in reasons], separators=(",", ":")),
                    int(catalog_version), arbitration_contract_version,
                    pipeline_contract_version, policy_version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
    except (OSError, sqlite3.Error) as exc:
        raise RuntimeError("Decision audit persistence failed; response cannot be released.") from exc


app = FastAPI(
    title="Cirvanna Decision Gateway",
    version=API_VERSION,
    description=(
        "First purchase-decision API slice. Catalog integration and deterministic "
        "domain composition are implemented; unavailable safety and fit providers fail closed."
    ),
)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "decision_http_api": True,
        "complementer_advisory_integration_configured": bool(
            os.getenv("COMPLEMENTER_SERVICE_URL")
            and len(os.getenv("COMPLEMENTER_SERVICE_TOKEN", "").encode("utf-8")) >= 32
            and _trusted_internal_base_url(os.getenv("COMPLEMENTER_SERVICE_URL", ""))
        ),
        "complementer_product_retrieval": False,
        "complementer_display_authority": False,
        "durable_complementer_memory": False,

        "catalog_service_integration": True,
        "deterministic_cal_arbitration": True,
        "explicit_negative_preferences": True,
        "persistent_npl_service_integrated": bool(
            os.getenv("NPL_SERVICE_URL")
            and len(os.getenv("NPL_SERVICE_TOKEN", "").encode("utf-8")) >= 32
            and len(os.getenv("NPL_EVIDENCE_HMAC_SECRET", "").encode("utf-8")) >= 32
        ),
        "explicit_cultural_requirements": True,
        "persistent_cultural_declarations_integrated": bool(
            os.getenv("CULTURAL_IDENTITY_SERVICE_URL")
            and len(os.getenv("CULTURAL_IDENTITY_SERVICE_TOKEN", "").encode("utf-8")) >= 32
            and len(os.getenv("CULTURAL_IDENTITY_HMAC_SECRET", "").encode("utf-8")) >= 32
        ),
        "durable_decision_audit": "sqlite_local_only",
        "trained_fit_predictor": False,
        "calibrated_fci_provider": False,
        "independent_safety_policy_provider": False,
        "persisted_user_profiles": False,
        "identity_provider_binding": False,
        "production_ready": False,
    }


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, Any]:
    base_url = os.getenv("CATALOG_SERVICE_URL", "").strip().rstrip("/")
    configured = bool(
        os.getenv("CIRVANNA_API_TOKEN")
        and os.getenv("CATALOG_API_TOKEN")
        and base_url
    )
    catalog_ready = False
    if base_url:
        try:
            with httpx.Client(timeout=httpx.Timeout(2.0, connect=1.0)) as client:
                response = client.get(f"{base_url}/ready")
            catalog_ready = response.status_code == 200 and response.json().get("ready") is True
        except (httpx.HTTPError, ValueError):
            catalog_ready = False
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path), timeout=2.0) as connection:
            connection.execute("SELECT 1")
        audit_ready = True
    except (OSError, sqlite3.Error, RuntimeError):
        audit_ready = False
    try:
        _policy()
        policy_configured = True
    except (RuntimeError, ValueError):
        policy_configured = False
    ready = configured and catalog_ready and audit_ready and policy_configured
    return {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE_NAME,
        "gateway_auth_configured": bool(os.getenv("CIRVANNA_API_TOKEN")),
        "catalog_auth_configured": bool(os.getenv("CATALOG_API_TOKEN")),
        "catalog_ready": catalog_ready,
        "audit_store_ready": audit_ready,
        "policy_configuration_valid": policy_configured,
        "fci_available": False,
        "safety_policy_available": False,
        "ready": ready,
    }


@app.post(
    "/v1/complementer/recommend",
    dependencies=[Depends(require_api_token)],
    tags=["personal aesthetic intelligence"],
)
def recommend_complementary_look(payload: ComplementerAdvisoryRequest) -> dict[str, Any]:
    """Return styling guidance only; product candidates require the separate CAL decision path."""
    return _complementer_advisory(payload)


@app.post(
    "/v1/decisions",
    response_model=DecisionResponse,
    dependencies=[Depends(require_api_token)],
    tags=["purchase decisions"],
)
def evaluate_decisions(
    payload: DecisionRequest,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
) -> DecisionResponse:
    """Evaluate active catalog products; verified USI profile and CAL govern eligibility."""
    request_id = str(uuid.uuid4())
    if _verified_identity_required():
        verified_subject = _resolve_verified_subject(end_user_authorization)
        if not hmac.compare_digest(verified_subject, payload.user_id):
            raise HTTPException(403, detail={"code": "REQUEST_SUBJECT_MISMATCH"})
        profile = _load_verified_usi_profile(verified_subject)
    else:
        profile = USIProfile(
            profile_id=f"request-profile:{request_id}",
            user_id=payload.user_id,
            version="request-profile-v1",
            preferences=tuple(
                StylePreference(
                    preference_id=f"style-{index}",
                    user_id=payload.user_id,
                    attribute=item.attribute,
                    weight=item.weight,
                )
                for index, item in enumerate(payload.style_preferences)
            ),
        )
    context = EEPLContext(
        user_id=payload.user_id,
        age_years=payload.context.age_years,
        location=payload.context.location,
        occasion=payload.context.occasion,
        climate=payload.context.climate,
    )
    explicit_negative_preferences = tuple(
        NegativePreference(
            preference_id=item.preference_id,
            user_id=payload.user_id,
            target_type=TargetType(item.target_type),
            target_value=item.target_value,
            source=PreferenceSource.USER_DECLARED,
        )
        for item in payload.negative_preferences
    )
    request_cultural_requirements = tuple(
        CulturalRequirement(
            requirement_id=item.requirement_id,
            declaration_id=item.declaration_id,
            user_id=payload.user_id,
            attribute=item.attribute,
            kind=RequirementKind(item.kind),
            hard=item.hard,
            active=True,
        )
        for item in payload.cultural_requirements
    )
    eepl_policy = _policy()
    candidates: list[CandidateDecisionOutput] = []
    # Bound parallelism so a batch does not serially pay the catalog timeout per item.
    with ThreadPoolExecutor(max_workers=min(5, len(payload.product_ids))) as executor:
        products = list(executor.map(fetch_product, payload.product_ids))

    for product_id, product in zip(payload.product_ids, products):
        attributes = _catalog_attributes(product)
        complete = _catalog_attributes_complete(product)
        persisted_cultural_requirements = _load_persisted_cultural_requirements(
            request_id=request_id,
            user_id=payload.user_id,
            product_id=product_id,
            attributes=attributes,
            attributes_complete=complete,
        )
        requirement_by_id = {item.requirement_id: item for item in persisted_cultural_requirements}
        for item in request_cultural_requirements:
            requirement_by_id.setdefault(item.requirement_id, item)
        cultural_requirements = tuple(requirement_by_id[key] for key in sorted(requirement_by_id))
        upstream_signals = (
            _safety_signal(product),
            _legal_signal(payload.context, product),
        ) + _user_constraint_signals(
            payload.user_id, product_id, attributes, complete, payload.hard_constraints,
        )
        persisted_preferences = _load_persisted_npl_preferences(
            request_id=request_id,
            user_id=payload.user_id,
            product_id=product_id,
            attributes=attributes,
        )
        # Durable provider values take precedence over request-local IDs; explicit
        # request exclusions may add a veto but cannot erase a persisted veto.
        preference_by_id = {item.preference_id: item for item in persisted_preferences}
        for item in explicit_negative_preferences:
            preference_by_id.setdefault(item.preference_id, item)
        negative_preferences = tuple(preference_by_id[key] for key in sorted(preference_by_id))
        estimate = _fit_estimate(payload.user_id, product_id)
        fit_required_evidence, fit_observed_evidence = _fit_evidence_fields(estimate)
        result = evaluate_candidate(
            request_id=request_id,
            candidate_id=product_id,
            eepl_policy=eepl_policy,
            context=context,
            usi_profile=profile,
            candidate_attributes=attributes,
            candidate_attributes_complete=complete,
            negative_preferences=negative_preferences,
            fit_estimate=estimate,
            cultural_requirements=cultural_requirements,
            fit_required_evidence=fit_required_evidence,
            fit_observed_evidence=fit_observed_evidence,
            upstream_signals=upstream_signals,
            policy_version=POLICY_VERSION,
        )
        arbitration = result.arbitration
        reasons = [
            ReasonOutput(code=reason.code, signal_id=reason.signal_id, explanation=reason.explanation)
            for reason in arbitration.reasons
        ]
        verdict = arbitration.verdict.value
        try:
            _record_audit(
                request_id=request_id,
                product_id=product_id,
                verdict=verdict,
                reasons=[reason.model_dump() for reason in reasons],
                catalog_version=int(product["catalog_version"]),
                arbitration_contract_version=arbitration.contract_version,
                pipeline_contract_version=result.contract_version,
                policy_version=arbitration.policy_version,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "DECISION_AUDIT_UNAVAILABLE", "message": "Decision audit persistence failed; no candidate decision is being released."},
            ) from exc

        candidates.append(CandidateDecisionOutput(
            product_id=product_id,
            sku=str(product["sku"]),
            name=str(product["name"]),
            category=str(product["category"]),
            brand=product.get("brand"),
            price_minor=int(product["price_minor"]),
            currency=str(product["currency"]),
            image_urls=product.get("image_urls") if isinstance(product.get("image_urls"), list) else [],
            catalog_version=int(product["catalog_version"]),
            verdict=verdict,
            may_display=arbitration.may_display,
            reasons=reasons,
            policy_version=arbitration.policy_version,
            arbitration_contract_version=arbitration.contract_version,
            decision_pipeline_contract_version=result.contract_version,
        ))

    return DecisionResponse(
        schema_version="1.0",
        request_id=request_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        candidates=candidates,
    )

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
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
from npl import NegativePreference, PreferenceSource, TargetType, canonical_npl_evidence_payload, evaluate as evaluate_npl  # noqa: E402
from usi import StylePreference, USIProfile  # noqa: E402
from app.comparison import compare_like_for_like_offers  # noqa: E402

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
    # Context is explicitly sourced; user-declared context is never represented as provider-verified.
    location_source: Literal["user_declared", "consented_device"] | None = None
    location_observed_at: str | None = Field(default=None, max_length=64)
    occasion_source: Literal["user_declared"] | None = None
    occasion_observed_at: str | None = Field(default=None, max_length=64)
    climate_source: Literal["user_declared", "weather_provider"] | None = None
    climate_observed_at: str | None = Field(default=None, max_length=64)


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
    use_wardrobe_context: bool = False
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



class DiscoveryRequest(BaseModel):
    """Live catalog/offer search request; identity is verified separately."""
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=2, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    limit: int = Field(default=10, ge=1, le=25)
    context: ContextInput = Field(default_factory=ContextInput)
    use_wardrobe_context: bool = False
    exclude_owned_products: bool = True
    negative_preferences: list[NegativePreferenceInput] = Field(default_factory=list, max_length=100)
    cultural_requirements: list[CulturalRequirementInput] = Field(default_factory=list, max_length=60)
    hard_constraints: list[HardConstraintInput] = Field(default_factory=list, max_length=60)

    @field_validator("user_id", "query")
    @classmethod
    def normalize_discovery_text(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized



class USIProfilePreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preference_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, gt=0, le=1)
    active: bool = True


class USIProfileUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int | None = Field(default=None, ge=0)
    preferences: list[USIProfilePreferenceInput] = Field(max_length=100)


class ConsentReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: str = Field(min_length=8, max_length=128)
    scope: Literal["personalization", "style_learning", "profile_storage"]
    consent_version: str = Field(min_length=1, max_length=80)
    granted: bool


class TALObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=160)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    feature_key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    observed_at: str
    expires_at: str | None = None
    event_kind: Literal["observation", "correction"] = "observation"
    supersedes_event_id: str | None = Field(default=None, max_length=128)


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


class TariDailyLooksRequest(BaseModel):
    """Daily-look request from the trusted same-origin BFF."""
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    local_date: str = Field(min_length=10, max_length=10)
    occasion: str | None = Field(default=None, max_length=120)
    climate: str | None = Field(default=None, max_length=80)
    wardrobe_items: list[dict[str, Any]] = Field(max_length=150)

    @field_validator("request_id", "user_id")
    @classmethod
    def trim_tari_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifier must not be blank")
        return normalized

    @field_validator("local_date")
    @classmethod
    def validate_tari_date(cls, value: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("local_date must be an ISO calendar date") from exc
        return value


class ReasonOutput(BaseModel):
    code: str
    explanation: str
    signal_id: str | None = None


class CandidateDecisionOutput(BaseModel):
    # Product merchandising fields are omitted unless CAL returns SHOW.
    product_id: str
    sku: str | None = None
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    price_minor: int | None = None
    currency: str | None = None
    image_urls: list[str] = Field(default_factory=list)
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


def _tari_npl_provider_configured() -> bool:
    """Tari must not recommend wardrobe pieces when its hard-exclusion owner is unavailable."""
    base = os.getenv("NPL_SERVICE_URL", "").strip()
    token = os.getenv("NPL_SERVICE_TOKEN", "").strip()
    secret = os.getenv("NPL_EVIDENCE_HMAC_SECRET", "").strip()
    return bool(
        base
        and _trusted_internal_base_url(base)
        and len(token.encode("utf-8")) >= 32
        and len(secret.encode("utf-8")) >= 32
    )


def _filter_npl_blocked_wardrobe_items(
    *, request_id: str, user_id: str, wardrobe_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Apply the persistent NPL hard-veto kernel to each owner-scoped closet item."""
    if not wardrobe_items:
        return [], 0

    def evaluate_item(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        attributes = tuple(
            [str(item.get("display_name", "")), str(item.get("category", ""))]
            + [value for value in item.get("attributes", []) if isinstance(value, str)]
        )
        preferences = _load_persisted_npl_preferences(
            request_id=request_id,
            user_id=user_id,
            product_id=item["item_id"],
            attributes=attributes,
        )
        decision = evaluate_npl(user_id, item["item_id"], attributes, preferences)
        return item, decision.blocked

    with ThreadPoolExecutor(max_workers=min(5, len(wardrobe_items))) as executor:
        evaluated = list(executor.map(evaluate_item, wardrobe_items))
    allowed = [item for item, blocked in evaluated if not blocked]
    return allowed, len(evaluated) - len(allowed)


def _tari_daily_looks(payload: TariDailyLooksRequest, style_signals: list[str], feedback_signals: list[str]) -> dict[str, Any]:
    """Call the internal wardrobe-only composer and verify every returned item ID."""
    base = os.getenv("COMPLEMENTER_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("COMPLEMENTER_SERVICE_TOKEN", "").strip()
    if not base or len(token.encode("utf-8")) < 32 or not _trusted_internal_base_url(base):
        raise HTTPException(503, detail={"code": "TARI_PROVIDER_CONFIGURATION_INVALID"})

    body = payload.model_dump(mode="json")
    body["style_signals"] = style_signals[:40]
    body["feedback_signals"] = feedback_signals[:40]
    try:
        with httpx.Client(
            timeout=httpx.Timeout(8.0, connect=2.0),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.post(
                f"{base}/v1/tari/daily-looks",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "TARI_PROVIDER_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "TARI_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code == 403:
        raise HTTPException(403, detail={"code": "TARI_WARDROBE_SCOPE_REJECTED"})
    if response.status_code == 422:
        raise HTTPException(422, detail={"code": "TARI_REQUEST_REJECTED"})
    if response.status_code in {401, 502, 503, 504} or response.status_code < 200 or response.status_code >= 300:
        raise HTTPException(503, detail={"code": "TARI_PROVIDER_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "TARI_INVALID_RESPONSE"}) from exc

    roles = ["everyday", "elevated", "explore"]
    owned_ids = {
        item["item_id"] for item in payload.wardrobe_items
        if isinstance(item, dict) and item.get("owner_user_id") == payload.user_id and item.get("status") == "active"
        and isinstance(item.get("item_id"), str)
    }
    looks = result.get("looks") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or result.get("schema_version") != "1.0"
        or result.get("request_id") != payload.request_id
        or result.get("capability") != "tari_daily_looks"
        or result.get("look_count") != 3
        or result.get("status") not in {"ready", "partial", "needs_input"}
        or not isinstance(looks, list)
        or len(looks) != 3
        or [item.get("role") if isinstance(item, dict) else None for item in looks] != roles
    ):
        raise HTTPException(502, detail={"code": "TARI_RESPONSE_SCHEMA_INVALID"})

    for look in looks:
        item_ids = look.get("item_ids")
        if not isinstance(item_ids, list) or any(not isinstance(item_id, str) or item_id not in owned_ids for item_id in item_ids):
            raise HTTPException(502, detail={"code": "TARI_RESPONSE_WARDROBE_SCOPE_MISMATCH"})
        preview = look.get("virtual_twin_preview")
        if not isinstance(preview, dict) or preview.get("status") != "unavailable":
            raise HTTPException(502, detail={"code": "TARI_TWIN_PREVIEW_STATE_INVALID"})
    return {
        "schema_version": "1.0",
        "request_id": payload.request_id,
        "mode": "tari_wardrobe_daily_looks",
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
    # Secure by default. Unverified request-scoped profiles are an explicit
    # local/test-only opt-out and must never be the implicit deployment mode.
    return os.getenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "true").strip().lower() == "true"


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
    if (
        not isinstance(subject, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}", subject.strip())
    ):
        raise HTTPException(502, detail={"code": "COMMERCE_IDENTITY_SUBJECT_INVALID"})
    return subject.strip()


def _load_verified_usi_profile(subject_id: str, *, allow_without_consent: bool = False) -> USIProfile:
    """Hydrate only the profile belonging to a Commerce-verified subject.

    Wardrobe discovery may proceed with an empty profile when the user has not
    granted profile_storage. This does not read or persist profile data.
    """
    base = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if not base and not token and allow_without_consent:
        return USIProfile(
            profile_id=f"usi-empty:{subject_id}",
            user_id=subject_id,
            version="profile-storage-provider-not-configured",
            preferences=(),
        )
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "USI_PROFILE_PROVIDER_CONFIGURATION_INVALID"})
    try:
        with httpx.Client(timeout=httpx.Timeout(4.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = client.get(
                f"{base}/v1/profiles/{subject_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "USI_PROFILE_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code == 403:
        if allow_without_consent:
            return USIProfile(
                profile_id=f"usi-empty:{subject_id}",
                user_id=subject_id,
                version="profile-storage-consent-not-granted",
                preferences=(),
            )
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
        or isinstance(data.get("profile_version"), bool)
        or data["profile_version"] < 0
        or not isinstance(data.get("preferences"), list)
        or len(data["preferences"]) > 100
    ):
        raise HTTPException(502, detail={"code": "USI_PROFILE_SCOPE_OR_SCHEMA_MISMATCH"})
    preferences = []
    for item in data["preferences"]:
        if not isinstance(item, dict):
            raise HTTPException(502, detail={"code": "USI_PROFILE_SCHEMA_INVALID"})
        active = item.get("active", True)
        weight = item.get("weight", 1.0)
        if not isinstance(active, bool) or isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise HTTPException(502, detail={"code": "USI_PROFILE_SCHEMA_INVALID"})
        try:
            preferences.append(StylePreference(
                preference_id=item["preference_id"],
                user_id=subject_id,
                attribute=item["attribute"],
                weight=float(weight),
                active=active,
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(502, detail={"code": "USI_PROFILE_SCHEMA_INVALID"}) from exc
    return USIProfile(
        profile_id=f"usi:{subject_id}",
        user_id=subject_id,
        version=str(data["profile_version"]),
        preferences=tuple(preferences),
    )




def _load_verified_wardrobe(subject_id: str) -> list[dict[str, Any]]:
    """Load only active items for the Commerce-verified subject."""
    base = os.getenv("WARDROBE_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("WARDROBE_SERVICE_TOKEN", "").strip()
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "WARDROBE_PROVIDER_NOT_CONFIGURED"})
    try:
        with httpx.Client(
            timeout=httpx.Timeout(4.0, connect=1.5),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.get(
                base + "/v1/items",
                params={"owner_user_id": subject_id, "include_archived": "false"},
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_PROVIDER_UNAVAILABLE"})
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(result, dict)
        or result.get("owner_user_id") != subject_id
        or not isinstance(result.get("items"), list)
    ):
        raise HTTPException(502, detail={"code": "WARDROBE_SCOPE_OR_SCHEMA_MISMATCH"})
    items: list[dict[str, Any]] = []
    for item in result["items"]:
        if not isinstance(item, dict):
            raise HTTPException(502, detail={"code": "WARDROBE_ITEM_SCHEMA_INVALID"})
        if item.get("owner_user_id") != subject_id:
            raise HTTPException(502, detail={"code": "WARDROBE_CROSS_SUBJECT_ITEM"})
        if item.get("status") != "active":
            continue
        if (
            not isinstance(item.get("item_id"), str)
            or not isinstance(item.get("category"), str)
            or not isinstance(item.get("attributes"), list)
            or any(not isinstance(value, str) or not value.strip() for value in item["attributes"])
        ):
            raise HTTPException(502, detail={"code": "WARDROBE_ITEM_SCHEMA_INVALID"})
        items.append(item)
    return items



def _load_consent_aware_wardrobe_likes(subject_id: str) -> dict[str, float]:
    """Use only current-consent, unexpired like/wear TAL events for positive ranking.

    Revoked or missing style-learning consent means historical events are not
    used. NPL remains the separate owner of negative preference enforcement.
    """
    base = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if not base and not token:
        # No granted learning receipt can exist without the provider; wardrobe-only
        # suggestions remain available but receive no historical learning bonus.
        return {}
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "WARDROBE_LEARNING_PROVIDER_CONFIGURATION_INVALID"})
    try:
        with httpx.Client(
            timeout=httpx.Timeout(4.0, connect=1.5),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.get(
                base + f"/v1/tal/export/{subject_id}",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_LEARNING_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "WARDROBE_LEARNING_PROVIDER_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "WARDROBE_LEARNING_RESPONSE_INVALID"}) from exc
    if (
        not isinstance(data, dict)
        or data.get("subject_id") != subject_id
        or not isinstance(data.get("consent_receipts"), list)
        or not isinstance(data.get("events"), list)
    ):
        raise HTTPException(502, detail={"code": "WARDROBE_LEARNING_SCOPE_OR_SCHEMA_MISMATCH"})

    now = datetime.now(timezone.utc)
    active_receipts: set[str] = set()
    for receipt in data["consent_receipts"]:
        if not isinstance(receipt, dict):
            continue
        if (
            receipt.get("scope") in {"style_learning", "personalization"}
            and receipt.get("granted") is True
            and receipt.get("revoked_at") is None
            and isinstance(receipt.get("receipt_id"), str)
        ):
            active_receipts.add(receipt["receipt_id"])
    if not active_receipts:
        return {}

    counts: dict[str, int] = {}
    # Bound work and output; one noisy event stream cannot dominate the rank.
    for event in data["events"][-500:]:
        if not isinstance(event, dict):
            continue
        if (
            event.get("event_kind") != "observation"
            or event.get("feature_key") not in {"wardrobe.feedback.like", "wardrobe.feedback.wear"}
            or event.get("consent_receipt_id") not in active_receipts
            or not isinstance(event.get("value"), str)
        ):
            continue
        try:
            observed = datetime.fromisoformat(str(event.get("observed_at", "")).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                continue
            observed = observed.astimezone(timezone.utc)
            expires_raw = event.get("expires_at")
            if expires_raw:
                expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
                if expires.tzinfo is None or expires.astimezone(timezone.utc) <= now:
                    continue
            if observed > now + timedelta(minutes=5) or observed < now - timedelta(days=180):
                continue
            value = json.loads(event["value"])
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        attributes = value.get("attributes")
        if isinstance(attributes, list):
            for raw in attributes:
                if isinstance(raw, str) and raw.strip():
                    key = raw.strip().casefold()
                    counts[key] = min(5, counts.get(key, 0) + 1)
        category = value.get("category")
        if isinstance(category, str) and category.strip():
            key = category.strip().casefold()
            counts[key] = min(5, counts.get(key, 0) + 1)
    return {key: min(0.15, count * 0.03) for key, count in counts.items()}



def _wardrobe_feature_values(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("category", "")).strip().casefold(),
        *(value.strip().casefold() for value in item.get("attributes", []) if isinstance(value, str) and value.strip()),
    }
    values.discard("")
    return values


def _product_feature_values(product: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.add(value.strip().casefold())
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
    visit(product.get("attributes", {}))
    visit(product.get("category"))
    return values


def _wardrobe_match(
    product: dict[str, Any], wardrobe_items: list[dict[str, Any]],
    positive_feedback: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return transparent exact-tag overlaps; this is a ranking hint, not a probability."""
    product_values = _product_feature_values(product)
    matched: list[tuple[str, list[str]]] = []
    for item in wardrobe_items:
        overlap = sorted(product_values.intersection(_wardrobe_feature_values(item)))
        if overlap:
            matched.append((item["item_id"], overlap))
    matched.sort(key=lambda value: value[0])
    attributes = sorted({tag for _, tags in matched for tag in tags})
    closet_score = min(0.25, 0.05 * len(attributes))
    learned = positive_feedback or {}
    learned_hits = sorted(tag for tag in product_values if tag in learned)
    learned_score = min(0.15, sum(max(0.0, min(0.15, float(learned[tag]))) for tag in learned_hits))
    score = min(0.40, closet_score + learned_score)
    return {
        "score": score,
        "closet_attribute_score": closet_score,
        "consented_positive_feedback_score": learned_score,
        "owned_item_ids": [item_id for item_id, _ in matched],
        "matched_attributes": attributes,
        "positive_feedback_attributes": learned_hits,
    }


def _offer_comparison_max_age_seconds() -> int:
    try:
        configured = int(os.getenv("COMMERCE_OFFER_MAX_AGE_SECONDS", "3600"))
    except ValueError:
        configured = 3600
    return max(60, min(configured, 604800))


def _fresh_context_for_eepl(context: ContextInput, *, strict: bool) -> tuple[ContextInput, dict[str, Any]]:
    """Drop context that lacks explicit provenance, timezone or freshness."""
    now = datetime.now(timezone.utc)
    specs = (
        ("location", "location_source", "location_observed_at", 24 * 3600),
        ("occasion", "occasion_source", "occasion_observed_at", 7 * 24 * 3600),
        ("climate", "climate_source", "climate_observed_at", 6 * 3600),
    )
    values: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    for field, source_field, observed_field, max_age in specs:
        value = getattr(context, field)
        source = getattr(context, source_field)
        observed_raw = getattr(context, observed_field)
        status = "unknown"
        if value is not None and (not strict or (source and observed_raw)):
            if not strict and not source and not observed_raw:
                values[field] = value
                status = "legacy_explicit_value"
            else:
                try:
                    observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
                    if observed.tzinfo is None:
                        raise ValueError("timezone required")
                    observed = observed.astimezone(timezone.utc)
                    age = (now - observed).total_seconds()
                    if -300 <= age <= max_age:
                        values[field] = value
                        status = "current"
                    else:
                        values[field] = None
                        status = "stale_or_future"
                except (AttributeError, TypeError, ValueError):
                    values[field] = None
                    status = "invalid_timestamp"
        else:
            values[field] = None
            status = "missing_value_or_provenance"
        evidence[field] = {
            "status": status,
            "source": source if status == "current" or status == "legacy_explicit_value" else None,
            "observed_at": observed_raw if status == "current" else None,
            "max_age_seconds": max_age,
        }
    normalized = ContextInput(
        age_years=context.age_years,
        location=values["location"],
        occasion=values["occasion"],
        climate=values["climate"],
        location_source=context.location_source,
        location_observed_at=context.location_observed_at,
        occasion_source=context.occasion_source,
        occasion_observed_at=context.occasion_observed_at,
        climate_source=context.climate_source,
        climate_observed_at=context.climate_observed_at,
    )
    return normalized, evidence


def _identity_service_request(method: str, path: str, subject_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "IDENTITY_SERVICE_NOT_CONFIGURED"})
    params = {"subject_id": subject_id}
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = client.request(
                method, base + path,
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                params=params,
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "IDENTITY_SERVICE_UNAVAILABLE"}) from exc
    try:
        data = response.json() if response.content else {}
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "IDENTITY_SERVICE_RESPONSE_INVALID"}) from exc
    if response.status_code in {400, 401, 403, 404, 409, 422}:
        raise HTTPException(response.status_code, detail=data.get("detail", data))
    if response.status_code < 200 or response.status_code >= 300 or not isinstance(data, dict):
        raise HTTPException(503, detail={"code": "IDENTITY_SERVICE_REQUEST_FAILED"})
    return data


def _verified_actor_from_header(end_user_authorization: str | None) -> str:
    return _resolve_verified_subject(end_user_authorization)



def _discover_catalog_and_offers(payload: DiscoveryRequest) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join canonical active Catalog products to currently purchasable Commerce offers."""
    catalog_base = os.getenv("CATALOG_SERVICE_URL", "").strip().rstrip("/")
    catalog_token = os.getenv("CATALOG_API_TOKEN", "").strip()
    commerce_base = os.getenv("COMMERCE_API_URL", "").strip().rstrip("/")
    if not catalog_base or not _trusted_internal_base_url(catalog_base) or len(catalog_token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "CATALOG_DISCOVERY_NOT_CONFIGURED"})
    if not commerce_base or not _trusted_internal_base_url(commerce_base):
        raise HTTPException(503, detail={"code": "COMMERCE_OFFERS_NOT_CONFIGURED"})
    params: dict[str, Any] = {"q": payload.query, "limit": payload.limit}
    if payload.category:
        params["category"] = payload.category
    catalog_items: list[dict[str, Any]] = []
    offer_items: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            catalog_response = client.get(
                catalog_base + "/products",
                params=params,
                headers={"Authorization": "Bearer " + catalog_token, "Accept": "application/json"},
            )
            if catalog_response.status_code != 200:
                raise HTTPException(503, detail={"code": "CATALOG_DISCOVERY_UNAVAILABLE"})
            catalog_payload = catalog_response.json()
            if not isinstance(catalog_payload, dict) or not isinstance(catalog_payload.get("items"), list):
                raise HTTPException(502, detail={"code": "CATALOG_DISCOVERY_RESPONSE_INVALID"})
            catalog_items = [x for x in catalog_payload["items"] if isinstance(x, dict) and x.get("status") == "active" and isinstance(x.get("product_id"), str)]
            offer_params: dict[str, Any] = {"q": payload.query, "limit": payload.limit}
            if payload.category:
                offer_params["category"] = payload.category
            if payload.currency:
                offer_params["currency"] = payload.currency.upper()
            offer_response = client.get(commerce_base + "/marketplace/offers", params=offer_params, headers={"Accept": "application/json"})
            if offer_response.status_code != 200:
                raise HTTPException(503, detail={"code": "COMMERCE_OFFERS_UNAVAILABLE"})
            offer_payload = offer_response.json()
            if not isinstance(offer_payload, dict) or not isinstance(offer_payload.get("items"), list):
                raise HTTPException(502, detail={"code": "COMMERCE_OFFERS_RESPONSE_INVALID"})
            offer_items = [x for x in offer_payload["items"] if isinstance(x, dict)]
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, detail={"code": "MARKETPLACE_DISCOVERY_UNAVAILABLE"}) from exc
    catalog_ids = {item["product_id"] for item in catalog_items}
    joined = [offer for offer in offer_items if offer.get("catalog_product_id") in catalog_ids]
    return catalog_items, joined


def _style_rank_score(product: dict[str, Any], profile: USIProfile) -> float:
    """Deterministic preference match for ordering only; never a probability or display gate."""
    active = [item for item in profile.preferences if item.active]
    if not active:
        return 0.0
    values: set[str] = set()
    def visit(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.add(value.strip().casefold())
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
    visit(product.get("attributes", {}))
    visit(product.get("category"))
    visit(product.get("brand"))
    total = sum(item.weight for item in active)
    matched = sum(item.weight for item in active if item.attribute.strip().casefold() in values)
    return matched / total if total else 0.0



def _canonical_provider_json(payload: dict[str, Any]) -> bytes:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(502, detail={"code": "EVIDENCE_PROVIDER_PAYLOAD_INVALID"}) from exc


def _provider_manifest_valid(manifest: Any, *, prefix: str, expected_scope: str, model_version: str, provider_id: str) -> bool:
    if not isinstance(manifest, dict):
        return False
    secret = os.getenv(prefix + "_VALIDATION_HMAC_SECRET", "").strip()
    expected_hash = os.getenv(prefix + "_VALIDATION_REPORT_SHA256", "").strip().lower()
    signature = manifest.get("signature")
    if len(secret.encode("utf-8")) < 32 or not expected_hash or not isinstance(signature, str):
        return False
    unsigned = {key: value for key, value in manifest.items() if key != "signature"}
    expected_signature = hmac.new(secret.encode("utf-8"), _canonical_provider_json(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature.lower()):
        return False
    if (
        manifest.get("report_sha256") != expected_hash
        or manifest.get("scope") != expected_scope
        or manifest.get("model_version") != model_version
        or manifest.get("independent_validation") is not True
        or not isinstance(manifest.get("evaluator_id"), str)
        or not manifest.get("evaluator_id").strip()
        or not isinstance(provider_id, str)
        or not provider_id.strip()
        or manifest.get("evaluator_id") == provider_id
    ):
        return False
    try:
        validated_at = datetime.fromisoformat(str(manifest["validated_at"]).replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(str(manifest["valid_until"]).replace("Z", "+00:00"))
        if validated_at.tzinfo is None or valid_until.tzinfo is None:
            return False
        now = datetime.now(timezone.utc)
        return validated_at <= now and valid_until > now
    except (KeyError, TypeError, ValueError):
        return False


def _verify_provider_signature(payload: dict[str, Any], *, prefix: str, signature_field: str) -> None:
    secret = os.getenv(prefix + "_EVIDENCE_HMAC_SECRET", "").strip()
    signature = payload.get(signature_field)
    if len(secret.encode("utf-8")) < 32 or not isinstance(signature, str):
        raise HTTPException(503, detail={"code": prefix + "_EVIDENCE_AUTH_NOT_CONFIGURED"})
    unsigned = {key: value for key, value in payload.items() if key != signature_field}
    expected = hmac.new(secret.encode("utf-8"), _canonical_provider_json(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(502, detail={"code": prefix + "_EVIDENCE_SIGNATURE_INVALID"})


def _call_evidence_provider(prefix: str, body: dict[str, Any]) -> dict[str, Any]:
    base = os.getenv(prefix + "_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv(prefix + "_SERVICE_TOKEN", "").strip()
    if not base or not _trusted_internal_base_url(base) or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": prefix + "_PROVIDER_NOT_CONFIGURED"})
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.5), trust_env=False, follow_redirects=False) as client:
            response = client.post(
                base + "/v1/evaluate",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": prefix + "_PROVIDER_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": prefix + "_PROVIDER_UNAVAILABLE"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": prefix + "_PROVIDER_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict):
        raise HTTPException(502, detail={"code": prefix + "_PROVIDER_RESPONSE_INVALID"})
    return data


def _load_safety_signal(product: dict[str, Any], *, user_id: str, request_id: str) -> DecisionSignal:
    """Use only independently attested, candidate-bound product-safety evidence."""
    prefix = "SAFETY"
    keys = ("SAFETY_SERVICE_URL", "SAFETY_SERVICE_TOKEN", "SAFETY_EVIDENCE_HMAC_SECRET", "SAFETY_VALIDATION_HMAC_SECRET", "SAFETY_VALIDATION_REPORT_SHA256")
    if not any(os.getenv(key, "").strip() for key in keys):
        return _safety_signal(product)
    snapshot_hash = hashlib.sha256(_canonical_provider_json(product)).hexdigest()
    result = _call_evidence_provider(prefix, {
        "request_id": request_id, "user_id": user_id, "candidate_id": product["product_id"],
        "product_snapshot_sha256": snapshot_hash,
    })
    _verify_provider_signature(result, prefix=prefix, signature_field="evidence_signature")
    if (
        result.get("request_id") != request_id
        or result.get("user_id") != user_id
        or result.get("candidate_id") != product["product_id"]
        or result.get("product_snapshot_sha256") != snapshot_hash
        or result.get("state") not in {"pass", "block", "unknown"}
        or not isinstance(result.get("evidence_id"), str)
        or not isinstance(result.get("model_version"), str)
        or not _provider_manifest_valid(
            result.get("validation_manifest"), prefix=prefix,
            expected_scope="product_safety", model_version=result.get("model_version", ""),
            provider_id=str(result.get("provider_id", "")),
        )
    ):
        raise HTTPException(502, detail={"code": "SAFETY_PROVIDER_EVIDENCE_UNTRUSTED"})
    state = {"pass": SignalState.PASS, "block": SignalState.BLOCK, "unknown": SignalState.UNKNOWN}[result["state"]]
    return DecisionSignal(
        signal_id=f"safety:{result['evidence_id']}:{product['product_id']}",
        kind=SignalKind.SAFETY, state=state,
        reason_code=str(result.get("reason_code", "SAFETY_PROVIDER_UNKNOWN")),
        explanation=str(result.get("explanation", "Independent product-safety provider supplied no explanation.")),
        required=True, source_version=f"{result['model_version']}:{result['validation_manifest']['report_sha256']}",
    )


def _load_fci_estimate(user_id: str, product_id: str, request_id: str, product: dict[str, Any]) -> FitConfidenceEstimate:
    """Load a calibrated, signed, independently validated FCI estimate or remain UNKNOWN."""
    prefix = "FCI"
    keys = ("FCI_SERVICE_URL", "FCI_SERVICE_TOKEN", "FCI_EVIDENCE_HMAC_SECRET", "FCI_VALIDATION_HMAC_SECRET", "FCI_VALIDATION_REPORT_SHA256")
    if not any(os.getenv(key, "").strip() for key in keys):
        return _fit_estimate(user_id, product_id)
    snapshot_hash = hashlib.sha256(_canonical_provider_json(product)).hexdigest()
    result = _call_evidence_provider(prefix, {
        "request_id": request_id, "user_id": user_id, "candidate_id": product_id,
        "product_snapshot_sha256": snapshot_hash,
    })
    _verify_provider_signature(result, prefix=prefix, signature_field="evidence_signature")
    model_version = result.get("model_version")
    if (
        result.get("request_id") != request_id
        or result.get("user_id") != user_id
        or result.get("candidate_id") != product_id
        or result.get("product_snapshot_sha256") != snapshot_hash
        or result.get("calibrated") is not True
        or not isinstance(model_version, str)
        or not _provider_manifest_valid(
            result.get("validation_manifest"), prefix=prefix,
            expected_scope="fit_confidence", model_version=model_version,
            provider_id=str(result.get("provider_id", "")),
        )
        or not isinstance(result.get("evidence_ids"), list)
        or not isinstance(result.get("required_evidence_fields"), list)
        or not isinstance(result.get("observed_evidence_fields"), list)
    ):
        raise HTTPException(502, detail={"code": "FCI_PROVIDER_EVIDENCE_UNTRUSTED"})
    try:
        return FitConfidenceEstimate(
            estimate_id=str(result["estimate_id"]), user_id=user_id, candidate_id=product_id,
            model_version=model_version, calibrated=True,
            confidence=float(result["confidence"]), lower_bound=float(result["lower_bound"]),
            upper_bound=float(result["upper_bound"]), calibration_version=str(result["calibration_version"]),
            evidence_ids=tuple(str(x) for x in result["evidence_ids"]),
            interval_level=float(result.get("interval_level", 0.95)),
            required_evidence_fields=tuple(str(x) for x in result["required_evidence_fields"]),
            observed_evidence_fields=tuple(str(x) for x in result["observed_evidence_fields"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, detail={"code": "FCI_PROVIDER_ESTIMATE_INVALID"}) from exc


def _fit_evidence_fields(estimate: FitConfidenceEstimate) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return field-level evidence coverage supplied by the signed FCI provider."""
    return estimate.required_evidence_fields, estimate.observed_evidence_fields


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
        "tari_daily_look_orchestration_configured": bool(
            os.getenv("COMPLEMENTER_SERVICE_URL")
            and len(os.getenv("COMPLEMENTER_SERVICE_TOKEN", "").encode("utf-8")) >= 32
            and _trusted_internal_base_url(os.getenv("COMPLEMENTER_SERVICE_URL", ""))
        ),
        "tari_daily_look_roles": ["everyday", "elevated", "explore"],
        "tari_requires_persistent_npl": True,
        "tari_npl_provider_configured": _tari_npl_provider_configured(),
        "tari_virtual_twin_preview_enabled": False,
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
        "calibrated_fci_provider": all(
            os.getenv(key, "").strip() for key in (
                "FCI_SERVICE_URL", "FCI_SERVICE_TOKEN", "FCI_EVIDENCE_HMAC_SECRET",
                "FCI_VALIDATION_HMAC_SECRET", "FCI_VALIDATION_REPORT_SHA256",
            )
        ),
        "independent_safety_policy_provider": all(
            os.getenv(key, "").strip() for key in (
                "SAFETY_SERVICE_URL", "SAFETY_SERVICE_TOKEN", "SAFETY_EVIDENCE_HMAC_SECRET",
                "SAFETY_VALIDATION_HMAC_SECRET", "SAFETY_VALIDATION_REPORT_SHA256",
            )
        ),
        "persisted_user_profiles": bool(
            _verified_identity_required()
            and os.getenv("IDENTITY_SERVICE_URL")
            and len(os.getenv("IDENTITY_SERVICE_TOKEN", "").encode("utf-8")) >= 32
        ),
        "durable_temporal_learning": bool(
            os.getenv("IDENTITY_SERVICE_URL")
            and len(os.getenv("IDENTITY_SERVICE_TOKEN", "").encode("utf-8")) >= 32
        ),
        "identity_provider_binding": bool(
            _verified_identity_required()
            and os.getenv("COMMERCE_API_URL")
            and _trusted_internal_base_url(os.getenv("COMMERCE_API_URL", ""))
        ),
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
    identity_required = _verified_identity_required()
    identity_ready = False
    identity_url = os.getenv("IDENTITY_SERVICE_URL", "").strip().rstrip("/")
    identity_token = os.getenv("IDENTITY_SERVICE_TOKEN", "").strip()
    if identity_url and _trusted_internal_base_url(identity_url) and len(identity_token.encode("utf-8")) >= 32:
        try:
            with httpx.Client(timeout=httpx.Timeout(2.0, connect=1.0), trust_env=False, follow_redirects=False) as client:
                response = client.get(identity_url + "/ready", headers={"Authorization": "Bearer " + identity_token})
            identity_ready = response.status_code == 200 and response.json().get("ready") is True
        except (httpx.HTTPError, ValueError):
            identity_ready = False
    commerce_url = os.getenv("COMMERCE_API_URL", "").strip()
    identity_binding_configured = bool(
        identity_required and identity_ready and commerce_url and _trusted_internal_base_url(commerce_url)
    )
    ready = configured and catalog_ready and audit_ready and policy_configured and (not identity_required or identity_binding_configured)
    return {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE_NAME,
        "gateway_auth_configured": bool(os.getenv("CIRVANNA_API_TOKEN")),
        "catalog_auth_configured": bool(os.getenv("CATALOG_API_TOKEN")),
        "catalog_ready": catalog_ready,
        "audit_store_ready": audit_ready,
        "policy_configuration_valid": policy_configured,
        "identity_provider_binding": identity_binding_configured,
        "identity_learning_service_ready": identity_ready,
        "fci_available": all(os.getenv(key, "").strip() for key in ("FCI_SERVICE_URL", "FCI_SERVICE_TOKEN", "FCI_EVIDENCE_HMAC_SECRET", "FCI_VALIDATION_HMAC_SECRET", "FCI_VALIDATION_REPORT_SHA256")),
        "safety_policy_available": all(os.getenv(key, "").strip() for key in ("SAFETY_SERVICE_URL", "SAFETY_SERVICE_TOKEN", "SAFETY_EVIDENCE_HMAC_SECRET", "SAFETY_VALIDATION_HMAC_SECRET", "SAFETY_VALIDATION_REPORT_SHA256")),
        "decision_evidence_ready": all(os.getenv(key, "").strip() for key in ("FCI_SERVICE_URL", "FCI_SERVICE_TOKEN", "FCI_EVIDENCE_HMAC_SECRET", "FCI_VALIDATION_HMAC_SECRET", "FCI_VALIDATION_REPORT_SHA256", "SAFETY_SERVICE_URL", "SAFETY_SERVICE_TOKEN", "SAFETY_EVIDENCE_HMAC_SECRET", "SAFETY_VALIDATION_HMAC_SECRET", "SAFETY_VALIDATION_REPORT_SHA256")),
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
    "/v1/tari/daily-looks",
    dependencies=[Depends(require_api_token)],
    tags=["tari daily looks"],
)
def compose_tari_daily_looks(
    payload: TariDailyLooksRequest,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
) -> dict[str, Any]:
    """Compose three looks only from the signed-in user's wardrobe snapshot."""
    subject = _resolve_verified_subject(end_user_authorization)
    if not hmac.compare_digest(subject, payload.user_id):
        raise HTTPException(403, detail={"code": "REQUEST_SUBJECT_MISMATCH"})
    for item in payload.wardrobe_items:
        if not isinstance(item, dict) or item.get("owner_user_id") != subject:
            raise HTTPException(403, detail={"code": "WARDROBE_SUBJECT_MISMATCH"})
        if item.get("status") != "active":
            raise HTTPException(422, detail={"code": "WARDROBE_SNAPSHOT_MUST_BE_ACTIVE_ONLY"})
    # Only positive, non-sensitive fashion preference namespaces may guide ranking.
    profile = _load_verified_usi_profile(subject, allow_without_consent=True)
    allowed_prefixes = ("style:", "color:", "colour:", "silhouette:", "material:", "pattern:")
    style_signals = [
        preference.attribute.strip()
        for preference in profile.preferences
        if preference.active and preference.attribute.strip().casefold().startswith(allowed_prefixes)
    ]
    if payload.wardrobe_items and not _tari_npl_provider_configured():
        raise HTTPException(503, detail={"code": "TARI_NPL_PROVIDER_NOT_CONFIGURED"})
    eligible_items, npl_excluded_count = _filter_npl_blocked_wardrobe_items(
        request_id=payload.request_id,
        user_id=subject,
        wardrobe_items=payload.wardrobe_items,
    )
    safe_payload = payload.model_copy(update={"wardrobe_items": eligible_items})
    positive_feedback = _load_consent_aware_wardrobe_likes(subject)
    feedback_signals = [
        f"feedback:{attribute}"
        for attribute, weight in positive_feedback.items()
        if isinstance(attribute, str) and attribute.strip() and isinstance(weight, (int, float)) and weight > 0
    ][:40]
    result = _tari_daily_looks(safe_payload, style_signals, feedback_signals)
    result["npl_excluded_wardrobe_item_count"] = npl_excluded_count
    return result


@app.get("/v1/me/style-profile", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def read_my_style_profile(
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("GET", f"/v1/profiles/{subject}", subject)


@app.put("/v1/me/style-profile", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def update_my_style_profile(
    payload: USIProfileUpdateInput,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("PUT", f"/v1/profiles/{subject}", subject, payload.model_dump(mode="json"))


@app.post("/v1/me/consents", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def create_my_consent_receipt(
    payload: ConsentReceiptInput,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("POST", "/v1/tal/consents", subject, payload.model_dump(mode="json"))


@app.post("/v1/me/consents/{receipt_id}/revoke", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def revoke_my_consent_receipt(
    receipt_id: str,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("POST", f"/v1/tal/consents/{receipt_id}/revoke", subject)


@app.post("/v1/me/tal/events", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def append_my_learning_event(
    payload: TALObservationInput,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("POST", "/v1/tal/events", subject, payload.model_dump(mode="json"))


@app.get("/v1/me/tal/export", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def export_my_learning_data(
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("GET", f"/v1/tal/export/{subject}", subject)


@app.delete("/v1/me/tal/data", dependencies=[Depends(require_api_token)], tags=["identity and learning"])
def delete_my_learning_data(
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
):
    subject = _verified_actor_from_header(end_user_authorization)
    return _identity_service_request("DELETE", f"/v1/tal/users/{subject}", subject)




@app.post(
    "/v1/discover",
    dependencies=[Depends(require_api_token)],
    tags=["marketplace discovery"],
)
def discover_marketplace(
    payload: DiscoveryRequest,
    end_user_authorization: str | None = Header(default=None, alias="X-End-User-Authorization"),
) -> dict[str, Any]:
    """Retrieve live Catalog/Commerce candidates, rank them, then CAL-gate every display."""
    if not _verified_identity_required():
        raise HTTPException(503, detail={"code": "VERIFIED_IDENTITY_REQUIRED_FOR_DISCOVERY"})
    subject = _resolve_verified_subject(end_user_authorization)
    if not hmac.compare_digest(subject, payload.user_id):
        raise HTTPException(403, detail={"code": "REQUEST_SUBJECT_MISMATCH"})
    profile = (_load_verified_usi_profile(subject, allow_without_consent=True)
               if payload.use_wardrobe_context else _load_verified_usi_profile(subject))
    wardrobe_items: list[dict[str, Any]] = []
    positive_wardrobe_feedback: dict[str, float] = {}
    if payload.use_wardrobe_context:
        # The NPL ledger is mandatory for wardrobe-driven recommendations. A missing
        # or partial configuration must not silently degrade into preference-blind output.
        npl_values = (
            bool(os.getenv("NPL_SERVICE_URL", "").strip()),
            len(os.getenv("NPL_SERVICE_TOKEN", "").encode("utf-8")) >= 32,
            len(os.getenv("NPL_EVIDENCE_HMAC_SECRET", "").encode("utf-8")) >= 32,
        )
        if not all(npl_values):
            raise HTTPException(503, detail={"code": "NPL_PROVIDER_REQUIRED_FOR_WARDROBE_DISCOVERY"})
        wardrobe_items = _load_verified_wardrobe(subject)
        positive_wardrobe_feedback = _load_consent_aware_wardrobe_likes(subject)
    eepl_context, context_evidence = _fresh_context_for_eepl(
        payload.context, strict=payload.use_wardrobe_context
    )
    products, offers = _discover_catalog_and_offers(payload)
    by_product = {item["product_id"]: item for item in products}
    owned_product_ids = {
        item.get("catalog_product_id")
        for item in wardrobe_items
        if isinstance(item.get("catalog_product_id"), str)
    }
    best_offer: dict[str, dict[str, Any]] = {}
    withheld_reasons: dict[str, str] = {}
    for offer in offers:
        product_id = offer.get("catalog_product_id")
        if not isinstance(product_id, str) or product_id not in by_product:
            continue
        price = offer.get("price_minor")
        currency = offer.get("currency")
        available = offer.get("available_stock")
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            continue
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            continue
        if isinstance(available, bool) or not isinstance(available, int) or available <= 0:
            continue
        if payload.currency and currency != payload.currency.upper():
            continue
        product_currency = by_product[product_id].get("currency")
        target_currency = payload.currency.upper() if payload.currency else product_currency
        if isinstance(target_currency, str) and re.fullmatch(r"[A-Z]{3}", target_currency):
            if currency != target_currency.upper():
                continue
        current = best_offer.get(product_id)
        if current is None:
            best_offer[product_id] = offer
        elif current.get("currency") != currency:
            withheld_reasons[product_id] = "OFFER_CURRENCY_AMBIGUOUS"
        elif (price, str(offer.get("merchant_id", "")), str(offer.get("variant_id", ""))) < (
            current["price_minor"], str(current.get("merchant_id", "")), str(current.get("variant_id", ""))
        ):
            best_offer[product_id] = offer

    candidates = []
    for product_id, offer in best_offer.items():
        product = by_product[product_id]
        if payload.use_wardrobe_context and payload.exclude_owned_products and product_id in owned_product_ids:
            withheld_reasons[product_id] = "ALREADY_IN_WARDROBE"
            continue
        wardrobe_match = _wardrobe_match(product, wardrobe_items, positive_wardrobe_feedback) if payload.use_wardrobe_context else {
            "score": 0.0, "closet_attribute_score": 0.0,
            "consented_positive_feedback_score": 0.0,
            "owned_item_ids": [], "matched_attributes": [], "positive_feedback_attributes": [],
        }
        usi_score = _style_rank_score(product, profile)
        total_score = usi_score + wardrobe_match["score"]
        candidates.append((product_id, total_score, usi_score, wardrobe_match, offer))
    candidates.sort(key=lambda item: (
        -item[1], item[4]["currency"], item[4]["price_minor"], item[0]
    ))
    ranked = candidates[:payload.limit]
    if not ranked:
        return {
            "request_id": str(uuid.uuid4()),
            "ranked_candidate_count": 0,
            "displayable_products": [],
            "withheld_candidate_ids": [
                {"product_id": pid, "decision": reason.lower(), "reason_code": reason}
                for pid, reason in sorted(withheld_reasons.items())
            ],
            "display_authority": "CaTaCaCi/CAL",
            "eepl_context_evidence": context_evidence,
            "wardrobe_context": {
                "used": payload.use_wardrobe_context,
                "active_item_count": len(wardrobe_items),
                "excluded_owned_product_count": sum(1 for reason in withheld_reasons.values() if reason == "ALREADY_IN_WARDROBE"),
            },
        }
    decision_request = DecisionRequest(
        user_id=subject,
        product_ids=[item[0] for item in ranked],
        context=eepl_context,
        use_wardrobe_context=payload.use_wardrobe_context,
        style_preferences=[],
        negative_preferences=payload.negative_preferences,
        cultural_requirements=payload.cultural_requirements,
        hard_constraints=payload.hard_constraints,
    )
    decision_response = evaluate_decisions(decision_request, end_user_authorization)
    decisions = {item.product_id: item for item in decision_response.candidates}
    displayable = []
    comparisons_by_product = {
        product_id: compare_like_for_like_offers(
            [offer for offer in offers if offer.get("catalog_product_id") == product_id],
            max_age_seconds=_offer_comparison_max_age_seconds(),
        )
        for product_id in by_product
    }
    withheld = [
        {"product_id": pid, "decision": reason.lower(), "reason_code": reason}
        for pid, reason in sorted(withheld_reasons.items())
    ]
    for product_id, score, usi_score, wardrobe_match, offer in ranked:
        decision = decisions.get(product_id)
        if decision is None or not decision.may_display or decision.verdict != "show":
            withheld.append({"product_id": product_id, "rank_score": score, "decision": decision.verdict if decision else "review"})
            continue
        displayable.append({
            "product": by_product[product_id],
            "offer": offer,
            "merchant_comparison": comparisons_by_product.get(product_id, {
                "status": "unavailable", "basis": None, "groups": [],
                "unavailable_reasons": ["NO_COMPARABLE_OFFERS"],
                "exclusions": ["shipping", "tax", "fulfilment", "local_transport", "foreign_exchange"],
                "landed_cost_available": False,
            }),
            "rank_score": score,
            "rank_score_semantics": "weighted explicit-USI match plus bounded exact wardrobe-attribute overlap; not probability",
            "usi_rank_score": usi_score,
            "wardrobe_compatibility": {
                "matched_owned_item_ids": wardrobe_match["owned_item_ids"],
                "matched_attributes": wardrobe_match["matched_attributes"],
            },
            "decision": decision.model_dump(),
        })
    return {
        "request_id": decision_response.request_id,
        "ranked_candidate_count": len(ranked),
        "displayable_products": displayable,
        "withheld_candidate_ids": withheld,
        "display_authority": "CaTaCaCi/CAL",
        "display_rule": "Only candidates with CAL SHOW are returned with product and offer details.",
        "eepl_context_evidence": context_evidence,
        "wardrobe_context": {
            "used": payload.use_wardrobe_context,
            "active_item_count": len(wardrobe_items),
            "excluded_owned_product_count": sum(1 for reason in withheld_reasons.values() if reason == "ALREADY_IN_WARDROBE"),
        },
    }


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
        profile = (_load_verified_usi_profile(verified_subject, allow_without_consent=True)
                   if payload.use_wardrobe_context else _load_verified_usi_profile(verified_subject))
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
            _load_safety_signal(product, user_id=payload.user_id, request_id=request_id),
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
        estimate = _load_fci_estimate(payload.user_id, product_id, request_id, product)
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

        display_authorized = verdict == "show" and arbitration.may_display
        candidates.append(CandidateDecisionOutput(
            product_id=product_id,
            sku=str(product["sku"]) if display_authorized else None,
            name=str(product["name"]) if display_authorized else None,
            category=str(product["category"]) if display_authorized else None,
            brand=product.get("brand") if display_authorized else None,
            price_minor=int(product["price_minor"]) if display_authorized else None,
            currency=str(product["currency"]) if display_authorized else None,
            image_urls=(
                product.get("image_urls")
                if display_authorized and isinstance(product.get("image_urls"), list)
                else []
            ),
            catalog_version=int(product["catalog_version"]),
            verdict=verdict,
            may_display=display_authorized,
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

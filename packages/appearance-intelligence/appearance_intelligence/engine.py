"""NPL- and CAL-governed specialist candidate evaluation."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Mapping, Sequence
from catacaci import ArbitrationRequest, DecisionSignal, SignalKind, SignalState, arbitrate
from npl import NegativePreference, evaluate as evaluate_npl
from .contracts import AppearanceContext, CandidateEvaluation, CatalogProduct, CatalogSnapshot, EvaluationStatus, SpecialistId, SpecialistResult, normalize_category, normalize_text
from .registry import describe_specialist

POLICY_VERSION = "appearance-display-v1"
CONTRACT_VERSION = "1.0.0"
_DEFAULT_CATALOG_MAX_AGE_SECONDS = 120
_PROVIDER_SIGNAL_KINDS = frozenset({SignalKind.SAFETY, SignalKind.LEGAL_ELIGIBILITY, SignalKind.FIT_CONFIDENCE})

def _signal(signal_id: str, kind: SignalKind, state: SignalState, reason_code: str, explanation: str, *, required: bool = True, confidence: float | None = None, source_version: str = CONTRACT_VERSION) -> DecisionSignal:
    return DecisionSignal(signal_id=signal_id, kind=kind, state=state, reason_code=reason_code, explanation=explanation, required=required, confidence=confidence, source_version=source_version)

def _values(value: object) -> set[str]:
    raw = value if isinstance(value, (list, tuple, set)) else [value]
    return {normalize_text(str(item)) for item in raw if isinstance(item, (str, int, float, bool)) and str(item).strip()}

def _attribute_map(product: CatalogProduct) -> dict[str, object]:
    return {normalize_category(str(k)): v for k, v in product.attributes.items()}

def _attribute_constraint_state(product: CatalogProduct, constraints: Mapping[str, str]) -> tuple[SignalState, str, str]:
    if not constraints:
        return SignalState.PASS, "NO_DECLARED_ATTRIBUTE_CONSTRAINT", "No attribute constraint was declared."
    attributes = _attribute_map(product)
    unknown, mismatch = [], []
    for key, expected in constraints.items():
        key_norm = normalize_category(key)
        if key_norm not in attributes:
            unknown.append(key)
        elif normalize_text(expected) not in _values(attributes[key_norm]):
            mismatch.append(key)
    if mismatch:
        return SignalState.BLOCK, "DECLARED_ATTRIBUTE_CONSTRAINT_MISMATCH", "The product conflicts with declared attribute constraints: " + ", ".join(sorted(mismatch))
    if unknown:
        return SignalState.UNKNOWN, "DECLARED_ATTRIBUTE_EVIDENCE_MISSING", "The catalog lacks evidence for declared attributes: " + ", ".join(sorted(unknown))
    return SignalState.PASS, "DECLARED_ATTRIBUTE_CONSTRAINTS_MATCH", "Catalog attributes match all declared constraints."

def _cultural_state(product: CatalogProduct, requirements: tuple[str, ...]) -> tuple[SignalState, str, str]:
    if not requirements:
        return SignalState.PASS, "NO_CULTURAL_REQUIREMENT_DECLARED", "No cultural requirement was declared."
    attributes = _attribute_map(product)
    if "cultural_tags" not in attributes:
        return SignalState.UNKNOWN, "CULTURAL_EVIDENCE_MISSING", "No catalog-declared cultural tags are available for the user's explicit requirement."
    if not {normalize_text(v) for v in requirements}.issubset(_values(attributes["cultural_tags"])):
        return SignalState.BLOCK, "DECLARED_CULTURAL_REQUIREMENT_MISMATCH", "Catalog tags do not satisfy the user's explicit cultural requirement."
    return SignalState.PASS, "DECLARED_CULTURAL_REQUIREMENT_MATCH", "Catalog tags satisfy the explicit user-declared requirement."

def _validated_provider_signals(signals: Sequence[DecisionSignal]) -> tuple[DecisionSignal, ...]:
    if not isinstance(signals, (tuple, list)):
        raise ValueError("trusted provider signals must be a tuple or list")
    result, seen_ids = [], set()
    for signal in signals:
        if not isinstance(signal, DecisionSignal):
            raise ValueError("trusted evidence must use the canonical DecisionSignal contract")
        if signal.kind not in _PROVIDER_SIGNAL_KINDS:
            raise ValueError("providers may supply only safety, legal-eligibility, and fit-confidence signals")
        if signal.source_version == "unspecified":
            raise ValueError("trusted provider signals must declare a source version")
        if signal.signal_id in seen_ids:
            raise ValueError("provider signal IDs must be unique")
        seen_ids.add(signal.signal_id)
        result.append(signal)
    return tuple(result)

def evaluate_candidate(
    context: AppearanceContext,
    product: CatalogProduct,
    negative_preferences: Sequence[NegativePreference] = (),
    trusted_signals: Sequence[DecisionSignal] = (),
    *,
    require_fit_confidence: bool = True,
    identity_override: DecisionSignal | None = None,
) -> CandidateEvaluation:
    """Evaluate one canonical product. Only CAL SHOW permits display.

    Trusted evidence and NPL preferences are server-side inputs; they must never
    be accepted as authoritative values from browser request bodies.
    """
    if not isinstance(context, AppearanceContext) or not isinstance(product, CatalogProduct):
        raise ValueError("context and product must use canonical appearance contracts")
    if not isinstance(negative_preferences, (tuple, list)) or any(not isinstance(p, NegativePreference) for p in negative_preferences):
        raise ValueError("negative_preferences must contain canonical NPL objects")
    provider_signals = _validated_provider_signals(trusted_signals)
    if identity_override is not None:
        if not isinstance(identity_override, DecisionSignal) or identity_override.kind is not SignalKind.IDENTITY_ALIGNMENT or identity_override.source_version == "unspecified":
            raise ValueError("identity_override must be a versioned identity-alignment signal")

    npl = evaluate_npl(context.user_id, product.product_id, product.npl_attributes(), tuple(negative_preferences))
    signals: list[DecisionSignal] = list(provider_signals)
    for kind, prefix, explanation in (
        (SignalKind.SAFETY, "safety", "No trusted safety/claims gate evidence was provided."),
        (SignalKind.LEGAL_ELIGIBILITY, "legal", "No trusted legal/eligibility gate evidence was provided."),
    ):
        if not any(s.kind is kind for s in signals):
            signals.append(_signal(f"{prefix}:{product.product_id}", kind, SignalState.UNKNOWN, prefix.upper() + "_EVIDENCE_MISSING", explanation, source_version="appearance-intelligence:missing-evidence-v1"))

    signals.append(_signal(
        f"npl:{product.product_id}", SignalKind.NPL_HARD_NEGATIVE,
        SignalState.BLOCK if npl.blocked else SignalState.PASS,
        "NPL_HARD_NEGATIVE" if npl.blocked else "NPL_NO_HARD_VETO",
        "Canonical NPL matched an active hard exclusion." if npl.blocked else "Canonical NPL found no active hard exclusion.",
        source_version="npl:" + npl.contract_version,
    ))

    hard_state, hard_code, hard_explanation = _attribute_constraint_state(product, context.hard_constraints)
    signals.append(_signal(f"hard-constraints:{product.product_id}", SignalKind.USER_HARD_CONSTRAINT, hard_state, hard_code, hard_explanation))

    culture_state, culture_code, culture_explanation = _cultural_state(product, context.cultural_requirements)
    signals.append(_signal(f"cultural:{product.product_id}", SignalKind.CULTURAL_REQUIREMENT, culture_state, culture_code, culture_explanation))

    if context.currency is None:
        context_state, context_code, context_explanation = SignalState.PASS, "NO_PRICE_CONSTRAINT_DECLARED", "No budget/currency constraint was declared."
    elif product.currency != context.currency:
        context_state, context_code, context_explanation = SignalState.BLOCK, "CURRENCY_MISMATCH", "Product currency differs from the user's declared currency."
    elif context.budget_minor is not None and product.price_minor > context.budget_minor:
        context_state, context_code, context_explanation = SignalState.BLOCK, "BUDGET_EXCEEDED", "Product price exceeds the declared budget."
    else:
        context_state, context_code, context_explanation = SignalState.PASS, "CONTEXT_CONSTRAINTS_MATCH", "Product currency and declared budget constraints match."
    signals.append(_signal(f"context:{product.product_id}", SignalKind.CONTEXT_ELIGIBILITY, context_state, context_code, context_explanation))

    if identity_override is not None:
        signals.append(identity_override)
    else:
        identity_state, identity_code, identity_explanation = _attribute_constraint_state(product, context.preferred_attributes)
        signals.append(_signal(f"identity:{product.product_id}", SignalKind.IDENTITY_ALIGNMENT, identity_state, identity_code, identity_explanation))

    arbitration = arbitrate(ArbitrationRequest(
        request_id=context.request_id,
        candidate_id=product.product_id,
        signals=tuple(signals),
        policy_version=POLICY_VERSION,
        require_fit_confidence=require_fit_confidence,
    ))
    return CandidateEvaluation(product=product, npl_decision=npl, arbitration=arbitration)

def run_specialist(
    context: AppearanceContext,
    specialist: SpecialistId | str,
    snapshot: CatalogSnapshot,
    negative_preferences: Sequence[NegativePreference] = (),
    trusted_signals_by_product: Mapping[str, Sequence[DecisionSignal]] | None = None,
    *,
    now: datetime | None = None,
    max_catalog_age_seconds: int = _DEFAULT_CATALOG_MAX_AGE_SECONDS,
) -> SpecialistResult:
    """Evaluate catalog candidates without ranking or claims of model inference."""
    descriptor = describe_specialist(specialist)
    if descriptor.specialist is SpecialistId.SKIN:
        return SpecialistResult(descriptor.specialist, EvaluationStatus.PROVIDER_UNAVAILABLE, (), ("DermalSight's API/adapter exists, but its validated inference provider is not configured; no skin analysis was fabricated.",))
    current = now or datetime.now(timezone.utc)
    if not snapshot.is_fresh(current, max_catalog_age_seconds):
        return SpecialistResult(descriptor.specialist, EvaluationStatus.NEEDS_REVIEW, (), ("Catalog snapshot is incomplete or stale; no candidates may be displayed.",))
    if not descriptor.catalog_matching_available:
        return SpecialistResult(descriptor.specialist, EvaluationStatus.PROVIDER_UNAVAILABLE, (), ("No executable provider is registered for this specialist.",))
    matches = [p for p in snapshot.products if p.normalized_category in descriptor.catalog_categories]
    if not matches:
        return SpecialistResult(descriptor.specialist, EvaluationStatus.NO_CATALOG_CANDIDATES, (), ("No active catalog products matched the specialist's declared category aliases.",))
    evidence = trusted_signals_by_product or {}
    results = tuple(evaluate_candidate(
        context, p, tuple(negative_preferences), tuple(evidence.get(p.product_id, ())),
        require_fit_confidence=descriptor.requires_fit_confidence,
    ) for p in sorted(matches, key=lambda item: item.product_id))
    notices = (descriptor.description, "Candidates are catalog records, not image analysis or a guarantee of personal suitability.") + descriptor.limits
    return SpecialistResult(descriptor.specialist, EvaluationStatus.COMPLETED, results, notices)

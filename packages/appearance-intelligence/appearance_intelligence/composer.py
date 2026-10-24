"""Deterministic Look + Makeup composition with bundle-level CAL arbitration."""
from __future__ import annotations
from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import islice, product as cartesian_product
from typing import Mapping, Sequence
from catacaci import DecisionSignal, SignalKind, SignalState
from npl import NegativePreference
from .contracts import AppearanceContext, CandidateEvaluation, CatalogProduct, CatalogSnapshot, EvaluationStatus, SpecialistId, SpecialistResult
from .engine import _signal, evaluate_candidate, run_specialist

@dataclass(frozen=True)
class LookOption:
    product_ids: tuple[str, ...]
    total_price_minor: int
    currency: str
    decision: CandidateEvaluation
    @property
    def may_display(self) -> bool:
        return self.decision.may_display

@dataclass(frozen=True)
class LookCompositionResult:
    status: EvaluationStatus
    components: Mapping[SpecialistId, SpecialistResult]
    options: tuple[LookOption, ...]
    evaluated_bundles: tuple[CandidateEvaluation, ...]
    notices: tuple[str, ...]

def _bundle_product(products: tuple[CatalogProduct, ...]) -> CatalogProduct:
    ids = tuple(item.product_id for item in products)
    digest = sha256("|".join(ids).encode("utf-8")).hexdigest()[:24]
    tags: set[str] = set()
    combined: dict[str, list[str]] = {}
    groups: list[str] = []
    for item in products:
        for key, raw in item.attributes.items():
            values = raw if isinstance(raw, (list, tuple, set)) else [raw]
            for value in values:
                if isinstance(value, (str, int, float, bool)) and str(value).strip():
                    value_text = str(value).strip()
                    combined.setdefault(str(key), []).append(value_text)
                    tags.add(value_text.casefold())
                    tags.add(f"{str(key).casefold()}:{value_text.casefold()}")
        tags.add(item.normalized_category)
        tags.add(item.product_id.casefold())
        group = item.attributes.get("look_compatibility_group")
        if isinstance(group, str) and group.strip():
            groups.append(group.strip().casefold())
    attributes: dict[str, object] = {
        "component_product_ids": list(ids),
        "component_attributes": sorted(tags),
    }
    for key, values in combined.items():
        attributes[key] = sorted(set(values), key=str.casefold)
    if len(groups) == len(products) and len(set(groups)) == 1:
        attributes["look_compatibility_group"] = groups[0]
    elif groups:
        attributes["look_compatibility_group"] = sorted(set(groups))
    return CatalogProduct(
        product_id="look-" + digest, sku="LOOK-" + digest.upper(),
        name="Composed look", category="look",
        price_minor=sum(item.price_minor for item in products),
        currency=products[0].currency, attributes=attributes, status="active",
        catalog_version=1, description="Deterministic bundle from canonical catalog IDs.",
    )

def _identity_compatibility(products: tuple[CatalogProduct, ...]) -> DecisionSignal:
    raw = [p.attributes.get("look_compatibility_group") for p in products]
    groups = [v.strip().casefold() if isinstance(v, str) and v.strip() else None for v in raw]
    if all(v is not None for v in groups) and len(set(groups)) == 1:
        return _signal("look:compatibility-group", SignalKind.IDENTITY_ALIGNMENT, SignalState.PASS, "LOOK_COMPATIBILITY_GROUP_MATCH", "Every component carries the same catalog-declared look_compatibility_group.", source_version="catalog-declared-look-group-v1")
    if any(v is not None for v in groups):
        return _signal("look:compatibility-group", SignalKind.IDENTITY_ALIGNMENT, SignalState.BLOCK, "LOOK_COMPATIBILITY_GROUP_CONFLICT", "Catalog compatibility groups are missing or conflict; bundle needs review.", source_version="catalog-declared-look-group-v1")
    return _signal("look:compatibility-group", SignalKind.IDENTITY_ALIGNMENT, SignalState.UNKNOWN, "LOOK_COMPATIBILITY_EVIDENCE_MISSING", "No explicit catalog compatibility group is available for this combination.", source_version="catalog-declared-look-group-v1")

def build_look(
    context: AppearanceContext,
    snapshot: CatalogSnapshot,
    negative_preferences: Sequence[NegativePreference] = (),
    trusted_signals_by_product: Mapping[str, Sequence[DecisionSignal]] | None = None,
    *,
    bundle_signals: Sequence[DecisionSignal] = (),
    components: tuple[SpecialistId, ...] = (SpecialistId.LOOK, SpecialistId.MAKEUP),
    now=None,
    max_candidates_per_component: int = 3,
    max_options: int = 12,
) -> LookCompositionResult:
    """Build bounded combinations; only component-and-bundle CAL SHOW become options."""
    if not isinstance(components, tuple) or len(components) < 2:
        raise ValueError("at least two component specialist domains are required")
    if len(components) != len(set(components)):
        raise ValueError("component specialist domains must be unique")
    if any(component is SpecialistId.SKIN for component in components):
        raise ValueError("skin analysis cannot be a catalog component; use the separate Skincare specialist")
    if isinstance(max_candidates_per_component, bool) or not isinstance(max_candidates_per_component, int) or max_candidates_per_component < 1:
        raise ValueError("max_candidates_per_component must be a positive integer")
    if isinstance(max_options, bool) or not isinstance(max_options, int) or max_options < 1:
        raise ValueError("max_options must be a positive integer")

    evidence = trusted_signals_by_product or {}
    component_results = {
        component: run_specialist(context, component, snapshot, negative_preferences, evidence, now=now)
        for component in components
    }
    shown = {
        component: tuple(c for c in result.candidates if c.may_display)[:max_candidates_per_component]
        for component, result in component_results.items()
    }
    if any(not candidates for candidates in shown.values()):
        messages = tuple(f"{key.value}: no CAL-SHOW product candidates are available." for key, value in shown.items() if not value)
        return LookCompositionResult(EvaluationStatus.NEEDS_REVIEW, component_results, (), (), messages)

    candidate_sets = [tuple(c.product for c in shown[component]) for component in components]
    bundles: list[CandidateEvaluation] = []
    options: list[LookOption] = []
    inspected = 0
    for raw in islice(cartesian_product(*candidate_sets), max_options):
        combo = tuple(raw)
        if len({item.currency for item in combo}) != 1:
            # Never sum different currency denominations or invent an exchange rate.
            continue
        bundle = _bundle_product(combo)
        identity = _identity_compatibility(combo)
        bundle_context = replace(context, hard_constraints={}, preferred_attributes={})
        evaluation = evaluate_candidate(
            bundle_context, bundle, tuple(negative_preferences), tuple(bundle_signals),
            require_fit_confidence=True, identity_override=identity,
        )
        bundles.append(evaluation)
        inspected += 1
        if evaluation.may_display:
            options.append(LookOption(tuple(item.product_id for item in combo), bundle.price_minor, bundle.currency, evaluation))

    status = EvaluationStatus.COMPLETED if options else EvaluationStatus.NEEDS_REVIEW
    notices = (
        "Only component-and-bundle CAL SHOW results become displayable options.",
        "A shared catalog-declared look_compatibility_group and bundle-level fit/safety/legal evidence are required.",
        "No price conversion, model-derived ranking, virtual try-on, or physical-fit claim is performed.",
    )
    if inspected == 0:
        notices += ("No same-currency combination was available.",)
    return LookCompositionResult(status, component_results, tuple(options), tuple(bundles), notices)

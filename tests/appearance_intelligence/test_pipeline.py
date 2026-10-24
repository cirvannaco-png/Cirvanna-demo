from __future__ import annotations
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from catacaci import ArbitrationRequest, DecisionSignal, DecisionVerdict, SignalKind, SignalState, arbitrate
from npl import NegativePreference, PreferenceSource, TargetType
from appearance_intelligence import AppearanceContext, CatalogProduct, CatalogSnapshot, EvaluationStatus, SpecialistId, SPECIALISTS, build_look, run_specialist
from catalog_client import CatalogClient, CatalogUnavailable

def signal(signal_id: str, kind: SignalKind, state: SignalState = SignalState.PASS, *, confidence: float | None = None) -> DecisionSignal:
    return DecisionSignal(signal_id=signal_id, kind=kind, state=state, reason_code="TEST_" + signal_id.upper().replace(":", "_").replace("-", "_"), explanation="Explicit test evidence.", confidence=confidence, source_version="test-fixture-v1")

def product_record(product_id: str, category: str, *, price_minor: int = 1500, currency: str = "KES", attributes: dict | None = None) -> dict:
    return {"product_id": product_id, "sku": "SKU-" + product_id.upper(), "name": product_id.replace("-", " ").title(), "category": category, "price_minor": price_minor, "currency": currency, "attributes": attributes or {}, "image_urls": [], "status": "active", "catalog_version": 1, "brand": "Catalog Brand", "description": "Canonical catalog fixture."}

def catalog_product(*args, **kwargs) -> CatalogProduct:
    return CatalogProduct.from_mapping(product_record(*args, **kwargs))

def snapshot(*products: CatalogProduct, fetched_at: datetime | None = None, complete: bool = True) -> CatalogSnapshot:
    return CatalogSnapshot(tuple(products), fetched_at or datetime.now(timezone.utc), complete)

def product_gates(product_id: str, *, include_fit: bool = False) -> tuple[DecisionSignal, ...]:
    result = [signal("safety:" + product_id, SignalKind.SAFETY), signal("legal:" + product_id, SignalKind.LEGAL_ELIGIBILITY)]
    if include_fit:
        result.append(signal("fit:" + product_id, SignalKind.FIT_CONFIDENCE, confidence=0.94))
    return tuple(result)

def bundle_gates() -> tuple[DecisionSignal, ...]:
    return (signal("bundle:safety", SignalKind.SAFETY), signal("bundle:legal", SignalKind.LEGAL_ELIGIBILITY), signal("bundle:fit", SignalKind.FIT_CONFIDENCE, confidence=0.92))

def test_all_seven_specialists_are_registered_and_skincare_is_separate_from_skin():
    assert set(SPECIALISTS) == {SpecialistId.HAIR, SpecialistId.FACE, SpecialistId.SKIN, SpecialistId.LOOK, SpecialistId.FOOTWEAR, SpecialistId.MAKEUP, SpecialistId.SKINCARE}
    assert not SPECIALISTS[SpecialistId.SKIN].catalog_matching_available
    assert SPECIALISTS[SpecialistId.SKINCARE].catalog_matching_available

def test_makeup_candidate_can_show_only_with_trusted_required_gates():
    context = AppearanceContext("req-1", "user-1", "KES", 2000)
    item = catalog_product("makeup-1", "makeup", attributes={"finish": "matte", "shade": "rose"})
    result = run_specialist(context, SpecialistId.MAKEUP, snapshot(item), (), {item.product_id: product_gates(item.product_id)})
    assert result.status is EvaluationStatus.COMPLETED
    assert len(result.candidates) == 1
    assert result.candidates[0].arbitration.verdict is DecisionVerdict.SHOW
    assert result.candidates[0].may_display

def test_missing_safety_or_legal_evidence_fails_closed_to_review():
    context = AppearanceContext("req-2", "user-1", "KES", 2000)
    item = catalog_product("makeup-2", "makeup", attributes={"finish": "matte"})
    candidate = run_specialist(context, SpecialistId.MAKEUP, snapshot(item)).candidates[0]
    assert candidate.arbitration.verdict is DecisionVerdict.REVIEW
    assert not candidate.may_display
    assert {"SAFETY_EVIDENCE_MISSING", "LEGAL_EVIDENCE_MISSING"}.issubset(set(candidate.reason_codes))

def test_npl_hard_negative_blocks_before_missing_gates():
    context = AppearanceContext("req-3", "user-1")
    item = catalog_product("red-lipstick", "makeup", attributes={"color": "red"})
    negative = NegativePreference("avoid-red", "user-1", TargetType.ATTRIBUTE, "red", PreferenceSource.USER_DECLARED)
    candidate = run_specialist(context, SpecialistId.MAKEUP, snapshot(item), (negative,)).candidates[0]
    assert candidate.npl_decision.blocked
    assert candidate.arbitration.verdict is DecisionVerdict.BLOCK
    assert not candidate.may_display

def test_footwear_requires_fit_evidence_but_makeup_does_not():
    context = AppearanceContext("req-4", "user-1", "KES", 4000)
    shoes = catalog_product("shoes-1", "footwear", attributes={"style": "loafers"})
    missing = run_specialist(context, SpecialistId.FOOTWEAR, snapshot(shoes), (), {shoes.product_id: product_gates(shoes.product_id)})
    assert missing.candidates[0].arbitration.verdict is DecisionVerdict.REVIEW
    present = run_specialist(context, SpecialistId.FOOTWEAR, snapshot(shoes), (), {shoes.product_id: product_gates(shoes.product_id, include_fit=True)})
    assert present.candidates[0].arbitration.verdict is DecisionVerdict.SHOW

def test_skin_provider_is_unavailable_but_skincare_catalog_matching_exists():
    context = AppearanceContext("req-5", "user-1", "KES", 5000)
    cleanser = catalog_product("cleanser-1", "skincare", attributes={"skin_type": "dry"})
    skincare = run_specialist(context, SpecialistId.SKINCARE, snapshot(cleanser), (), {cleanser.product_id: product_gates(cleanser.product_id)})
    skin = run_specialist(context, SpecialistId.SKIN, snapshot(cleanser))
    assert skincare.candidates[0].arbitration.verdict is DecisionVerdict.SHOW
    assert skin.status is EvaluationStatus.PROVIDER_UNAVAILABLE
    assert not skin.candidates

def test_hard_constraint_mismatch_blocks_and_missing_attribute_reviews():
    context = AppearanceContext("req-6", "user-1", "KES", 2000, hard_constraints={"material": "cotton"})
    mismatch = catalog_product("top-1", "apparel", attributes={"material": "polyester"})
    blocked = run_specialist(context, SpecialistId.LOOK, snapshot(mismatch), (), {mismatch.product_id: product_gates(mismatch.product_id, include_fit=True)}).candidates[0]
    assert blocked.arbitration.verdict is DecisionVerdict.BLOCK
    missing = catalog_product("top-2", "apparel", attributes={"color": "navy"})
    review = run_specialist(context, SpecialistId.LOOK, snapshot(missing), (), {missing.product_id: product_gates(missing.product_id, include_fit=True)}).candidates[0]
    assert review.arbitration.verdict is DecisionVerdict.REVIEW

def test_look_plus_makeup_composes_only_after_component_and_bundle_show():
    context = AppearanceContext("req-7", "user-1", "KES", 7000)
    apparel = catalog_product("look-top", "apparel", price_minor=4000, attributes={"look_compatibility_group": "ceremony-neutral", "color": "navy"})
    makeup = catalog_product("makeup-3", "makeup", price_minor=1800, attributes={"look_compatibility_group": "ceremony-neutral", "shade": "rose"})
    evidence = {apparel.product_id: product_gates(apparel.product_id, include_fit=True), makeup.product_id: product_gates(makeup.product_id)}
    result = build_look(context, snapshot(apparel, makeup), (), evidence, bundle_signals=bundle_gates())
    assert result.status is EvaluationStatus.COMPLETED
    assert len(result.options) == 1
    assert result.options[0].may_display
    assert result.options[0].total_price_minor == 5800
    assert result.options[0].product_ids == ("look-top", "makeup-3")

def test_bundle_without_compatibility_or_bundle_evidence_never_shows():
    context = AppearanceContext("req-8", "user-1", "KES", 7000)
    apparel = catalog_product("look-top-2", "apparel", price_minor=4000, attributes={"color": "navy"})
    makeup = catalog_product("makeup-4", "makeup", price_minor=1800, attributes={"shade": "rose"})
    evidence = {apparel.product_id: product_gates(apparel.product_id, include_fit=True), makeup.product_id: product_gates(makeup.product_id)}
    result = build_look(context, snapshot(apparel, makeup), (), evidence)
    assert result.options == ()
    assert len(result.evaluated_bundles) == 1
    assert result.evaluated_bundles[0].arbitration.verdict is DecisionVerdict.REVIEW

def test_incomplete_or_stale_catalog_returns_no_candidates():
    context = AppearanceContext("req-9", "user-1")
    item = catalog_product("makeup-5", "makeup")
    stale = snapshot(item, fetched_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    result = run_specialist(context, SpecialistId.MAKEUP, stale)
    assert result.status is EvaluationStatus.NEEDS_REVIEW
    assert result.candidates == ()

def test_non_fit_cal_profile_does_not_fabricate_fit_confidence_and_default_remains_strict():
    required = (SignalKind.SAFETY, SignalKind.LEGAL_ELIGIBILITY, SignalKind.USER_HARD_CONSTRAINT, SignalKind.NPL_HARD_NEGATIVE, SignalKind.CULTURAL_REQUIREMENT, SignalKind.CONTEXT_ELIGIBILITY, SignalKind.IDENTITY_ALIGNMENT)
    signals = tuple(signal("pass:" + kind.value, kind) for kind in required)
    product_only = arbitrate(ArbitrationRequest(request_id="req-10", candidate_id="cosmetic-1", signals=signals, required_kinds=required, require_fit_confidence=False))
    default_fit_sensitive = arbitrate(ArbitrationRequest(request_id="req-10", candidate_id="shoe-1", signals=signals))
    assert product_only.verdict is DecisionVerdict.SHOW
    assert default_fit_sensitive.verdict is DecisionVerdict.REVIEW

def test_catalog_client_reads_a_valid_complete_page():
    record = product_record("api-makeup", "makeup", attributes={"finish": "matte"})
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/products"
        assert request.headers.get("authorization") == "Bearer " + "R" * 40
        assert request.url.params["offset"] == "0" and request.url.params["limit"] == "100"
        return httpx.Response(200, json={"items": [record], "total": 1, "offset": 0, "limit": 100})
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = CatalogClient("http://127.0.0.1:8123", "R" * 40, client=client).fetch_active_catalog()
    assert result.complete and len(result.products) == 1 and result.products[0].product_id == "api-makeup"

def test_catalog_client_rejects_total_changing_mid_pagination():
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        total = 101 if offset == 0 else 102
        items = [product_record(f"p-{i}", "makeup") for i in range(100)] if offset == 0 else [product_record("p-100", "makeup"), product_record("p-101", "makeup")]
        return httpx.Response(200, json={"items": items, "total": total, "offset": offset, "limit": 100})
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        adapter = CatalogClient("http://127.0.0.1:8123", "R" * 40, client=client)
        with pytest.raises(CatalogUnavailable, match="total changed"):
            adapter.fetch_active_catalog()

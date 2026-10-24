"""Unittest discovery tests for the governed appearance-specialist slice."""
from __future__ import annotations
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in (
    "packages/appearance-intelligence",
    "packages/identity-intelligence",
    "packages/preferences",
):
    sys.path.insert(0, str(ROOT / relative))

from catacaci import ArbitrationRequest, DecisionSignal, DecisionVerdict, SignalKind, SignalState, arbitrate
from npl import NegativePreference, PreferenceSource, TargetType
from appearance_intelligence import (
    AppearanceContext, CatalogProduct, CatalogSnapshot, EvaluationStatus,
    SpecialistId, SPECIALISTS, build_look, run_specialist,
)


def gate(signal_id, kind, confidence=None):
    return DecisionSignal(
        signal_id=signal_id, kind=kind, state=SignalState.PASS,
        reason_code="TEST_PASS", explanation="Explicit trusted test evidence.",
        confidence=confidence, source_version="test-v1",
    )


def product(product_id, category, price=1500, attributes=None):
    return CatalogProduct.from_mapping({
        "product_id": product_id, "sku": "SKU-" + product_id.upper(),
        "name": product_id.title(), "category": category,
        "price_minor": price, "currency": "KES",
        "attributes": attributes or {}, "status": "active", "catalog_version": 1,
    })


def snap(*items, fetched_at=None, complete=True):
    return CatalogSnapshot(tuple(items), fetched_at or datetime.now(timezone.utc), complete)


def product_gates(product_id, with_fit=False):
    rows = [gate("safe:" + product_id, SignalKind.SAFETY), gate("legal:" + product_id, SignalKind.LEGAL_ELIGIBILITY)]
    if with_fit:
        rows.append(gate("fit:" + product_id, SignalKind.FIT_CONFIDENCE, 0.94))
    return tuple(rows)


class AppearanceSpecialistContractTests(unittest.TestCase):
    def test_all_seven_domains_registered_and_skin_is_not_skincare(self):
        self.assertEqual(set(SPECIALISTS), set(SpecialistId))
        self.assertFalse(SPECIALISTS[SpecialistId.SKIN].catalog_matching_available)
        self.assertTrue(SPECIALISTS[SpecialistId.SKINCARE].catalog_matching_available)

    def test_makeup_show_requires_trusted_safety_and_legal_gates(self):
        item = product("makeup-1", "makeup", attributes={"finish": "matte"})
        context = AppearanceContext("req-1", "user-1", "KES", 2000)
        result = run_specialist(context, SpecialistId.MAKEUP, snap(item), (), {item.product_id: product_gates(item.product_id)})
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.SHOW)

    def test_missing_safety_legal_evidence_is_review_not_show(self):
        item = product("makeup-2", "makeup")
        result = run_specialist(AppearanceContext("req-2", "user-1"), SpecialistId.MAKEUP, snap(item))
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.candidates[0].may_display)

    def test_npl_hard_negative_forces_cal_block(self):
        item = product("red-lipstick", "makeup", attributes={"color": "red"})
        negative = NegativePreference("avoid-red", "user-1", TargetType.ATTRIBUTE, "red", PreferenceSource.USER_DECLARED)
        result = run_specialist(AppearanceContext("req-3", "user-1"), SpecialistId.MAKEUP, snap(item), (negative,))
        self.assertTrue(result.candidates[0].npl_decision.blocked)
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.BLOCK)

    def test_footwear_fit_gate_remains_mandatory(self):
        item = product("shoe-1", "footwear")
        context = AppearanceContext("req-4", "user-1", "KES", 3000)
        no_fit = run_specialist(context, SpecialistId.FOOTWEAR, snap(item), (), {item.product_id: product_gates(item.product_id)})
        with_fit = run_specialist(context, SpecialistId.FOOTWEAR, snap(item), (), {item.product_id: product_gates(item.product_id, True)})
        self.assertEqual(no_fit.candidates[0].arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertEqual(with_fit.candidates[0].arbitration.verdict, DecisionVerdict.SHOW)

    def test_skincare_product_matching_runs_while_skin_provider_fails_closed(self):
        item = product("cleanser-1", "skincare", attributes={"skin_type": "dry"})
        context = AppearanceContext("req-5", "user-1", "KES", 5000)
        skincare = run_specialist(context, SpecialistId.SKINCARE, snap(item), (), {item.product_id: product_gates(item.product_id)})
        skin = run_specialist(context, SpecialistId.SKIN, snap(item))
        self.assertEqual(skincare.candidates[0].arbitration.verdict, DecisionVerdict.SHOW)
        self.assertEqual(skin.status, EvaluationStatus.PROVIDER_UNAVAILABLE)

    def test_declared_hard_constraint_mismatch_blocks_and_missing_evidence_reviews(self):
        context = AppearanceContext("req-6", "user-1", "KES", 3000, hard_constraints={"material": "cotton"})
        mismatch = product("top-1", "apparel", attributes={"material": "polyester"})
        blocked = run_specialist(context, SpecialistId.LOOK, snap(mismatch), (), {mismatch.product_id: product_gates(mismatch.product_id, True)})
        missing = product("top-2", "apparel", attributes={"color": "navy"})
        review = run_specialist(context, SpecialistId.LOOK, snap(missing), (), {missing.product_id: product_gates(missing.product_id, True)})
        self.assertEqual(blocked.candidates[0].arbitration.verdict, DecisionVerdict.BLOCK)
        self.assertEqual(review.candidates[0].arbitration.verdict, DecisionVerdict.REVIEW)

    def test_look_plus_makeup_only_emerges_after_component_and_bundle_show(self):
        context = AppearanceContext("req-7", "user-1", "KES", 7000)
        apparel = product("look-top", "apparel", 4000, {"look_compatibility_group": "ceremony-neutral", "color": "navy"})
        makeup = product("makeup-3", "makeup", 1800, {"look_compatibility_group": "ceremony-neutral", "shade": "rose"})
        evidence = {
            apparel.product_id: product_gates(apparel.product_id, True),
            makeup.product_id: product_gates(makeup.product_id),
        }
        bundle_evidence = (
            gate("bundle-safe", SignalKind.SAFETY),
            gate("bundle-legal", SignalKind.LEGAL_ELIGIBILITY),
            gate("bundle-fit", SignalKind.FIT_CONFIDENCE, 0.92),
        )
        result = build_look(context, snap(apparel, makeup), (), evidence, bundle_signals=bundle_evidence)
        self.assertEqual(result.status, EvaluationStatus.COMPLETED)
        self.assertEqual(len(result.options), 1)
        self.assertEqual(result.options[0].total_price_minor, 5800)
        self.assertTrue(result.options[0].may_display)

    def test_look_without_bundle_fit_or_compatibility_is_review(self):
        context = AppearanceContext("req-8", "user-1", "KES", 7000)
        apparel = product("top-3", "apparel", 4000, {"color": "navy"})
        makeup = product("makeup-4", "makeup", 1800, {"shade": "rose"})
        evidence = {
            apparel.product_id: product_gates(apparel.product_id, True),
            makeup.product_id: product_gates(makeup.product_id),
        }
        result = build_look(context, snap(apparel, makeup), (), evidence)
        self.assertEqual(result.options, ())
        self.assertEqual(result.evaluated_bundles[0].arbitration.verdict, DecisionVerdict.REVIEW)

    def test_stale_catalog_snapshot_is_not_used(self):
        item = product("makeup-5", "makeup")
        stale = snap(item, fetched_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        result = run_specialist(AppearanceContext("req-9", "user-1"), SpecialistId.MAKEUP, stale)
        self.assertEqual(result.status, EvaluationStatus.NEEDS_REVIEW)
        self.assertEqual(result.candidates, ())

    def test_cal_fit_confidence_is_optional_only_when_profile_explicitly_disables_it(self):
        required = (
            SignalKind.SAFETY, SignalKind.LEGAL_ELIGIBILITY, SignalKind.USER_HARD_CONSTRAINT,
            SignalKind.NPL_HARD_NEGATIVE, SignalKind.CULTURAL_REQUIREMENT,
            SignalKind.CONTEXT_ELIGIBILITY, SignalKind.IDENTITY_ALIGNMENT,
        )
        signals = tuple(gate("pass:" + kind.value, kind) for kind in required)
        cosmetic = arbitrate(ArbitrationRequest(
            request_id="req-10", candidate_id="cosmetic-1", signals=signals,
            required_kinds=required, require_fit_confidence=False,
        ))
        physical = arbitrate(ArbitrationRequest(request_id="req-10", candidate_id="shoe-1", signals=signals))
        self.assertEqual(cosmetic.verdict, DecisionVerdict.SHOW)
        self.assertEqual(physical.verdict, DecisionVerdict.REVIEW)


if __name__ == "__main__":
    unittest.main()

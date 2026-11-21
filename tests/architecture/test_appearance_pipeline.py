"""Small cross-package architecture smoke tests for appearance decision wiring.

Detailed catalog pagination and composer regressions live in
tests/appearance_intelligence/test_pipeline.py. Keep this file dependency-light
so the repository-wide unittest architecture job can run without pytest/httpx.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for relative in (
    "packages/appearance-intelligence",
    "packages/identity-intelligence",
    "packages/preferences",
):
    sys.path.insert(0, str(ROOT / relative))

from catacaci import DecisionSignal, DecisionVerdict, SignalKind, SignalState
from npl import NegativePreference, PreferenceSource, TargetType
from appearance_intelligence import (
    AppearanceContext,
    CatalogProduct,
    CatalogSnapshot,
    EvaluationStatus,
    SpecialistId,
    SPECIALISTS,
    run_specialist,
)


def product(product_id: str, category: str, attributes: dict | None = None) -> CatalogProduct:
    return CatalogProduct.from_mapping({
        "product_id": product_id,
        "sku": "SKU-" + product_id.upper(),
        "name": product_id.replace("-", " ").title(),
        "category": category,
        "price_minor": 1500,
        "currency": "KES",
        "attributes": attributes or {},
        "status": "active",
        "catalog_version": 1,
    })


def snapshot(*products: CatalogProduct) -> CatalogSnapshot:
    return CatalogSnapshot(tuple(products), datetime.now(timezone.utc), complete=True)


def trusted_gates(product_id: str, *, fit: bool = False) -> tuple[DecisionSignal, ...]:
    result = [
        DecisionSignal(
            signal_id="safety:" + product_id,
            kind=SignalKind.SAFETY,
            state=SignalState.PASS,
            reason_code="TEST_SAFETY_PASS",
            explanation="Explicit trusted test evidence.",
            source_version="architecture-test-v1",
        ),
        DecisionSignal(
            signal_id="legal:" + product_id,
            kind=SignalKind.LEGAL_ELIGIBILITY,
            state=SignalState.PASS,
            reason_code="TEST_LEGAL_PASS",
            explanation="Explicit trusted test evidence.",
            source_version="architecture-test-v1",
        ),
    ]
    if fit:
        result.append(DecisionSignal(
            signal_id="fit:" + product_id,
            kind=SignalKind.FIT_CONFIDENCE,
            state=SignalState.PASS,
            reason_code="TEST_FIT_PASS",
            explanation="Explicit calibrated fit fixture.",
            confidence=0.94,
            source_version="architecture-test-v1",
        ))
    return tuple(result)


class AppearanceArchitectureSmokeTests(unittest.TestCase):
    def test_seven_specialists_are_registered_and_skin_analysis_fails_closed(self):
        self.assertEqual(set(SPECIALISTS), set(SpecialistId))
        result = run_specialist(
            AppearanceContext("smoke-skin", "user-1"),
            SpecialistId.SKIN,
            snapshot(product("cleanser-1", "skincare")),
            (),
        )
        self.assertEqual(result.status, EvaluationStatus.PROVIDER_UNAVAILABLE)
        self.assertEqual(result.candidates, ())

    def test_missing_npl_state_never_authorizes_makeup_display(self):
        item = product("makeup-1", "makeup")
        result = run_specialist(
            AppearanceContext("smoke-npl", "user-1", "KES", 3000),
            SpecialistId.MAKEUP,
            snapshot(item),
            None,
            {item.product_id: trusted_gates(item.product_id)},
        )
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.candidates[0].may_display)
        self.assertIn("NPL_EVIDENCE_UNAVAILABLE", result.candidates[0].reason_codes)

    def test_explicit_npl_negative_blocks_candidate_despite_positive_provider_evidence(self):
        item = product("red-lipstick", "makeup", {"color": "red"})
        negative = NegativePreference(
            "avoid-red",
            "user-1",
            TargetType.ATTRIBUTE,
            "red",
            PreferenceSource.USER_DECLARED,
        )
        result = run_specialist(
            AppearanceContext("smoke-hard-negative", "user-1", "KES", 3000),
            SpecialistId.MAKEUP,
            snapshot(item),
            (negative,),
            {item.product_id: trusted_gates(item.product_id)},
        )
        self.assertTrue(result.candidates[0].npl_decision.blocked)
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.BLOCK)

    def test_look_stays_fit_strict_without_calibrated_fit_evidence(self):
        item = product("top-1", "apparel", {"look_compatibility_group": "formal-neutral"})
        result = run_specialist(
            AppearanceContext("smoke-fit", "user-1", "KES", 3000),
            SpecialistId.LOOK,
            snapshot(item),
            (),
            {item.product_id: trusted_gates(item.product_id)},
        )
        self.assertEqual(result.candidates[0].arbitration.verdict, DecisionVerdict.REVIEW)
        self.assertFalse(result.candidates[0].may_display)


if __name__ == "__main__":
    unittest.main()

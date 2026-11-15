from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from appearance_intelligence import (  # noqa: E402
    AppearanceComponent,
    ComponentOperation,
    EditAction,
    FidelityAssessment,
    FidelityGate,
    GateStatus,
    LookBase,
    LookBaseKind,
    LookComposition,
    OperationOrigin,
    RecommendationTrack,
    ReferenceKind,
)


class AppearanceIntelligenceContractTests(unittest.TestCase):
    def source_base(self):
        return LookBase(
            kind=LookBaseKind.SOURCE_PHOTO,
            source_asset_ids=("original-photo-001",),
        )

    def operation(self, **overrides):
        values = {
            "operation_id": "edit-001",
            "component": AppearanceComponent.HAIRSTYLE,
            "action": EditAction.REPLACE,
            "description": "Explore a textured crop with a tapered finish",
        }
        values.update(overrides)
        return ComponentOperation(**values)

    def composition(self, **overrides):
        values = {
            "look_id": "look-001",
            "subject_id": "subject-001",
            "version": 1,
            "base": self.source_base(),
            "operations": (self.operation(),),
        }
        values.update(overrides)
        return LookComposition(**values)

    def assessment(self, **overrides):
        core = {
            FidelityGate.IDENTITY_CONSISTENCY,
            FidelityGate.FACIAL_GEOMETRY_PRESERVATION,
            FidelityGate.SKIN_TONE_PRESERVATION,
            FidelityGate.UNAFFECTED_REGION_PRESERVATION,
            FidelityGate.LIGHTING_CONSISTENCY,
            FidelityGate.ANATOMICAL_CORRECTNESS,
            FidelityGate.PHOTOGRAPHIC_CREDIBILITY,
        }
        checks = tuple(
            (gate, GateStatus.PASS if gate in core else GateStatus.NOT_APPLICABLE)
            for gate in FidelityGate
        )
        values = {
            "assessment_id": "assessment-001",
            "look_id": "look-001",
            "look_version": 1,
            "output_asset_id": "private-render-001",
            "model_version": "renderer-v1@sha256:" + ("a" * 64),
            "checks": checks,
        }
        values.update(overrides)
        return FidelityAssessment(**values)

    def test_contract_covers_full_grooming_beauty_fashion_and_accessories(self):
        expected = {
            "hairstyle", "hair_colour", "hairline", "facial_hair",
            "eyebrows", "eyelashes", "lipstick", "makeup",
            "skincare_application", "skincare_product", "haircare_product",
            "garment", "footwear", "jewellery", "eyewear", "headwear",
            "hair_accessory", "bag", "accessory", "nail_art", "fragrance",
        }
        self.assertTrue(expected <= {item.value for item in AppearanceComponent})

    def test_one_look_can_combine_unlimited_edit_operations_without_fixed_style_cap(self):
        operations = tuple(
            self.operation(
                operation_id=f"edit-{index:03d}",
                component=list(AppearanceComponent)[index % len(AppearanceComponent)],
                action=EditAction.REPLACE,
                description=f"User-selected appearance variation {index}",
            )
            for index in range(1, 31)
        )
        look = self.composition(operations=operations)
        self.assertEqual(len(look.operations), 30)

    def test_original_source_lineage_is_required(self):
        with self.assertRaisesRegex(ValueError, "at least one original source asset"):
            LookBase(kind=LookBaseKind.SOURCE_PHOTO, source_asset_ids=())

    def test_twin_base_requires_twin_id_and_retains_source_assets(self):
        base = LookBase(
            kind=LookBaseKind.VIRTUAL_TWIN,
            source_asset_ids=("twin-source-001", "twin-source-002"),
            twin_id="twin-001",
        )
        self.assertEqual(base.twin_id, "twin-001")
        with self.assertRaisesRegex(ValueError, "requires twin_id"):
            LookBase(kind=LookBaseKind.VIRTUAL_TWIN, source_asset_ids=("source-001",))

    def test_previous_render_branch_keeps_original_source_lineage(self):
        base = LookBase(
            kind=LookBaseKind.PREVIOUS_RENDER,
            source_asset_ids=("original-photo-001",),
            parent_look_id="look-previous",
            parent_render_asset_id="render-previous",
        )
        self.assertEqual(base.source_asset_ids, ("original-photo-001",))
        with self.assertRaisesRegex(ValueError, "requires both parent_look_id"):
            LookBase(
                kind=LookBaseKind.PREVIOUS_RENDER,
                source_asset_ids=("original-photo-001",),
                parent_look_id="look-previous",
            )

    def test_arbitrary_photo_urls_are_not_accepted_as_asset_references(self):
        with self.assertRaisesRegex(ValueError, "opaque internal identifier"):
            LookBase(
                kind=LookBaseKind.SOURCE_PHOTO,
                source_asset_ids=("https://example.com/person.jpg",),
            )

    def test_user_can_explicitly_request_experimental_or_uncommon_styles(self):
        operation = self.operation(
            origin=OperationOrigin.ACCEPTED_RECOMMENDATION,
            recommendation_id="recommendation-001",
            recommendation_track=RecommendationTrack.EXPERIMENTAL,
            description="Asymmetric, high-volume sculptural hairstyle",
        )
        look = self.composition(operations=(operation,))
        self.assertEqual(look.operations[0].recommendation_track, RecommendationTrack.EXPERIMENTAL)

    def test_ai_recommendation_must_be_accepted_and_traceable(self):
        with self.assertRaisesRegex(ValueError, "require a recommendation_id"):
            self.operation(origin=OperationOrigin.ACCEPTED_RECOMMENDATION)

    def test_remove_operation_can_target_a_component_without_a_catalog_item(self):
        operation = self.operation(
            component=AppearanceComponent.FACIAL_HAIR,
            action=EditAction.REMOVE,
            description=None,
        )
        self.assertEqual(operation.action, EditAction.REMOVE)

    def test_catalog_and_wardrobe_references_are_explicitly_typed(self):
        operation = self.operation(
            reference_kind=ReferenceKind.WARDROBE_ITEM,
            reference_id="wardrobe-item-001",
            description=None,
        )
        self.assertEqual(operation.reference_kind, ReferenceKind.WARDROBE_ITEM)

    def test_duplicate_operation_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be unique"):
            self.composition(operations=(
                self.operation(operation_id="same-edit"),
                self.operation(operation_id="same-edit", component=AppearanceComponent.LIPSTICK),
            ))

    def test_identity_geometry_and_skin_tone_cannot_be_disabled(self):
        for field in ("preserve_identity", "preserve_facial_geometry", "preserve_underlying_skin_tone"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.composition(**{field: False})

    def test_unrequested_regions_cannot_be_modified_by_an_operation(self):
        with self.assertRaisesRegex(ValueError, "preserve every region"):
            self.operation(preserve_unrequested_regions=False)

    def test_complete_fidelity_report_is_releasable_only_after_all_applicable_gates_pass(self):
        result = self.assessment()
        self.assertTrue(result.releasable)
        self.assertEqual(result.disposition, "releasable")

    def test_uncertain_optional_gate_requires_review_and_withholds_output(self):
        result = self.assessment(checks=tuple(
            (gate, GateStatus.REVIEW_REQUIRED if gate is FidelityGate.HAIRLINE_INTEGRATION
             else (GateStatus.PASS if gate in {
                 FidelityGate.IDENTITY_CONSISTENCY,
                 FidelityGate.FACIAL_GEOMETRY_PRESERVATION,
                 FidelityGate.SKIN_TONE_PRESERVATION,
                 FidelityGate.UNAFFECTED_REGION_PRESERVATION,
                 FidelityGate.LIGHTING_CONSISTENCY,
                 FidelityGate.ANATOMICAL_CORRECTNESS,
                 FidelityGate.PHOTOGRAPHIC_CREDIBILITY,
             } else GateStatus.NOT_APPLICABLE))
            for gate in FidelityGate
        ))
        self.assertFalse(result.releasable)
        self.assertEqual(result.disposition, "review_required")

    def test_failed_core_gate_is_recordable_but_output_is_withheld(self):
        result = self.assessment(checks=tuple(
            (gate, GateStatus.FAIL if gate is FidelityGate.IDENTITY_CONSISTENCY
             else (GateStatus.PASS if gate in {
                 FidelityGate.FACIAL_GEOMETRY_PRESERVATION,
                 FidelityGate.SKIN_TONE_PRESERVATION,
                 FidelityGate.UNAFFECTED_REGION_PRESERVATION,
                 FidelityGate.LIGHTING_CONSISTENCY,
                 FidelityGate.ANATOMICAL_CORRECTNESS,
                 FidelityGate.PHOTOGRAPHIC_CREDIBILITY,
             } else GateStatus.NOT_APPLICABLE))
            for gate in FidelityGate
        ))
        self.assertFalse(result.releasable)
        self.assertEqual(result.disposition, "withheld")

    def test_every_fidelity_gate_must_be_reported(self):
        with self.assertRaisesRegex(ValueError, "every fidelity gate"):
            self.assessment(checks=())

    def test_renderer_revision_must_be_pinned(self):
        with self.assertRaisesRegex(ValueError, "SHA-256-pinned"):
            self.assessment(model_version="latest")


if __name__ == "__main__":
    unittest.main()

import pytest
from pydantic import ValidationError

from app.product_intelligence import ProductIntelligence, validate_product_intelligence_attributes


def evidence(**overrides):
    value = {
        "source_type": "manufacturer_declared",
        "reference": "manufacturer-ingredient-label-2026-11",
        "reviewed_at": "2026-11-10",
        "source_id": "SRC-MANUFACTURER-001",
        "evidence_grade": "E4",
        "scope": "finished_product",
    }
    value.update(overrides)
    return value


def test_structured_ingredients_keep_product_label_provenance():
    metadata = {
        "schema_version": "1.0",
        "ingredient_declarations": [
            {"inci_name": "Glycerin", "label_order": 2, "evidence": evidence()},
            {"inci_name": "Squalane", "label_order": 5, "evidence": evidence(reference="label-2")},
        ],
    }
    normalized = validate_product_intelligence_attributes({"product_intelligence": metadata})
    ingredients = normalized["product_intelligence"]["ingredient_declarations"]
    assert [item["inci_name"] for item in ingredients] == ["Glycerin", "Squalane"]
    assert ingredients[0]["evidence"]["source_id"] == "SRC-MANUFACTURER-001"


def test_structured_ingredient_requires_a_source_registry_reference():
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "ingredient_declarations": [{
                "inci_name": "Glycerin",
                "evidence": evidence(source_id=None),
            }],
        })


def test_catalog_does_not_allow_claim_approval_before_runtime_cil_gate():
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "claims": [{
                "claim_id": "CLAIM-HYDRATION-001",
                "claim_type": "finished_product_efficacy",
                "statement": "This finished product measurably improves hydration.",
                "evidence": evidence(evidence_grade="E4", source_type="manufacturer_declared"),
                "review_status": "approved",
                "limitations": "Manufacturer claims are not independent clinical efficacy evidence.",
            }],
        })


def test_catalog_claims_cannot_bypass_cil_with_an_ingredient_level_study():
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "claims": [{
                "claim_id": "CLAIM-HYDRATION-002",
                "claim_type": "finished_product_efficacy",
                "statement": "This finished product measurably improves hydration.",
                "evidence": evidence(
                    source_type="public_research", evidence_grade="E2", scope="ingredient",
                ),
                "review_status": "approved",
                "limitations": "Ingredient studies do not establish this finished formulation's efficacy.",
            }],
        })


def test_pending_marketing_claim_is_stored_but_not_promoted_to_approved():
    metadata = ProductIntelligence.model_validate({
        "schema_version": "1.0",
        "claims": [{
            "claim_id": "CLAIM-MARKETING-001",
            "claim_type": "finished_product_efficacy",
            "statement": "A marketing claim awaiting evidence review.",
            "evidence": evidence(source_id=None, evidence_grade="E6", scope="general"),
            "review_status": "pending_review",
            "limitations": "Marketing-only claims are not scientific or clinical substantiation.",
        }],
    })
    assert metadata.claims[0].review_status == "pending_review"


def test_duplicate_inci_labels_are_rejected_case_and_space_insensitively():
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "ingredient_declarations": [
                {"inci_name": "Glycerin", "evidence": evidence()},
                {"inci_name": " GLYCERIN ", "evidence": evidence(reference="label-2")},
            ],
        })



def garment_fit_evidence(**overrides):
    value = evidence(
        source_type="manufacturer_declared",
        reference="manufacturer-size-chart-2026-11",
        source_id="SRC-GARMENT-SIZE-001",
        evidence_grade="E4",
        scope="finished_product",
    )
    value.update(overrides)
    return value


def garment_size_spec(**overrides):
    value = {
        "variant_id": "123e4567-e89b-12d3-a456-426614174000",
        "size_label": "M",
        "category": "top",
        "pattern_dimensions_mm": {
            "chest_mm": 1000,
            "waist_mm": 780,
            "shoulder_width_mm": 460,
            "sleeve_length_mm": 610,
            "garment_length_mm": 700,
        },
        "stretch_ratio": 0.35,
        "fit_class": "regular",
        "fabric_weight": "medium",
        "structure": "semi_structured",
        "ease_allowance_mm": {"chest_mm": 20, "waist_mm": 20},
        "evidence": garment_fit_evidence(),
    }
    value.update(overrides)
    return value


def test_garment_fit_metadata_is_strict_evidence_backed_and_variant_bound():
    metadata = ProductIntelligence.model_validate({
        "schema_version": "1.0",
        "garment_fit": {"size_specs": [garment_size_spec()]},
    })
    spec = metadata.garment_fit.size_specs[0]
    assert spec.size_label == "m"
    assert spec.pattern_dimensions_mm.chest_mm == 1000
    assert spec.evidence.source_id == "SRC-GARMENT-SIZE-001"


def test_garment_fit_metadata_rejects_missing_category_dimensions():
    spec = garment_size_spec(
        pattern_dimensions_mm={
            "chest_mm": 1000,
            "waist_mm": 780,
            "shoulder_width_mm": 460,
            "garment_length_mm": 700,
        }
    )
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "garment_fit": {"size_specs": [spec]},
        })


@pytest.mark.parametrize(
    "evidence_override",
    [
        {"source_id": None},
        {"scope": "ingredient"},
        {"evidence_grade": "E6"},
        {"source_type": "public_research"},
    ],
)
def test_garment_fit_requires_product_specific_measurement_evidence(evidence_override):
    spec = garment_size_spec(evidence=garment_fit_evidence(**evidence_override))
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "garment_fit": {"size_specs": [spec]},
        })


def test_garment_fit_rejects_duplicate_variant_specs():
    first = garment_size_spec()
    second = garment_size_spec(size_label="large")
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "garment_fit": {"size_specs": [first, second]},
        })


def test_garment_fit_rejects_noncanonical_variant_ids():
    with pytest.raises(ValidationError):
        ProductIntelligence.model_validate({
            "schema_version": "1.0",
            "garment_fit": {"size_specs": [garment_size_spec(variant_id="variant-m")]},
        })

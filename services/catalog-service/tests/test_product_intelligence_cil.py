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

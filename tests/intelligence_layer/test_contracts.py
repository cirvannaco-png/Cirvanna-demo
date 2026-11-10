import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "intelligence-layer"))

from cirvanna_intelligence import (  # noqa: E402
    ClaimSupport, ClaimType, DataPurpose, EvidenceGrade, EvidenceRecord,
    EvidenceScope, FeedbackReason, IngredientDeclaration, ModelMetric,
    MetricDirection, MetricThreshold, ModelReadinessPolicy,
    ModelValidationCard, ModelValidationStatus, ProductClaim,
    ProductIntelligenceRecord, RecommendationAction, RecommendationOutcome,
    RightsStatus, SourceKind, SourceRecord, SuitabilityResponse,
    aggregate_feedback_cohort, assess_model_readiness, assess_product_claim,
)

TIMESTAMP = "2026-11-10T10:00:00Z"


def source(source_id="source-1", *, rights=RightsStatus.LICENSED,
           kind=SourceKind.MANUFACTURER_DOCUMENTATION,
           purposes=(DataPurpose.COMMERCIAL_RECOMMENDATION,), expires_at=None):
    return SourceRecord(
        source_id=source_id, owner="Example source owner", source_kind=kind,
        locator="https://example.org/evidence/record-1",
        access_method="documented_manual_review", rights_status=rights,
        permitted_purposes=purposes, rights_reference="contract-or-licence-record-1",
        collected_at="2026-11-01T10:00:00Z", reviewed_at="2026-11-02T10:00:00Z",
        expires_at=expires_at,
    )


def evidence(evidence_id="evidence-1", *, source_id="source-1",
             grade=EvidenceGrade.E4, scope=EvidenceScope.FINISHED_PRODUCT):
    return EvidenceRecord(
        evidence_id=evidence_id, source_id=source_id, grade=grade, scope=scope,
        reference="product-specific-label-or-report-1",
        methodology="Document review with source and product identity cross-check.",
        population="One identified finished product and its current catalogue version.",
        limitations="This evidence supports only the precise product fact and scope recorded.",
        reviewed_at=TIMESTAMP, sample_size=1,
    )


def outcome(index, suitability=SuitabilityResponse.NOT_REPORTED,
            action=RecommendationAction.REJECTED):
    return RecommendationOutcome(
        event_id=f"event-{index}", recommendation_id=f"recommendation-{index}",
        product_id="product-1", context_key="hot_humid:daily",
        contributor_token="hmac-sha256:" + f"{index:064x}", cal_decision_reference=f"cal-receipt-{index}",
        cal_verdict="SHOW", consent_granted=True, consent_receipt_id=f"consent-{index}",
        consent_scope="recommendation_outcome_learning", action=action,
        reported_suitability=suitability,
        reason_codes=(FeedbackReason.PERSONAL_PREFERENCE,)
        if suitability is SuitabilityResponse.UNSUITABLE else (),
        observed_at=TIMESTAMP, model_version="ranker-1.2.0",
    )


class SourceRegistryTests(unittest.TestCase):
    def test_unknown_source_rights_never_authorize_reuse(self):
        item = source(rights=RightsStatus.UNKNOWN, purposes=())
        self.assertFalse(item.allows(DataPurpose.COMMERCIAL_RECOMMENDATION, at=TIMESTAMP))

    def test_research_only_source_cannot_authorize_commercial_recommendation(self):
        with self.assertRaises(ValueError):
            source(rights=RightsStatus.RESEARCH_ONLY,
                   purposes=(DataPurpose.INTERNAL_RESEARCH, DataPurpose.COMMERCIAL_RECOMMENDATION))
        item = source(rights=RightsStatus.RESEARCH_ONLY,
                      purposes=(DataPurpose.INTERNAL_RESEARCH, DataPurpose.MODEL_EVALUATION))
        self.assertTrue(item.allows(DataPurpose.INTERNAL_RESEARCH, at=TIMESTAMP))
        self.assertFalse(item.allows(DataPurpose.COMMERCIAL_RECOMMENDATION, at=TIMESTAMP))

    def test_expired_licence_is_not_usable(self):
        item = source(expires_at="2026-11-09T10:00:00Z")
        self.assertFalse(item.allows(DataPurpose.COMMERCIAL_RECOMMENDATION, at=TIMESTAMP))

    def test_web_source_must_use_https_and_no_embedded_credentials(self):
        with self.assertRaises(ValueError):
            SourceRecord(
                source_id="insecure", owner="Owner", source_kind=SourceKind.PUBLIC_RESEARCH,
                locator="http://example.org/paper", access_method="manual",
                rights_status=RightsStatus.UNKNOWN, permitted_purposes=(),
                collected_at=TIMESTAMP, reviewed_at=TIMESTAMP,
            )


class EvidenceAssessmentTests(unittest.TestCase):
    def test_product_specific_research_can_support_a_finished_product_efficacy_claim(self):
        src = source(kind=SourceKind.PUBLIC_RESEARCH)
        ev = evidence(grade=EvidenceGrade.E1)
        claim = ProductClaim("claim-1", "product-1", ClaimType.FINISHED_PRODUCT_EFFICACY,
                             "Product-specific efficacy statement.", ("evidence-1",))
        assessment = assess_product_claim(claim, {ev.evidence_id: ev}, {src.source_id: src}, at=TIMESTAMP)
        self.assertEqual(assessment.support, ClaimSupport.SUPPORTED)
        self.assertTrue(assessment.user_facing_claim_allowed)

    def test_ingredient_level_study_cannot_support_finished_product_efficacy(self):
        src = source(kind=SourceKind.PUBLIC_RESEARCH)
        ev = evidence(grade=EvidenceGrade.E2, scope=EvidenceScope.INGREDIENT)
        claim = ProductClaim("claim-2", "product-1", ClaimType.FINISHED_PRODUCT_EFFICACY,
                             "Finished-product efficacy statement.", ("evidence-1",))
        assessment = assess_product_claim(claim, {ev.evidence_id: ev}, {src.source_id: src}, at=TIMESTAMP)
        self.assertEqual(assessment.support, ClaimSupport.UNSUPPORTED)
        self.assertFalse(assessment.user_facing_claim_allowed)

    def test_independent_product_test_can_support_efficacy_when_product_specific(self):
        src = source(kind=SourceKind.INDEPENDENT_PRODUCT_TEST)
        ev = evidence(grade=EvidenceGrade.E1)
        claim = ProductClaim("claim-5", "product-1", ClaimType.FINISHED_PRODUCT_EFFICACY,
                             "Independently tested finished-product claim.", ("evidence-1",))
        assessment = assess_product_claim(claim, {ev.evidence_id: ev}, {src.source_id: src}, at=TIMESTAMP)
        self.assertEqual(assessment.support, ClaimSupport.SUPPORTED)

    def test_marketing_claim_does_not_become_evidence(self):
        src = source(kind=SourceKind.MANUFACTURER_DOCUMENTATION)
        ev = evidence(grade=EvidenceGrade.E6)
        claim = ProductClaim("claim-3", "product-1", ClaimType.FINISHED_PRODUCT_EFFICACY,
                             "Marketing-only efficacy statement.", ("evidence-1",))
        assessment = assess_product_claim(claim, {ev.evidence_id: ev}, {src.source_id: src}, at=TIMESTAMP)
        self.assertEqual(assessment.support, ClaimSupport.UNSUPPORTED)

    def test_source_rights_must_allow_commercial_recommendation(self):
        src = source(rights=RightsStatus.RESEARCH_ONLY,
                     purposes=(DataPurpose.INTERNAL_RESEARCH,), kind=SourceKind.PUBLIC_RESEARCH)
        ev = evidence(grade=EvidenceGrade.E1)
        claim = ProductClaim("claim-4", "product-1", ClaimType.FINISHED_PRODUCT_EFFICACY,
                             "Product-specific efficacy statement.", ("evidence-1",))
        assessment = assess_product_claim(claim, {ev.evidence_id: ev}, {src.source_id: src}, at=TIMESTAMP)
        self.assertEqual(assessment.support, ClaimSupport.RIGHTS_UNCLEARED)
        self.assertFalse(assessment.user_facing_claim_allowed)

    def test_product_record_rejects_ingredient_level_evidence_for_a_product_label(self):
        ev = evidence(scope=EvidenceScope.INGREDIENT)
        record = ProductIntelligenceRecord(
            "product-1", 2, (IngredientDeclaration("product-1", "Glycerin", "evidence-1"),), (),
        )
        with self.assertRaises(ValueError):
            record.validate_evidence_links({ev.evidence_id: ev})

    def test_product_record_requires_unique_normalized_ingredient_labels(self):
        with self.assertRaises(ValueError):
            ProductIntelligenceRecord(
                "product-1", 1,
                (IngredientDeclaration("product-1", "Glycerin", "evidence-1"),
                 IngredientDeclaration("product-1", "  GLYCERIN ", "evidence-2")),
                (),
            )


class ModelValidationTests(unittest.TestCase):
    def test_unvalidated_model_cannot_power_user_facing_assessment(self):
        card = ModelValidationCard(
            model_id="skin-attributes", model_version="0.1", provider="internal",
            task="non-diagnostic cosmetic skin-attribute analysis",
            status=ModelValidationStatus.UNVALIDATED,
            intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
        )
        result = assess_model_readiness(card, readiness_policy())
        self.assertFalse(result.eligible)
        self.assertIn("MODEL_NOT_INDEPENDENTLY_VALIDATED", result.reason_codes)

    def test_independent_validation_requires_calibration_and_population_evaluation(self):
        with self.assertRaises(ValueError):
            ModelValidationCard(
                model_id="skin-attributes", model_version="1.0", provider="provider",
                task="non-diagnostic cosmetic skin-attribute analysis",
                status=ModelValidationStatus.INDEPENDENTLY_VALIDATED,
                intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
                validation_dataset_reference="dataset-2026", validation_report_reference="report-2026",
                evaluated_populations=("adult-image-set",),
                metrics=(ModelMetric("macro_f1", 0.88, "adult-image-set", 800),),
                known_limitations=("Performance is not established outside the evaluated image conditions.",),
            )

    def test_independently_validated_and_calibrated_model_can_be_eligible(self):
        card = ModelValidationCard(
            model_id="skin-attributes", model_version="1.0", provider="independent-provider",
            task="non-diagnostic cosmetic skin-attribute analysis",
            status=ModelValidationStatus.INDEPENDENTLY_VALIDATED,
            intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
            evaluated_populations=("adult-image-set", "skin-tone-strata"),
            metrics=(
                ModelMetric("macro_f1", 0.88, "adult-image-set", 800),
                ModelMetric("macro_f1", 0.85, "skin-tone-strata", 400),
            ),
            validation_dataset_reference="dataset-2026", validation_report_reference="report-2026",
            independent_reviewer="Independent Review Lab",
            calibration_method="isotonic calibration on a held-out set",
            expected_calibration_error=0.04, brier_score=0.11,
            known_limitations=("Performance is not established outside the evaluated image conditions.",),
        )
        result = assess_model_readiness(card, readiness_policy())
        self.assertTrue(result.eligible)
        self.assertEqual(result.reason_codes, ())


    def test_independent_validation_is_not_enough_when_policy_thresholds_fail(self):
        card = ModelValidationCard(
            model_id="skin-attributes", model_version="1.0", provider="provider",
            task="non-diagnostic cosmetic skin-attribute analysis",
            status=ModelValidationStatus.INDEPENDENTLY_VALIDATED,
            intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
            evaluated_populations=("adult-image-set", "skin-tone-strata"),
            metrics=(ModelMetric("macro_f1", 0.71, "adult-image-set", 800),),
            validation_dataset_reference="dataset-2026", validation_report_reference="report-2026",
            independent_reviewer="Independent Review Lab",
            calibration_method="isotonic calibration on a held-out set",
            expected_calibration_error=0.16, brier_score=0.27,
            known_limitations=("Performance is not established outside the evaluated image conditions.",),
        )
        result = assess_model_readiness(card, readiness_policy())
        self.assertFalse(result.eligible)
        self.assertIn("EXPECTED_CALIBRATION_ERROR_THRESHOLD_NOT_MET", result.reason_codes)
        self.assertIn("BRIER_SCORE_THRESHOLD_NOT_MET", result.reason_codes)
        self.assertIn("MODEL_METRIC_MINIMUM_NOT_MET", result.reason_codes)

    def test_model_metric_requires_policy_minimum_sample_size(self):
        card = ModelValidationCard(
            model_id="skin-attributes", model_version="1.0", provider="provider",
            task="non-diagnostic cosmetic skin-attribute analysis",
            status=ModelValidationStatus.INDEPENDENTLY_VALIDATED,
            intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
            evaluated_populations=("adult-image-set", "skin-tone-strata"),
            metrics=(
                ModelMetric("macro_f1", 0.88, "adult-image-set", 800),
                ModelMetric("macro_f1", 0.85, "skin-tone-strata", 80),
            ),
            validation_dataset_reference="dataset-2026", validation_report_reference="report-2026",
            independent_reviewer="Independent Review Lab",
            calibration_method="isotonic calibration on a held-out set",
            expected_calibration_error=0.04, brier_score=0.11,
            known_limitations=("Performance is not established outside the evaluated image conditions.",),
        )
        result = assess_model_readiness(card, readiness_policy())
        self.assertFalse(result.eligible)
        self.assertIn("MODEL_METRIC_SAMPLE_SIZE_BELOW_MINIMUM", result.reason_codes)

    def test_readiness_policy_requires_metrics_for_each_required_population(self):
        card = ModelValidationCard(
            model_id="skin-attributes", model_version="1.0", provider="provider",
            task="non-diagnostic cosmetic skin-attribute analysis",
            status=ModelValidationStatus.INDEPENDENTLY_VALIDATED,
            intended_uses=(DataPurpose.COMMERCIAL_RECOMMENDATION,),
            evaluated_populations=("adult-image-set", "skin-tone-strata"),
            metrics=(ModelMetric("macro_f1", 0.88, "adult-image-set", 800),),
            validation_dataset_reference="dataset-2026", validation_report_reference="report-2026",
            independent_reviewer="Independent Review Lab",
            calibration_method="isotonic calibration on a held-out set",
            expected_calibration_error=0.04, brier_score=0.11,
            known_limitations=("Performance is not established outside the evaluated image conditions.",),
        )
        result = assess_model_readiness(card, readiness_policy())
        self.assertFalse(result.eligible)
        self.assertIn("REQUIRED_MODEL_METRIC_MISSING", result.reason_codes)


def readiness_policy():
    return ModelReadinessPolicy(
        policy_id="skin-assessment-commercial-v1",
        task="non-diagnostic cosmetic skin-attribute analysis",
        intended_use=DataPurpose.COMMERCIAL_RECOMMENDATION,
        required_populations=("adult-image-set", "skin-tone-strata"),
        metric_thresholds=(
            MetricThreshold("macro_f1", "adult-image-set", MetricDirection.MINIMUM, 0.80, 300),
            MetricThreshold("macro_f1", "skin-tone-strata", MetricDirection.MINIMUM, 0.78, 200),
        ),
        maximum_expected_calibration_error=0.08,
        maximum_brier_score=0.18,
    )


class FeedbackTests(unittest.TestCase):
    def test_feedback_requires_explicit_purpose_bound_consent(self):
        with self.assertRaises(PermissionError):
            RecommendationOutcome(
                event_id="event-no-consent", recommendation_id="rec", product_id="product-1",
                context_key="daily", contributor_token="token", cal_decision_reference="cal-1",
                cal_verdict="SHOW", consent_granted=False, consent_receipt_id=None,
                consent_scope=None, action=RecommendationAction.REJECTED,
                reported_suitability=SuitabilityResponse.NOT_REPORTED, reason_codes=(), observed_at=TIMESTAMP,
            )

    def test_feedback_rejects_raw_contributor_identifier(self):
        with self.assertRaisesRegex(ValueError, "keyed HMAC-SHA256"):
            RecommendationOutcome(
                event_id="event-raw-id", recommendation_id="rec", product_id="product-1",
                context_key="daily", contributor_token="kelson@example.test", cal_decision_reference="cal-1",
                cal_verdict="SHOW", consent_granted=True, consent_receipt_id="consent-1",
                consent_scope="recommendation_outcome_learning", action=RecommendationAction.REJECTED,
                reported_suitability=SuitabilityResponse.NOT_REPORTED, reason_codes=(), observed_at=TIMESTAMP,
            )

    def test_feedback_requires_cal_show(self):
        with self.assertRaises(ValueError):
            RecommendationOutcome(
                event_id="event-review", recommendation_id="rec", product_id="product-1",
                context_key="daily", contributor_token="token", cal_decision_reference="cal-1",
                cal_verdict="REVIEW", consent_granted=True, consent_receipt_id="consent-1",
                consent_scope="recommendation_outcome_learning", action=RecommendationAction.REJECTED,
                reported_suitability=SuitabilityResponse.NOT_REPORTED, reason_codes=(), observed_at=TIMESTAMP,
            )

    def test_rejected_action_without_suitability_report_is_not_counted_as_negative(self):
        events = tuple(outcome(index) for index in range(30))
        aggregate = aggregate_feedback_cohort(events, unsuitable_share_review_threshold=0.5)
        self.assertIsNone(aggregate.reported_count)
        self.assertIsNone(aggregate.unsuitable_share)
        self.assertFalse(aggregate.review_recommended)

    def test_disclosure_floor_counts_actual_responses_not_impressions(self):
        events = tuple(
            outcome(index, SuitabilityResponse.SUITABLE if index < 4 else SuitabilityResponse.NOT_REPORTED)
            for index in range(30)
        )
        aggregate = aggregate_feedback_cohort(events, unsuitable_share_review_threshold=0.5)
        self.assertEqual(aggregate.status, "suppressed")
        self.assertIsNone(aggregate.suitable_count)

    def test_small_cohort_suppresses_breakdown(self):
        events = tuple(outcome(index, SuitabilityResponse.UNSUITABLE) for index in range(5))
        aggregate = aggregate_feedback_cohort(events, unsuitable_share_review_threshold=0.5)
        self.assertEqual(aggregate.status, "suppressed")
        self.assertIsNone(aggregate.unsuitable_count)
        self.assertIsNone(aggregate.unsuitable_share)

    def test_high_unsuitable_share_flags_review_but_never_suppresses_automatically(self):
        events = tuple(
            outcome(index, SuitabilityResponse.UNSUITABLE if index < 18 else SuitabilityResponse.SUITABLE,
                    RecommendationAction.REJECTED if index < 18 else RecommendationAction.SAVED)
            for index in range(30)
        )
        aggregate = aggregate_feedback_cohort(events, unsuitable_share_review_threshold=0.5)
        self.assertEqual(aggregate.status, "review_required")
        self.assertTrue(aggregate.review_recommended)
        self.assertAlmostEqual(aggregate.unsuitable_share, 0.6)
        self.assertEqual(aggregate.reason_code, "CIL_UNSUITABLE_SHARE_REVIEW")

    def test_duplicate_contributor_cannot_dominate_cohort(self):
        events = tuple(outcome(index) for index in range(29)) + (outcome(0),)
        with self.assertRaises(ValueError):
            aggregate_feedback_cohort(events, unsuitable_share_review_threshold=0.5)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCORER_PATH = ROOT / "tools" / "click_it_privacy_eval" / "score.py"
SPEC = importlib.util.spec_from_file_location("click_it_privacy_scorer", SCORER_PATH)
scorer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(scorer)


POLICY = {
    "minimum_faces_per_stratum": 50,
    "maximum_fnr_upper_95": 0.10,
    "maximum_unmasked_faces": 0,
    "reject_uncertain_outputs": True,
    "maximum_identity_feature_calls": 0,
    "maximum_age_estimation_calls": 0,
    "reject_child_processing": True,
    "reject_child_publication": True,
}
FIELDS = [
    "stratum", "ground_truth_face_count", "missed_face_count",
    "unmasked_face_count", "mask_before_embedding", "uncertain", "uncertain_output_rejected",
    "identity_feature_calls", "age_estimation_calls", "child_media",
    "child_processing_performed", "public_publication_allowed",
]


class ClickItPrivacyEvaluationTests(unittest.TestCase):
    def score_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            return scorer.score(path, POLICY)

    def base_row(self, **overrides):
        row = {
            "stratum": "low_light",
            "ground_truth_face_count": "100",
            "missed_face_count": "0",
            "unmasked_face_count": "0",
            "mask_before_embedding": "true",
            "uncertain": "false",
            "uncertain_output_rejected": "false",
            "identity_feature_calls": "0",
            "age_estimation_calls": "0",
            "child_media": "false",
            "child_processing_performed": "false",
            "public_publication_allowed": "false",
        }
        row.update(overrides)
        return row

    def test_clean_stratum_passes_preregistered_sample_and_fnr_gates(self):
        report = self.score_rows([self.base_row()])
        self.assertTrue(report["passed"])
        self.assertEqual(report["total_faces"], 100)
        self.assertLessEqual(report["strata"]["low_light"]["false_negative_rate_upper_95"], 0.10)

    def test_residual_unmasked_face_fails_even_if_fnr_threshold_passes(self):
        report = self.score_rows([self.base_row(unmasked_face_count="1")])
        self.assertFalse(report["passed"])
        self.assertGreater(report["unmasked_faces"], 0)

    def test_child_processing_and_publication_fail(self):
        report = self.score_rows([self.base_row(
            child_media="true",
            child_processing_performed="true",
            public_publication_allowed="true",
        )])
        self.assertFalse(report["passed"])
        self.assertTrue(any("child media was processed" in item for item in report["violations"]))
        self.assertTrue(any("child media was allowed public publication" in item for item in report["violations"]))

    def test_identity_or_age_estimation_calls_fail(self):
        report = self.score_rows([self.base_row(identity_feature_calls="1", age_estimation_calls="1")])
        self.assertFalse(report["passed"])
        self.assertTrue(any("identity feature call" in item for item in report["violations"]))
        self.assertTrue(any("age-estimation call" in item for item in report["violations"]))

    def test_uncertain_detector_output_fails_closed(self):
        report = self.score_rows([self.base_row(uncertain="true")])
        self.assertFalse(report["passed"])
        self.assertTrue(any("uncertain detector output" in item for item in report["violations"]))

    def test_uncertain_output_is_safe_only_when_rejected_and_not_published(self):
        report = self.score_rows([self.base_row(
            uncertain="true",
            uncertain_output_rejected="true",
            public_publication_allowed="false",
        )])
        self.assertTrue(report["passed"])

    def test_uncertain_output_cannot_be_published_even_if_rejection_flag_is_set(self):
        report = self.score_rows([self.base_row(
            uncertain="true",
            uncertain_output_rejected="true",
            public_publication_allowed="true",
        )])
        self.assertFalse(report["passed"])
        self.assertTrue(any("uncertain detector output was allowed to publish" in item for item in report["violations"]))

    def test_small_stratum_fails_sample_floor(self):
        report = self.score_rows([self.base_row(ground_truth_face_count="10")])
        self.assertFalse(report["passed"])
        self.assertFalse(report["strata"]["low_light"]["passed_sample_floor"])


if __name__ == "__main__":
    unittest.main()

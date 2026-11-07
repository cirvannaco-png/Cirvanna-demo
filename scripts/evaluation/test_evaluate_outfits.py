import unittest

from evaluate_outfits import baseline_score, evaluate


def make_case(case_id: str, session_id: str, rejected: bool = False) -> dict:
    candidates = [
        {
            "look_id": "work-set", "garment_ids": ["shirt-1", "trouser-1"],
            "category_tags": ["top", "bottom"], "style_tags": ["minimal"],
            "color_tags": ["navy"], "occasion_tags": ["work"], "exclusion_tags": [],
        },
        {
            "look_id": "evening-dress", "garment_ids": ["dress-1"],
            "category_tags": ["dress"], "style_tags": ["bold"],
            "color_tags": ["red"], "occasion_tags": ["evening"], "exclusion_tags": [],
        },
        {
            "look_id": "forbidden-leather", "garment_ids": ["jacket-1", "shirt-1"],
            "category_tags": ["outerwear", "top"], "style_tags": ["minimal"],
            "color_tags": ["navy"], "occasion_tags": ["work"], "exclusion_tags": ["leather"],
        },
    ]
    reviews = []
    relevance = {"work-set": 5, "evening-dress": 3, "forbidden-leather": 4}
    for candidate in candidates:
        look_id = candidate["look_id"]
        violation = look_id == "forbidden-leather"
        reviews.extend([
            {"look_id": look_id, "reviewer_key": "reviewer-a", "relevance": relevance[look_id], "exclusion_violation": violation},
            {"look_id": look_id, "reviewer_key": "reviewer-b", "relevance": relevance[look_id], "exclusion_violation": violation},
        ])
    return {
        "schema_version": "1.0", "case_id": case_id,
        "participant_key": "participant-001", "session_id": session_id,
        "assigned_system": "cirvanna",
        "context": {
            "required_categories": ["top", "bottom"],
            "preferred_style_tags": ["minimal"], "preferred_color_tags": ["navy"],
            "occasion": "work", "hard_excluded_item_ids": [],
            "hard_excluded_tags": ["leather"],
        },
        "candidate_outfits": candidates,
        "cirvanna_ranked_look_ids": ["forbidden-leather", "work-set", "evening-dress"],
        "human_reviews": reviews, "adjudications": [],
        "exposures": [
            {"look_id": "forbidden-leather", "action": "rejected" if rejected else "no_action", "edit_count": 0},
            {"look_id": "work-set", "action": "edited", "edit_count": 1},
            {"look_id": "evening-dress", "action": "accepted", "edit_count": 0},
        ],
    }


class OutfitEvaluationTests(unittest.TestCase):
    def test_baseline_hard_filters_declared_exclusions_and_prioritizes_context(self):
        case = make_case("case-0001", "session-0001")
        candidates = {item["look_id"]: item for item in case["candidate_outfits"]}
        self.assertIsNone(baseline_score(candidates["forbidden-leather"], case["context"]))
        self.assertGreater(
            baseline_score(candidates["work-set"], case["context"]),
            baseline_score(candidates["evening-dress"], case["context"]),
        )

    def test_relevance_diversity_exclusion_edits_and_repeat_rejection(self):
        first = make_case("case-0001", "session-0001", rejected=True)
        second = make_case("case-0002", "session-0002", rejected=True)
        result = evaluate([first, second], k=3)
        self.assertEqual(result["status"], "descriptive_only")
        self.assertEqual(result["systems"]["baseline"]["hard_exclusion_violation_rate"], 0.0)
        self.assertGreater(result["systems"]["cirvanna"]["hard_exclusion_violation_rate"], 0.0)
        self.assertEqual(result["systems"]["cirvanna"]["edited_look_rate"], 0.3333)
        self.assertEqual(result["systems"]["cirvanna"]["repeated_rejection_signature_rate"], 1.0)
        self.assertIsNotNone(result["systems"]["cirvanna"]["ndcg_at_k"])
        self.assertIsNotNone(result["systems"]["baseline"]["intra_list_diversity"])

    def test_disagreement_requires_independent_adjudication(self):
        case = make_case("case-0001", "session-0001")
        case["human_reviews"][1]["relevance"] = 2
        with self.assertRaisesRegex(ValueError, "requires adjudication"):
            evaluate([case])
        case["adjudications"] = [{
            "look_id": "work-set", "adjudicator_key": "reviewer-c",
            "relevance": 4, "exclusion_violation": False,
        }]
        self.assertEqual(evaluate([case])["status"], "descriptive_only")


    def test_participant_cannot_switch_randomized_system_arms(self):
        first = make_case("case-0001", "session-0001")
        second = make_case("case-0002", "session-0002")
        second["assigned_system"] = "baseline"
        second["exposures"] = []
        with self.assertRaisesRegex(ValueError, "one randomized system arm"):
            evaluate([first, second])

    def test_empty_baseline_slate_is_reported_as_no_result_not_zero_violations(self):
        case = make_case("case-0001", "session-0001")
        case["context"]["hard_excluded_item_ids"] = [
            "shirt-1", "trouser-1", "dress-1", "jacket-1"
        ]
        result = evaluate([case], k=3)
        baseline = result["systems"]["baseline"]
        self.assertEqual(baseline["no_result_rate"], 1.0)
        self.assertEqual(baseline["top_k_fill_rate"], 0.0)
        self.assertIsNone(baseline["hard_exclusion_violation_rate"])

    def test_reports_participant_cluster_confidence_intervals_and_reviewer_agreement(self):
        first = make_case("case-0001", "session-0001")
        second = make_case("case-0002", "session-0002")
        second["participant_key"] = "participant-002"
        result = evaluate([first, second], k=3)
        for system in ("cirvanna", "baseline"):
            intervals = result["systems"][system]["confidence_intervals_95"]
            self.assertEqual(len(intervals["ndcg_at_k"]), 2)
            self.assertLessEqual(intervals["ndcg_at_k"][0], intervals["ndcg_at_k"][1])
        paired = result["paired_cirvanna_minus_baseline_confidence_intervals_95"]
        self.assertEqual(len(paired["mean_human_relevance_top_k"]), 2)
        agreement = result["inter_rater_agreement"]
        self.assertEqual(agreement["candidate_review_pairs"], 6)
        self.assertEqual(agreement["exact_relevance_agreement_rate"], 1.0)
        self.assertEqual(agreement["hard_exclusion_agreement_rate"], 1.0)
        self.assertEqual(agreement["weighted_relevance_kappa_across_reviewer_pairs"], 1.0)
        self.assertEqual(agreement["hard_exclusion_kappa_across_reviewer_pairs"], 1.0)

    def test_duplicate_reviewer_and_duplicate_exposure_are_rejected(self):
        case = make_case("case-0001", "session-0001")
        case["human_reviews"][1]["reviewer_key"] = "reviewer-a"
        with self.assertRaisesRegex(ValueError, "exactly two independent reviewers"):
            evaluate([case])
        case = make_case("case-0001", "session-0001")
        case["exposures"].append({"look_id": "work-set", "action": "no_action", "edit_count": 0})
        with self.assertRaisesRegex(ValueError, "duplicate exposure outcome"):
            evaluate([case])
    def test_empty_dataset_makes_no_performance_claim(self):
        result = evaluate([])
        self.assertEqual(result["status"], "insufficient_human_reviewed_data")
        self.assertEqual(result["reviewed_contexts"], 0)


if __name__ == "__main__":
    unittest.main()

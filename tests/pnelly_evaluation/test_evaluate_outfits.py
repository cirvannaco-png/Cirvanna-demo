import json
import tempfile
import unittest
from pathlib import Path

from tools.pnelly_evaluation.evaluate_outfits import load_rows, session_metrics, summarize, baseline_key, inter_rater_agreement


def row(session, outfit, rank, relevance, *, occasion=True, prefs=0, excluded=False, edited=False, rejected=False, user="u1"):
    return {
        "session_id": session, "user_pseudonym": user, "outfit_id": outfit,
        "algorithm_rank": rank, "human_relevance": relevance,
        "hard_exclusion_violation": excluded, "edited": edited, "rejected": rejected,
        "occasion_match": occasion, "preference_match_count": prefs,
        "garment_categories": ["top", outfit], "style_tags": ["casual"],
        "human_reviewed": True, "reviewer_scores": [
            {"reviewer_id": "reviewer-a", "human_relevance": relevance, "hard_exclusion_violation": excluded},
            {"reviewer_id": "reviewer-b", "human_relevance": max(1, relevance - 1), "hard_exclusion_violation": excluded},
        ],
        "review_rubric_version": "v1",
    }


class OutfitEvaluationTests(unittest.TestCase):
    def test_loader_rejects_unreviewed_rows(self):
        data = row("s1", "o1", 1, 4)
        data["human_reviewed"] = False
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "human-reviewed"):
                load_rows(path)

    def test_loader_requires_two_distinct_reviewers(self):
        data = row("s1", "o1", 1, 4)
        data["reviewer_scores"][1]["reviewer_id"] = "reviewer-a"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "two distinct reviewers"):
                load_rows(path)

    def test_loader_rejects_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text(json.dumps({"session_id": "s1"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing fields"):
                load_rows(path)

    def test_inter_rater_agreement_uses_raw_blinded_scores(self):
        rows = [row("s1", "o1", 1, 5), row("s1", "o2", 2, 3)]
        agreement = inter_rater_agreement(rows)
        self.assertEqual(agreement["adjudicated_candidate_rows"], 2)
        self.assertEqual(agreement["exact_relevance_agreement_rate"], 0.0)
        self.assertEqual(agreement["hard_exclusion_agreement_rate"], 1.0)
        self.assertIsNone(agreement["hard_exclusion_cohen_kappa"])

    def test_baseline_hard_exclusion_is_absolute_priority(self):
        unsafe = row("s1", "a", 1, 5, occasion=True, prefs=100, excluded=True)
        safe = row("s1", "b", 2, 3, occasion=False, prefs=0)
        self.assertLess(baseline_key(safe), baseline_key(unsafe))

    def test_repeated_rejection_counts_distinct_sessions_not_duplicate_events(self):
        rows = [
            row("s1", "o1", 1, 5, rejected=True),
            row("s1", "o2", 2, 4),
            row("s2", "o1", 1, 4, rejected=True),
            row("s2", "o3", 2, 3),
        ]
        sessions = session_metrics(rows, "algorithm_rank", 3)
        report = summarize(sessions, rows, 3)
        self.assertEqual(report["repeated_rejection_pairs"], 1)
        self.assertEqual(report["repeated_rejection_pairs_in_multiple_sessions"], 1)

    def test_duplicate_candidate_and_duplicate_rank_are_rejected(self):
        for duplicate in ("candidate", "rank"):
            rows = [row("s1", "o1", 1, 4), row("s1", "o1" if duplicate == "candidate" else "o2", 1 if duplicate == "rank" else 2, 3)]
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "data.jsonl"
                path.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    load_rows(path)

    def test_empty_dataset_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("# no labels yet\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No human-reviewed rows"):
                load_rows(path)


if __name__ == "__main__":
    unittest.main()

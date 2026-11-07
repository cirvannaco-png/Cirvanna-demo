import json
import tempfile
import unittest
from pathlib import Path

from tools.pnelly_evaluation.evaluate_outfits import load_rows, summarize, baseline_key


def row(session, outfit, rank, relevance, *, occasion=True, prefs=0, excluded=False, edited=False, rejected=False, user="u1"):
    return {
        "session_id": session, "user_pseudonym": user, "outfit_id": outfit,
        "algorithm_rank": rank, "human_relevance": relevance,
        "hard_exclusion_violation": excluded, "edited": edited, "rejected": rejected,
        "occasion_match": occasion, "preference_match_count": prefs,
        "garment_categories": ["top", outfit], "style_tags": ["casual"],
        "human_reviewed": True, "reviewer_id": "reviewer-a",
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

    def test_loader_rejects_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text(json.dumps({"session_id": "s1"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing fields"):
                load_rows(path)

    def test_baseline_prioritizes_occasion_and_explicit_preferences(self):
        wrong_occasion = row("s1", "a", 1, 5, occasion=False, prefs=9)
        occasion_match = row("s1", "b", 2, 3, occasion=True, prefs=1)
        self.assertLess(baseline_key(occasion_match), baseline_key(wrong_occasion))

    def test_metrics_count_hard_exclusions_edits_and_repeated_rejections(self):
        rows = [
            row("s1", "o1", 1, 5, excluded=True, edited=True, rejected=True),
            row("s1", "o2", 2, 4, rejected=True),
            row("s1", "o3", 3, 3),
            row("s2", "o1", 1, 4, rejected=True),
            row("s2", "o4", 2, 3),
            row("s2", "o5", 3, 2),
        ]
        report = summarize(rows, "algorithm_rank", 3)
        self.assertEqual(report["sessions"], 2)
        self.assertEqual(report["hard_exclusion_violation_rate_at_k"], 0.1667)
        self.assertEqual(report["user_edit_rate_at_k"], 0.1667)
        self.assertEqual(report["repeated_rejection_rate"], 0.5)

    def test_empty_dataset_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("# no labels yet\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No human-reviewed rows"):
                load_rows(path)


if __name__ == "__main__":
    unittest.main()

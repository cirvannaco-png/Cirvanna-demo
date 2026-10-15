from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from cultural_identity import (  # noqa: E402
    CulturalRequirement,
    RequirementKind,
    RequirementVerdict,
    evaluate,
)


def requirement(requirement_id, kind, attribute, *, hard=True, user_id="u1"):
    return CulturalRequirement(
        requirement_id=requirement_id,
        declaration_id=f"decl-{requirement_id}",
        user_id=user_id,
        attribute=attribute,
        kind=kind,
        hard=hard,
    )


class CulturalIdentityPolicyTests(unittest.TestCase):
    def test_explicit_required_attribute_blocks_when_complete_and_absent(self):
        result = evaluate(
            "u1", "item-1", ("cotton",),
            (requirement("r1", RequirementKind.REQUIRED_ATTRIBUTE, "long-sleeve"),),
            candidate_attributes_complete=True,
        )
        self.assertEqual(result.verdict, RequirementVerdict.BLOCK)
        self.assertEqual(result.hard_conflict_ids, ("r1",))

    def test_forbidden_attribute_blocks_when_present(self):
        result = evaluate(
            "u1", "item-1", ("red", "sleeveless"),
            (requirement("r1", RequirementKind.FORBIDDEN_ATTRIBUTE, "sleeveless"),),
            candidate_attributes_complete=False,
        )
        self.assertEqual(result.verdict, RequirementVerdict.BLOCK)

    def test_missing_candidate_metadata_routes_to_review(self):
        result = evaluate(
            "u1", "item-1", ("cotton",),
            (requirement("r1", RequirementKind.REQUIRED_ATTRIBUTE, "long-sleeve"),),
            candidate_attributes_complete=False,
        )
        self.assertEqual(result.verdict, RequirementVerdict.REVIEW)
        self.assertIn("CULTURAL_CANDIDATE_METADATA_INCOMPLETE", result.reason_codes)

    def test_soft_conflict_does_not_block(self):
        result = evaluate(
            "u1", "item-1", ("sleeveless",),
            (requirement("r1", RequirementKind.FORBIDDEN_ATTRIBUTE, "sleeveless", hard=False),),
            candidate_attributes_complete=True,
        )
        self.assertEqual(result.verdict, RequirementVerdict.PASS)
        self.assertEqual(result.soft_conflict_ids, ("r1",))

    def test_other_users_requirements_are_ignored(self):
        result = evaluate(
            "u2", "item-1", ("sleeveless",),
            (requirement("r1", RequirementKind.FORBIDDEN_ATTRIBUTE, "sleeveless", user_id="u1"),),
            candidate_attributes_complete=True,
        )
        self.assertEqual(result.verdict, RequirementVerdict.PASS)

    def test_hard_conflict_dominates_metadata_review(self):
        requirements = (
            requirement("r1", RequirementKind.FORBIDDEN_ATTRIBUTE, "sleeveless"),
            requirement("r2", RequirementKind.REQUIRED_ATTRIBUTE, "long-sleeve"),
        )
        result = evaluate("u1", "item-1", ("sleeveless",), requirements, candidate_attributes_complete=False)
        self.assertEqual(result.verdict, RequirementVerdict.BLOCK)

    def test_invalid_requirement_is_rejected(self):
        with self.assertRaises(ValueError):
            CulturalRequirement("r1", "", "u1", "sleeves", RequirementKind.REQUIRED_ATTRIBUTE)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "identity-intelligence"))

from usi import ColorPreferenceProfile, StylePreference, USIProfile  # noqa: E402


class ColorPreferenceProfileTests(unittest.TestCase):
    def test_round_trip_preserves_three_distinct_user_declared_groups(self):
        profile = ColorPreferenceProfile(
            "user-1", 4,
            liked_colors=("Teal", "Soft cream"),
            disliked_colors=("Neon orange",),
            feel_best_colors=("Deep blue", "Warm gold"),
        )
        records = profile.to_preference_records()
        restored = ColorPreferenceProfile.from_style_preferences("user-1", 4, records)
        self.assertEqual(restored, profile)
        self.assertTrue(all(record["attribute"].startswith("color_profile:") for record in records))
        by_attribute = {record["attribute"]: record["active"] for record in records}
        self.assertFalse(by_attribute["color_profile:disliked:Neon orange"])
        self.assertTrue(by_attribute["color_profile:liked:Teal"])

    def test_merge_replaces_only_colour_namespace_and_preserves_other_preferences(self):
        existing = USIProfile(
            "profile-1", "user-1", "usi-v1",
            (
                StylePreference("style-1", "user-1", "style:editorial", 0.8),
                StylePreference("old-colour", "user-1", "color_profile:liked:old blue"),
                StylePreference("material-1", "user-1", "material:linen", 0.7),
            ),
        )
        colour = ColorPreferenceProfile("user-1", 5, ("Teal",), ("Neon orange",), ("Deep blue",))
        merged = colour.merge_into_usi_profile(existing)
        attributes = [item.attribute for item in merged.preferences]
        self.assertIn("style:editorial", attributes)
        self.assertIn("material:linen", attributes)
        self.assertNotIn("color_profile:liked:old blue", attributes)
        self.assertIn("color_profile:liked:Teal", attributes)

    def test_colours_are_normalized_for_duplicate_detection(self):
        with self.assertRaises(ValueError):
            ColorPreferenceProfile("user-1", 0, ("Teal", " teal "))

    def test_same_colour_cannot_be_both_liked_and_disliked(self):
        with self.assertRaises(ValueError):
            ColorPreferenceProfile("user-1", 0, ("Blue",), ("blue",))

    def test_custom_best_colours_remain_separate_from_likes(self):
        profile = ColorPreferenceProfile("user-1", 1, ("Olive",), (), ("Deep plum",))
        groups = {item.attribute.split(":")[1] for item in profile.to_style_preferences()}
        self.assertEqual(groups, {"liked", "feel_best"})

    def test_profile_version_and_owner_are_validated(self):
        with self.assertRaises(ValueError):
            ColorPreferenceProfile("", 0)
        with self.assertRaises(ValueError):
            ColorPreferenceProfile("user-1", -1)

    def test_profile_merge_rejects_cross_user_mutation(self):
        profile = USIProfile("profile-1", "user-2", "usi-v1", ())
        colour = ColorPreferenceProfile("user-1", 1, ("Teal",))
        with self.assertRaises(ValueError):
            colour.merge_into_usi_profile(profile)


if __name__ == "__main__":
    unittest.main()

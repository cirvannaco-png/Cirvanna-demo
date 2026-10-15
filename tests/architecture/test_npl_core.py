from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "preferences"))

from npl import (  # noqa: E402
    NegativePreference,
    PreferenceSource,
    TargetType,
    evaluate,
    record_rejection,
    retract_preference,
)


def explicit(preference_id: str, target_type: TargetType, value: str, user_id: str = "user-1"):
    return NegativePreference(
        preference_id=preference_id,
        user_id=user_id,
        target_type=target_type,
        target_value=value,
        source=PreferenceSource.USER_DECLARED,
    )


def learned(preference_id: str = "learned-1", value: str = "red", user_id: str = "user-1"):
    return NegativePreference(
        preference_id=preference_id,
        user_id=user_id,
        target_type=TargetType.ATTRIBUTE,
        target_value=value,
        source=PreferenceSource.LEARNED_REJECTION,
    )


class NPLHardVetoTests(unittest.TestCase):
    def test_explicit_item_exclusion_blocks(self):
        decision = evaluate("user-1", "item-7", (), (explicit("p1", TargetType.ITEM, "item-7"),))
        self.assertTrue(decision.blocked)
        self.assertFalse(decision.may_display)
        self.assertEqual(decision.reason_code, "NPL_HARD_NEGATIVE")
        self.assertEqual(decision.hard_veto_preference_ids, ("p1",))

    def test_explicit_attribute_exclusion_is_case_insensitive(self):
        decision = evaluate("user-1", "item-7", ("RED", "cotton"), (explicit("p1", TargetType.ATTRIBUTE, "red"),))
        self.assertTrue(decision.blocked)

    def test_three_unique_rejections_create_durable_veto(self):
        pref = learned()
        for event_id in ("reject-1", "reject-2"):
            pref = record_rejection(pref, event_id)
        before_threshold = evaluate("user-1", "item-7", ("red",), (pref,))
        self.assertFalse(before_threshold.blocked)
        self.assertEqual(before_threshold.soft_negative_preference_ids, ("learned-1",))
        pref = record_rejection(pref, "reject-3")
        after_threshold = evaluate("user-1", "item-7", ("red",), (pref,))
        self.assertTrue(after_threshold.blocked)

    def test_duplicate_rejection_event_is_idempotent(self):
        pref = record_rejection(learned(), "reject-1")
        again = record_rejection(pref, "reject-1")
        self.assertEqual(pref, again)
        self.assertEqual(again.rejection_count, 1)

    def test_other_users_preferences_never_leak(self):
        decision = evaluate("user-2", "item-7", ("red",), (explicit("p1", TargetType.ATTRIBUTE, "red", user_id="user-1"),))
        self.assertFalse(decision.blocked)

    def test_correction_retracts_preference_and_is_idempotent(self):
        pref = explicit("p1", TargetType.ITEM, "item-7")
        retracted = retract_preference(pref, "correction-1")
        self.assertEqual(retract_preference(retracted, "correction-1"), retracted)
        decision = evaluate("user-1", "item-7", (), (retracted,))
        self.assertFalse(decision.blocked)

    def test_retracted_preference_cannot_learn_more_rejections(self):
        pref = retract_preference(learned(), "correction-1")
        with self.assertRaises(ValueError):
            record_rejection(pref, "reject-1")

    def test_invalid_empty_rejection_event_is_rejected(self):
        with self.assertRaises(ValueError):
            record_rejection(learned(), " ")

    def test_npl_pass_is_not_full_display_authorization(self):
        decision = evaluate("user-1", "item-7", (), ())
        self.assertTrue(decision.may_display)
        self.assertEqual(decision.reason_code, "NPL_NO_HARD_VETO")
        # Consumer must still require the CaTaCaCi CAL verdict before displaying.

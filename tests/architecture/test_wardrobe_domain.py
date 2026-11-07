from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from wardrobe import WardrobeItem, WardrobeItemStatus, transition_item  # noqa: E402

class WardrobeDomainTests(unittest.TestCase):
    def item(self, **overrides):
        values = {
            "item_id": "item-001",
            "owner_user_id": "user-1",
            "display_name": "Blue shirt",
            "category": "tops",
            "attributes": ("blue", "cotton"),
            "image_asset_id": "asset-001",
            "image_storage_consent": True,
        }
        values.update(overrides)
        return WardrobeItem(**values)

    def test_category_aliases_normalize_to_stable_taxonomy_ids(self):
        self.assertEqual(self.item(category="Footwear").category, "shoes")
        self.assertEqual(self.item(category="jewellery").category, "jewelry")
        self.assertEqual(self.item(category="Sunglasses").category, "eyewear")
        self.assertEqual(self.item(category="Bottoms").category, "lower_body")

    def test_category_taxonomy_covers_beauty_and_accessory_items(self):
        from wardrobe import WARDROBE_CATEGORIES, TAXONOMY_VERSION
        category_ids = {entry["id"] for entry in WARDROBE_CATEGORIES}
        self.assertEqual(TAXONOMY_VERSION, "1.0.0")
        self.assertTrue({"makeup", "skincare", "haircare", "shoes", "bags", "ties", "eyewear", "watches"} <= category_ids)

    def test_unknown_category_is_rejected_instead_of_silently_misclassified(self):
        with self.assertRaisesRegex(ValueError, "unsupported wardrobe category"):
            self.item(category="unverified-special-type")

    def test_create_requires_consent_for_persisted_image(self):
        with self.assertRaises(ValueError):
            self.item(image_storage_consent=False)

    def test_asset_ids_are_opaque_not_urls(self):
        with self.assertRaises(ValueError):
            self.item(image_asset_id="https://example.com/photo.jpg")

    def test_owner_can_archive_and_restore_with_versions(self):
        item = self.item(status=WardrobeItemStatus.ACTIVE)
        archived = transition_item(
            item, actor_user_id="user-1",
            target_status=WardrobeItemStatus.ARCHIVED, command_id="cmd-001",
        )
        self.assertEqual(archived.version, 2)
        self.assertEqual(archived.status, WardrobeItemStatus.ARCHIVED)
        restored = transition_item(
            archived, actor_user_id="user-1",
            target_status=WardrobeItemStatus.ACTIVE, command_id="cmd-002",
        )
        self.assertEqual(restored.version, 3)

    def test_other_user_cannot_change_item(self):
        with self.assertRaises(PermissionError):
            transition_item(
                self.item(), actor_user_id="user-2",
                target_status=WardrobeItemStatus.DELETED, command_id="cmd-001",
            )

    def test_deleted_item_is_terminal(self):
        deleted = transition_item(
            self.item(status=WardrobeItemStatus.ARCHIVED), actor_user_id="user-1",
            target_status=WardrobeItemStatus.DELETED, command_id="cmd-delete",
        )
        with self.assertRaises(ValueError):
            transition_item(
                deleted, actor_user_id="user-1",
                target_status=WardrobeItemStatus.ACTIVE, command_id="cmd-restore",
            )

    def test_repeated_command_is_idempotent_for_same_current_state(self):
        item = transition_item(
            self.item(), actor_user_id="user-1",
            target_status=WardrobeItemStatus.ACTIVE, command_id="cmd-001",
        )
        same = transition_item(
            item, actor_user_id="user-1",
            target_status=WardrobeItemStatus.ACTIVE, command_id="cmd-001",
        )
        self.assertIs(same, item)

if __name__ == "__main__":
    unittest.main()

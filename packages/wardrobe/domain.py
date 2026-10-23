"""Wardrobe item domain contract and ownership-checked lifecycle rules."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re

ASSET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")

class WardrobeItemStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"

_ALLOWED_TRANSITIONS = {
    WardrobeItemStatus.DRAFT: {
        WardrobeItemStatus.ACTIVE, WardrobeItemStatus.ARCHIVED, WardrobeItemStatus.DELETED,
    },
    WardrobeItemStatus.ACTIVE: {
        WardrobeItemStatus.ARCHIVED, WardrobeItemStatus.DELETED,
    },
    WardrobeItemStatus.ARCHIVED: {
        WardrobeItemStatus.ACTIVE, WardrobeItemStatus.DELETED,
    },
    WardrobeItemStatus.DELETED: set(),
}

@dataclass(frozen=True)
class WardrobeItem:
    item_id: str
    owner_user_id: str
    display_name: str
    category: str
    attributes: tuple[str, ...] = ()
    catalog_product_id: str | None = None
    image_asset_id: str | None = None
    image_storage_consent: bool = False
    status: WardrobeItemStatus = WardrobeItemStatus.DRAFT
    version: int = 1
    last_command_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("item_id", "owner_user_id", "display_name", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if not isinstance(self.attributes, tuple):
            raise ValueError("attributes must be a tuple")
        if any(not isinstance(value, str) or not value.strip() for value in self.attributes):
            raise ValueError("attributes must contain non-empty strings")
        normalized = [value.strip().casefold() for value in self.attributes]
        if len(normalized) != len(set(normalized)):
            raise ValueError("attributes must not contain duplicates")
        if self.catalog_product_id is not None and (
            not isinstance(self.catalog_product_id, str) or not self.catalog_product_id.strip()
        ):
            raise ValueError("catalog_product_id must be non-empty or None")
        if self.image_asset_id is not None:
            if not isinstance(self.image_asset_id, str) or not ASSET_ID_PATTERN.fullmatch(self.image_asset_id.strip()):
                raise ValueError("image_asset_id must be an opaque internal asset identifier")
            if not self.image_storage_consent:
                raise ValueError("an image asset requires explicit image_storage_consent")
        if self.status not in WardrobeItemStatus:
            raise ValueError("status must be a WardrobeItemStatus")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if self.last_command_id is not None and not self.last_command_id.strip():
            raise ValueError("last_command_id must be non-empty or None")

def transition_item(
    item: WardrobeItem,
    *,
    actor_user_id: str,
    target_status: WardrobeItemStatus,
    command_id: str,
) -> WardrobeItem:
    """Return an updated item or fail; persistence must enforce this atomically."""
    if not isinstance(item, WardrobeItem):
        raise ValueError("item must be a WardrobeItem")
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise ValueError("actor_user_id must not be empty")
    if actor_user_id != item.owner_user_id:
        raise PermissionError("wardrobe item is owned by another user")
    if not isinstance(target_status, WardrobeItemStatus):
        raise ValueError("target_status must be a WardrobeItemStatus")
    if not isinstance(command_id, str) or not command_id.strip():
        raise ValueError("command_id must not be empty")
    if item.status is target_status:
        if item.last_command_id == command_id:
            return item
        raise ValueError("item is already in the requested state")
    if target_status not in _ALLOWED_TRANSITIONS[item.status]:
        raise ValueError(f"invalid wardrobe transition: {item.status.value} -> {target_status.value}")
    return replace(
        item,
        status=target_status,
        version=item.version + 1,
        last_command_id=command_id,
    )

"""Wardrobe item domain contract and ownership-checked lifecycle rules."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re

from .taxonomy import normalize_category

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
    commerce_order_id: str | None = None
    commerce_order_item_id: str | None = None
    purchase_event_id: str | None = None
    purchase_quantity: int | None = None
    purchase_currency: str | None = None
    purchase_unit_price_minor: int | None = None
    purchase_paid_at: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("item_id", "owner_user_id", "display_name", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        object.__setattr__(self, "category", normalize_category(self.category))
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
        if not isinstance(self.status, WardrobeItemStatus):
            raise ValueError("status must be a WardrobeItemStatus")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if self.last_command_id is not None and not self.last_command_id.strip():
            raise ValueError("last_command_id must be non-empty or None")
        purchase_fields = (self.commerce_order_id, self.commerce_order_item_id, self.purchase_event_id, self.purchase_quantity, self.purchase_currency, self.purchase_unit_price_minor, self.purchase_paid_at)
        if any(value is not None for value in purchase_fields):
            if not all(value is not None for value in purchase_fields):
                raise ValueError("purchase provenance fields must be supplied together")
            for name in ("commerce_order_id", "commerce_order_item_id", "purchase_event_id"):
                value = getattr(self, name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be non-empty")
            if not isinstance(self.purchase_quantity, int) or isinstance(self.purchase_quantity, bool) or self.purchase_quantity < 1:
                raise ValueError("purchase_quantity must be a positive integer")
            if not isinstance(self.purchase_currency, str) or len(self.purchase_currency) != 3 or not self.purchase_currency.isupper():
                raise ValueError("purchase_currency must be a three-letter uppercase code")
            if not isinstance(self.purchase_unit_price_minor, int) or isinstance(self.purchase_unit_price_minor, bool) or self.purchase_unit_price_minor < 0:
                raise ValueError("purchase_unit_price_minor must be a non-negative integer")
            if not isinstance(self.purchase_paid_at, str) or not self.purchase_paid_at.strip():
                raise ValueError("purchase_paid_at must be non-empty")

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

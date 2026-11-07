"""Versioned, extensible category vocabulary for user-owned wardrobe items.

Category IDs are stable machine keys. Labels are presentation-only. Legacy aliases
are normalized at the domain boundary so old records remain readable.
"""
from __future__ import annotations

TAXONOMY_VERSION = "1.0.0"

# Keep IDs stable: integrations should store these keys, never localized labels.
WARDROBE_CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": "tops", "label": "Tops", "group": "clothing"},
    {"id": "outerwear", "label": "Outerwear", "group": "clothing"},
    {"id": "lower_body", "label": "Bottoms", "group": "clothing"},
    {"id": "dress", "label": "Dresses and jumpsuits", "group": "clothing"},
    {"id": "suits", "label": "Suits and tailoring", "group": "clothing"},
    {"id": "activewear", "label": "Activewear", "group": "clothing"},
    {"id": "swimwear", "label": "Swimwear", "group": "clothing"},
    {"id": "underwear", "label": "Underwear and lingerie", "group": "clothing"},
    {"id": "sleepwear", "label": "Sleepwear", "group": "clothing"},
    {"id": "shoes", "label": "Shoes and footwear", "group": "footwear"},
    {"id": "bags", "label": "Bags", "group": "accessories"},
    {"id": "jewelry", "label": "Jewellery", "group": "accessories"},
    {"id": "ties", "label": "Ties and bow ties", "group": "accessories"},
    {"id": "eyewear", "label": "Glasses and sunglasses", "group": "accessories"},
    {"id": "watches", "label": "Watches", "group": "accessories"},
    {"id": "belts", "label": "Belts", "group": "accessories"},
    {"id": "scarves", "label": "Scarves", "group": "accessories"},
    {"id": "hats", "label": "Hats and headwear", "group": "accessories"},
    {"id": "hair_accessories", "label": "Hair accessories", "group": "accessories"},
    {"id": "socks", "label": "Socks and hosiery", "group": "accessories"},
    {"id": "accessories", "label": "Other accessories", "group": "accessories"},
    {"id": "makeup", "label": "Makeup", "group": "beauty"},
    {"id": "skincare", "label": "Skincare", "group": "beauty"},
    {"id": "haircare", "label": "Haircare and styling", "group": "beauty"},
    {"id": "fragrance", "label": "Fragrance", "group": "beauty"},
    {"id": "other", "label": "Other", "group": "other"},
)

_CATEGORY_IDS = frozenset(item["id"] for item in WARDROBE_CATEGORIES)
_ALIASES = {
    "bottoms": "lower_body",
    "trousers": "lower_body",
    "pants": "lower_body",
    "footwear": "shoes",
    "shoe": "shoes",
    "jewellery": "jewelry",
    "glasses": "eyewear",
    "sunglasses": "eyewear",
    "frames": "eyewear",
    "bow_ties": "ties",
    "bow_tie": "ties",
    "dress_and_jumpsuits": "dress",
    "dresses": "dress",
    "lingerie": "underwear",
    "haircare_products": "haircare",
}


def normalize_category(value: str) -> str:
    """Return a stable category key or reject an unsupported category."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("category must not be empty")
    key = value.strip().casefold().replace("-", "_").replace(" ", "_")
    key = _ALIASES.get(key, key)
    if key not in _CATEGORY_IDS:
        raise ValueError(f"unsupported wardrobe category: {value.strip()}")
    return key


def list_categories() -> dict[str, object]:
    """Return a copy-safe, versioned category payload for clients."""
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "categories": [dict(item) for item in WARDROBE_CATEGORIES],
    }

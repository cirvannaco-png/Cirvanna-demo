"""Deterministic, wardrobe-grounded assembly for Tari's daily three looks.

This module does not infer body traits, identify people, invent garments, or render
Virtual Twin previews. It uses only active wardrobe records and context explicitly
provided by the user.
"""
from __future__ import annotations

from itertools import product
import re
from typing import Any

_TOPS = {"tops", "top", "shirt", "shirts", "blouse", "blouses", "t-shirt", "sweater"}
_BOTTOMS = {"lower_body", "bottoms", "bottom", "trousers", "pants", "jeans", "skirt", "shorts"}
_DRESSES = {"dress", "dresses", "jumpsuit", "one_piece"}
_SHOES = {"shoes", "shoe", "footwear", "sneakers", "boots", "sandals"}
_LAYERS = {"outerwear", "jacket", "coat", "cardigan", "blazer"}
_ACCESSORIES = {"accessories", "accessory", "bag", "belt", "scarf", "hat", "jewelry"}
_ROLES = (
    ("Everyday", "A practical combination from the pieces you already own."),
    ("Elevated", "A more finished combination, using an available layer or accessory where possible."),
    ("Explore", "A distinct combination that brings different pieces of your wardrobe into rotation."),
)


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 1}


def _category(item: dict[str, Any]) -> str:
    return str(item.get("category", "")).strip().casefold().replace(" ", "_")


def _item_tokens(item: dict[str, Any]) -> set[str]:
    values = [str(item.get("display_name", "")), str(item.get("category", ""))]
    attributes = item.get("attributes", [])
    if isinstance(attributes, list):
        values.extend(value for value in attributes if isinstance(value, str))
    return _tokens(" ".join(values))


def build_daily_looks(
    items: list[dict[str, Any]],
    *,
    occasion: str | None = None,
    climate: str | None = None,
) -> dict[str, Any]:
    """Build up to three unique outfits; never repeat an identical combination."""
    active = [
        item for item in items
        if isinstance(item, dict) and item.get("status") == "active"
        and isinstance(item.get("item_id"), str)
        and isinstance(item.get("display_name"), str)
        and isinstance(item.get("category"), str)
    ]
    tops = [item for item in active if _category(item) in _TOPS]
    bottoms = [item for item in active if _category(item) in _BOTTOMS]
    dresses = [item for item in active if _category(item) in _DRESSES]
    shoes = [item for item in active if _category(item) in _SHOES]
    layers = [None, *[item for item in active if _category(item) in _LAYERS]]
    accessories = [None, *[item for item in active if _category(item) in _ACCESSORIES]]

    bases = [(top, bottom, shoe) for top, bottom, shoe in product(tops, bottoms, shoes)]
    bases.extend((dress, None, shoe) for dress, shoe in product(dresses, shoes))

    combinations: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for base in bases:
        for layer, accessory in product(layers, accessories):
            selected = [item for item in (*base, layer, accessory) if item is not None]
            ids = tuple(sorted(str(item["item_id"]) for item in selected))
            if len(ids) != len(set(ids)):
                continue
            combinations.setdefault(ids, selected)
            if len(combinations) >= 1500:
                break
        if len(combinations) >= 1500:
            break

    context_tokens = _tokens(occasion) | _tokens(climate)

    def context_score(outfit: list[dict[str, Any]]) -> int:
        return sum(len(context_tokens & _item_tokens(item)) for item in outfit)

    unique_outfits = list(combinations.values())
    selected_ids: set[tuple[str, ...]] = set()
    selected_items: set[str] = set()
    looks = []

    for index, (role, description) in enumerate(_ROLES):
        available = [
            outfit for outfit in unique_outfits
            if tuple(sorted(str(item["item_id"]) for item in outfit)) not in selected_ids
        ]
        if role == "Everyday":
            available.sort(key=lambda outfit: (
                -context_score(outfit), len(outfit),
                tuple(sorted(str(item["item_id"]) for item in outfit)),
            ))
        elif role == "Elevated":
            available.sort(key=lambda outfit: (
                -context_score(outfit), -len(outfit),
                tuple(sorted(str(item["item_id"]) for item in outfit)),
            ))
        else:
            available.sort(key=lambda outfit: (
                -len({str(item["item_id"]) for item in outfit} - selected_items),
                -context_score(outfit),
                tuple(sorted(str(item["item_id"]) for item in outfit)),
            ))

        if available:
            outfit = available[0]
            ids = tuple(sorted(str(item["item_id"]) for item in outfit))
            selected_ids.add(ids)
            selected_items.update(ids)
            looks.append({
                "role": role,
                "status": "ready",
                "items": [{
                    "item_id": item["item_id"],
                    "display_name": item["display_name"],
                    "category": item["category"],
                    "attributes": item.get("attributes", []) if isinstance(item.get("attributes", []), list) else [],
                } for item in outfit],
                "missing": [],
                "reason": description + (
                    f" Context uses your selected occasion: {occasion}." if occasion else ""
                ) + (f" Climate context you supplied: {climate}." if climate else ""),
            })
            continue

        missing = []
        if not shoes:
            missing.append("shoes")
        if not dresses and not (tops and bottoms):
            if not tops:
                missing.append("tops")
            if not bottoms:
                missing.append("bottoms")
            if not dresses:
                missing.append("a dress or a top-and-bottom combination")
        if not missing:
            missing.append("additional distinct wardrobe pieces for another unique combination")
        looks.append({
            "role": role,
            "status": "needs_items",
            "items": [],
            "missing": list(dict.fromkeys(missing)),
            "reason": description + " This option is withheld rather than repeating an identical outfit or inventing garments.",
        })

    ready_count = sum(look["status"] == "ready" for look in looks)
    return {
        "looks": looks,
        "ready_count": ready_count,
        "wardrobe_item_count": len(active),
        "preview_status": "unavailable",
        "preview_message": "Virtual Twin preview is unavailable until persistent Twin ownership, active consent, authorized assets and a validated renderer are connected.",
    }

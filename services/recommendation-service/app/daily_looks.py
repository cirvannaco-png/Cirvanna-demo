"""Deterministic daily outfit composition from an owner-scoped wardrobe snapshot.

This module never invents wardrobe items or marketplace products. It creates
three role slots and reports missing wardrobe coverage instead of duplicating
an outfit to fill the response.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

POLICY_VERSION = "tari-daily-looks-v1"
ROLES = ("everyday", "elevated", "explore")

_CATEGORY_ALIASES = {
    "top": "top", "tops": "top", "upper_body": "top", "shirt": "top", "shirts": "top",
    "t-shirt": "top", "tshirts": "top", "t_shirts": "top", "tee": "top", "tees": "top",
    "blouse": "top", "blouses": "top", "sweater": "top", "sweaters": "top",
    "knitwear": "top", "hoodie": "top", "hoodies": "top",
    "bottom": "bottom", "bottoms": "bottom", "lower_body": "bottom", "trouser": "bottom",
    "trousers": "bottom", "pants": "bottom", "jeans": "bottom",
    "skirt": "bottom", "skirts": "bottom", "shorts": "bottom",
    "leggings": "bottom",
    "dress": "one_piece", "dresses": "one_piece", "jumpsuit": "one_piece",
    "jumpsuits": "one_piece", "romper": "one_piece", "overalls": "one_piece",
    "one_piece": "one_piece", "full_outfit": "one_piece", "outfit_set": "one_piece",
    "shoe": "footwear", "shoes": "footwear", "footwear": "footwear",
    "sneaker": "footwear", "sneakers": "footwear", "boot": "footwear",
    "boots": "footwear", "sandal": "footwear", "sandals": "footwear",
    "heels": "footwear", "flats": "footwear",
    "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear",
    "cardigan": "outerwear", "outerwear": "outerwear",
    "bag": "accessory", "belt": "accessory", "watch": "accessory",
    "scarf": "accessory", "hat": "accessory", "jewellery": "accessory",
    "jewelry": "accessory", "accessory": "accessory", "accessories": "accessory",
}
_ROLE_TERMS = {
    "everyday": ("casual", "daily", "everyday", "comfortable", "relaxed"),
    "elevated": ("formal", "work", "office", "smart", "evening", "tailored", "elegant"),
    "explore": ("bold", "statement", "editorial", "creative", "experimental", "pattern"),
}


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[_-]+", " ", value.casefold()).split())


def _kind(item: dict[str, Any]) -> str | None:
    raw = _normalise(str(item.get("category", "")))
    direct = _CATEGORY_ALIASES.get(raw.replace(" ", "_")) or _CATEGORY_ALIASES.get(raw)
    if direct:
        return direct
    for attribute in item.get("attributes", []):
        key = _normalise(str(attribute)).split(":", 1)[0]
        candidate = _CATEGORY_ALIASES.get(key.replace(" ", "_")) or _CATEGORY_ALIASES.get(key)
        if candidate:
            return candidate
    return None


def _item_text(item: dict[str, Any]) -> str:
    fields = [str(item.get("display_name", "")), str(item.get("category", ""))]
    fields.extend(str(value) for value in item.get("attributes", []))
    return _normalise(" ".join(fields))


def _stable_tie(user_id: str, local_date: str, role: str, ids: Iterable[str]) -> str:
    raw = "|".join((user_id, local_date, role, *sorted(ids)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_OCCASION_TERMS = {
    "everyday": ("casual", "daily", "comfortable", "relaxed"),
    "work": ("work", "office", "tailored", "smart", "formal", "structured"),
    "meeting": ("meeting", "work", "office", "tailored", "smart", "formal"),
    "office": ("office", "work", "tailored", "smart", "formal", "structured"),
    "evening": ("evening", "elegant", "formal", "dress", "statement"),
    "date": ("date", "elegant", "evening", "romantic"),
    "formal": ("formal", "tailored", "suit", "dress", "blazer"),
    "travel": ("travel", "comfortable", "relaxed", "cotton", "linen"),
    "sport": ("sport", "active", "performance", "breathable", "sneaker"),
    "special occasion": ("formal", "elegant", "statement", "dress", "tailored"),
}
_CLIMATE_TERMS = {
    "hot_humid": {
        "positive": ("breathable", "linen", "cotton", "lightweight", "airy", "light"),
        "negative": ("wool", "fleece", "heavy", "thick", "thermal"),
    },
    "hot_dry": {
        "positive": ("breathable", "linen", "cotton", "lightweight", "airy", "light"),
        "negative": ("wool", "fleece", "heavy", "thick", "thermal"),
    },
    "cool": {
        "positive": ("wool", "knit", "sweater", "fleece", "jacket", "coat", "layered"),
        "negative": ("sleeveless", "shorts", "linen", "lightweight"),
    },
    "temperate": {"positive": (), "negative": ()},
}


def _context_terms(value: str | None, mapping: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    normalized = _normalise(value)
    for key, terms in mapping.items():
        if normalized == key or key in normalized:
            return terms
    return ()


def _score(
    items: list[dict[str, Any]],
    role: str,
    style_signals: tuple[str, ...],
    occasion: str | None = None,
    climate: str | None = None,
) -> int:
    text = " ".join(_item_text(item) for item in items)
    score = sum(3 for term in _ROLE_TERMS[role] if term in text)

    # Only explicit occasion/climate values and item metadata are used. These
    # are transparent ranking hints, not weather forecasts or fit predictions.
    occasion_terms = _context_terms(occasion, _OCCASION_TERMS)
    score += sum(5 for term in occasion_terms if term in text)

    climate_key = _normalise(climate or "").replace(" ", "_")
    climate_rules = _CLIMATE_TERMS.get(climate_key, {"positive": (), "negative": ()})
    score += sum(3 for term in climate_rules["positive"] if term in text)
    score -= sum(3 for term in climate_rules["negative"] if term in text)

    # USI attributes are explicit positive fashion preference strings; they
    # are ranking hints only and never inferred traits or hard exclusions.
    score += sum(2 for signal in style_signals if signal and signal.split(":", 1)[-1] in text)
    return score


def build_daily_looks(
    *,
    request_id: str,
    user_id: str,
    wardrobe_items: list[dict[str, Any]],
    local_date: str,
    occasion: str | None = None,
    climate: str | None = None,
    style_signals: Iterable[str] = (),
) -> dict[str, Any]:
    """Build exactly three distinct look roles from verified wardrobe records."""
    if not request_id.strip() or not user_id.strip():
        raise ValueError("request_id and user_id are required")
    if len(wardrobe_items) > 150:
        raise ValueError("wardrobe snapshot exceeds 150 items")

    seen: set[str] = set()
    active: list[dict[str, Any]] = []
    for item in wardrobe_items:
        if not isinstance(item, dict):
            raise ValueError("wardrobe item must be an object")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("wardrobe item id is required")
        if item.get("owner_user_id") != user_id:
            raise PermissionError("wardrobe item belongs to another subject")
        if item_id in seen:
            raise ValueError("duplicate wardrobe item id")
        seen.add(item_id)
        if item.get("status") != "active":
            continue
        if not isinstance(item.get("display_name"), str) or not isinstance(item.get("category"), str):
            raise ValueError("active wardrobe item is missing display name or category")
        attributes = item.get("attributes", [])
        if not isinstance(attributes, list) or any(not isinstance(x, str) for x in attributes):
            raise ValueError("wardrobe item attributes must be a list of strings")
        # Explicit allowlist: do not pass image asset IDs or storage metadata.
        active.append({
            "item_id": item_id,
            "display_name": item["display_name"],
            "category": item["category"],
            "attributes": attributes,
        })

    classified: dict[str, list[dict[str, Any]]] = {
        "top": [], "bottom": [], "one_piece": [], "footwear": [],
        "outerwear": [], "accessory": [],
    }
    for item in active:
        kind = _kind(item)
        if kind:
            classified[kind].append(item)

    candidates: list[list[dict[str, Any]]] = []
    candidates.extend([[item] for item in classified["one_piece"]])
    for top in classified["top"]:
        for bottom in classified["bottom"]:
            candidates.append([top, bottom])
            if len(candidates) >= 500:
                break
        if len(candidates) >= 500:
            break

    signals = tuple(_normalise(value) for value in style_signals if isinstance(value, str) and value.strip())[:40]
    selected_base: set[frozenset[str]] = set()
    selected_item_ids: set[str] = set()
    looks: list[dict[str, Any]] = []
    context = {
        "occasion": occasion.strip() if isinstance(occasion, str) and occasion.strip() else None,
        "climate": climate.strip() if isinstance(climate, str) and climate.strip() else None,
    }

    for role in ROLES:
        available = [candidate for candidate in candidates
                     if frozenset(x["item_id"] for x in candidate) not in selected_base]
        if not available:
            missing = (
                ["a top and a bottom, or a one-piece outfit"]
                if not candidates else ["additional wardrobe pieces for a distinct outfit"]
            )
            looks.append({
                "role": role,
                "status": "needs_input",
                "item_ids": [],
                "items": [],
                "missing": missing,
                "reason": "There are not enough distinct complete outfit combinations in the active wardrobe yet.",
                "virtual_twin_preview": {
                    "status": "unavailable",
                    "reason_code": "PERSISTENT_TWIN_AND_VALIDATED_RENDERER_NOT_READY",
                },
            })
            continue

        candidate = max(
            available,
            key=lambda group: (
                _score(group, role, signals, occasion, climate),
                -sum(len(set(x["item_id"] for x in group) & selected_item_ids) for _ in (0,)),
                _stable_tie(user_id, local_date, role, (x["item_id"] for x in group)),
            ),
        )
        base_ids = frozenset(x["item_id"] for x in candidate)
        selected_base.add(base_ids)
        chosen = list(candidate)
        used = {x["item_id"] for x in chosen}

        # Add one complementary item from a different category, when available.
        optional_kinds = ("footwear", "outerwear", "accessory")
        optional_candidates: list[dict[str, Any]] = []
        for kind in optional_kinds:
            pool = [x for x in classified[kind] if x["item_id"] not in used]
            if pool:
                optional_candidates.append(max(
                    pool,
                    key=lambda x: (
                        _score([x], role, signals, occasion, climate),
                        _stable_tie(user_id, local_date, role, [x["item_id"]]),
                    ),
                ))
        # Footwear is helpful but not required; add no more than one optional item
        # to keep the first slice conservative and avoid over-completing a look.
        if optional_candidates:
            optional = max(
                optional_candidates,
                key=lambda x: (
                    _score([x], role, signals),
                    _stable_tie(user_id, local_date, role, [x["item_id"]]),
                ),
            )
            chosen.append(optional)
            used.add(optional["item_id"])

        selected_item_ids.update(used)
        looks.append({
            "role": role,
            "status": "ready",
            "item_ids": [x["item_id"] for x in chosen],
            "items": chosen,
            "missing": [],
            "reason": {
                "everyday": "A practical combination assembled from active wardrobe items.",
                "elevated": "A more polished combination assembled from active wardrobe items and declared context.",
                "explore": "A distinct alternative assembled from active wardrobe items; no new purchases are required.",
            }[role],
            "context": context,
            "virtual_twin_preview": {
                "status": "unavailable",
                "reason_code": "PERSISTENT_TWIN_AND_VALIDATED_RENDERER_NOT_READY",
            },
        })

    ready_count = sum(look["status"] == "ready" for look in looks)
    return {
        "schema_version": "1.0",
        "policy_version": POLICY_VERSION,
        "request_id": request_id,
        "capability": "tari_daily_looks",
        "status": "ready" if ready_count == 3 else ("partial" if ready_count else "needs_input"),
        "look_count": 3,
        "ready_count": ready_count,
        "looks": looks,
        "personalization": {
            "style_signals_used": bool(signals),
            "source": "consented_usi_profile" if signals else "no_persisted_style_signals",
            "durable_learning_performed": False,
        },
        "limits": [
            "Looks use only active, owner-scoped wardrobe item records.",
            "The three roles are distinct outfit combinations, not a fit or purchase guarantee.",
            "No body, face, culture, gender, religion or modesty attribute is inferred.",
            "Virtual Twin preview is unavailable until persistent Twin ownership, consent and a validated renderer are integrated.",
            "Marketplace candidates, prices, stock and product-display authorization are not part of this response.",
        ],
    }

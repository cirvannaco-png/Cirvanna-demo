"""Preference-led colour coordination across clothing, makeup and accessories."""
from __future__ import annotations

from typing import Any

HARMONIES = {
    "navy": ("mustard", "terracotta", "soft ivory"),
    "blue": ("coral", "warm orange", "camel"),
    "cobalt": ("soft orange", "cream", "silver"),
    "teal": ("coral", "warm cream", "copper"),
    "emerald": ("blush", "champagne", "plum"),
    "forest green": ("dusty rose", "warm ivory", "burgundy"),
    "olive": ("burgundy", "cream", "dusty rose"),
    "sage": ("soft plum", "warm ivory", "terracotta"),
    "burgundy": ("sage", "soft gold", "blush"),
    "plum": ("butter yellow", "soft grey", "ivory"),
    "lavender": ("sage", "butter yellow", "deep plum"),
    "pink": ("chocolate brown", "olive", "soft grey"),
    "coral": ("teal", "navy", "warm cream"),
    "red": ("camel", "navy", "soft pink"),
    "rust": ("teal", "cream", "deep olive"),
    "terracotta": ("teal", "cream", "deep brown"),
    "mustard": ("navy", "plum", "cream"),
    "cream": ("forest green", "burgundy", "cobalt"),
    "beige": ("teal", "forest green", "terracotta"),
    "brown": ("turquoise", "cream", "copper"),
    "black": ("emerald", "cobalt", "soft ivory"),
    "white": ("cobalt", "emerald", "burgundy"),
    "grey": ("berry", "mustard", "teal"),
    "charcoal": ("cobalt", "copper", "soft ivory"),
}


def _clean(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = " ".join(str(raw).strip().casefold().split())
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def coordinate_colours(preferences: dict[str, Any], look: dict[str, Any]) -> dict[str, Any]:
    clothing = _clean(look.get("outfit_colors"))
    makeup_current = _clean(look.get("makeup_colors"))
    jewellery_current = _clean(look.get("jewellery_colors"))
    accessories_current = _clean(look.get("accessory_colors"))
    favourites = _clean(preferences.get("favorite_colors"))
    avoided = set(_clean(preferences.get("avoid_colors")))
    base = clothing[0] if clothing else (favourites[0] if favourites else None)

    preferred_accents = [c for c in favourites if c not in avoided and c not in clothing]
    curated = [c for c in HARMONIES.get(base or "", ()) if c not in avoided]
    accents = (preferred_accents or curated)[:2]

    makeup_favourites = [c for c in _clean(preferences.get("favorite_makeup_colors")) if c not in avoided]
    jewellery_favourites = [c for c in _clean(preferences.get("favorite_jewellery_colors")) if c not in avoided]
    accessory_favourites = [c for c in _clean(preferences.get("favorite_accessory_colors")) if c not in avoided]

    return {
        "clothing": {
            "base_colors": clothing or ([base] if base else []),
            "accent_options": accents,
            "reason": (
                "The accent options use colours you have saved and exclude colours you asked to avoid."
                if preferred_accents else
                f"The options are conventional palette pairings for {base}; use them as optional directions."
                if accents else
                "Add an outfit colour or a preferred colour to create a grounded palette."
            ),
        },
        "makeup": {
            "current_colors": makeup_current,
            "suggested_directions": makeup_favourites[:2] or accents,
            "reason": (
                "Makeup directions follow your saved shade preferences."
                if makeup_favourites else
                "These are optional colour-harmony directions, not a complexion or undertone assessment."
                if accents else
                "No makeup shade is assumed; add colours you enjoy to personalise this part."
            ),
        },
        "jewellery": {
            "current_colors": jewellery_current,
            "suggested_directions": jewellery_favourites[:2] or accents,
            "preferred_metals": _clean(preferences.get("preferred_metals")),
            "reason": "Jewellery colours and metals should repeat or deliberately contrast with the chosen outfit palette.",
        },
        "accessories": {
            "current_colors": accessories_current,
            "suggested_directions": accessory_favourites[:2] or accents,
            "reason": "Accessory colours are coordinated with the outfit palette while respecting saved exclusions.",
        },
        "excluded_colors_respected": sorted(avoided),
        "evidence_boundary": "No skin tone, undertone or facial feature is inferred from an image by this service.",
    }

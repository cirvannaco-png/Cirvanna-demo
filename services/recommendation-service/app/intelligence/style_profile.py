"""Orthogonal, user-declared style dimensions for PNELLY composition.

The dimensions are intentionally independent: cultural expression, personal
aesthetic, occasion, personal preferences and regional context can be combined
without collapsing the user into a single fashion category.
"""
from __future__ import annotations

from typing import Any


def _values(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return list(dict.fromkeys(
        " ".join(item.strip().split())
        for item in value
        if isinstance(item, str) and item.strip()
    ))


def compose_style_profile(preferences: dict[str, Any], look: dict[str, Any]) -> dict[str, Any]:
    """Return independent style axes; never infer an omitted dimension."""
    cultural = _values(preferences.get("cultural_contexts"))
    aesthetics = _values(preferences.get("aesthetics"))
    occasion = look.get("occasion") if isinstance(look.get("occasion"), str) else None
    personal = {
        "favourite_colours": _values(preferences.get("favorite_colors")),
        "excluded_colours": _values(preferences.get("avoid_colors")),
        "silhouettes": _values(preferences.get("preferred_silhouettes")),
        "materials": _values(preferences.get("preferred_materials")),
        "patterns": _values(preferences.get("preferred_patterns")),
        "coverage_requirements": _values(preferences.get("coverage_requirements")),
    }
    regional = {
        "market_country_code": preferences.get("regional_market"),
        "declared_location": look.get("location") if isinstance(look.get("location"), str) else None,
        "climate": look.get("climate") if isinstance(look.get("climate"), str) else None,
    }
    dimensions = {
        "cultural_expression": {"status": "selected" if cultural else "not_selected", "values": cultural},
        "personal_aesthetic": {"status": "selected" if aesthetics else "not_selected", "values": aesthetics},
        "occasion": {"status": "selected" if occasion else "not_selected", "value": occasion},
        "personal_preferences": {
            "status": "selected" if any(personal.values()) else "not_selected",
            **personal,
        },
        "regional_context": {
            "status": "selected" if any(regional.values()) else "not_selected",
            **regional,
        },
    }
    return {
        "schema_version": "1.0",
        "dimensions": dimensions,
        "composition_policy": "orthogonal_dimensions",
        "inference_policy": "explicit_user_selection_only",
        "explanation": (
            "PNELLY combines only the dimensions supplied by the user. "
            "An omitted dimension remains unspecified and does not constrain the look."
        ),
    }

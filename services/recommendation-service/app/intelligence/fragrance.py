"""Fragrance direction from declared scent preferences and use context."""
from __future__ import annotations

from typing import Any


def compose_fragrance(preferences: dict[str, Any], look: dict[str, Any]) -> dict[str, Any]:
    families = list(dict.fromkeys(preferences.get("favorite_fragrance_families") or []))
    profiles = list(dict.fromkeys(preferences.get("preferred_scent_profiles") or []))
    sensitive = bool(preferences.get("fragrance_sensitive") or preferences.get("fragrance_free"))

    if sensitive:
        return {
            "status": "fragrance_free",
            "families": [],
            "scent_profiles": [],
            "occasion": None,
            "longevity_preference": None,
            "budget": None,
            "intensity": "none",
            "reason": "Your fragrance-free or sensitivity setting takes priority over every style suggestion.",
            "product_claim_boundary": "No allergy-safety or hypoallergenic claim is made.",
        }

    if not families and not profiles:
        return {
            "status": "needs_input",
            "families": [],
            "scent_profiles": [],
            "occasion": None,
            "longevity_preference": None,
            "budget": None,
            "reason": "Choose scent families or scent profiles you enjoy; no preference is inferred.",
        }

    occasions = list(dict.fromkeys(preferences.get("fragrance_occasions") or []))
    requested_occasion = look.get("occasion")
    if requested_occasion and requested_occasion in {
        "daily", "work", "evening", "formal", "date", "travel", "sport", "special_occasion"
    } and requested_occasion not in occasions:
        occasions.append(requested_occasion)

    budget = None
    if preferences.get("fragrance_budget_minor") is not None:
        budget = {
            "maximum_minor_units": preferences["fragrance_budget_minor"],
            "currency": preferences.get("fragrance_budget_currency"),
        }

    intensity = preferences.get("fragrance_intensity") or ("light" if look.get("climate") == "hot_humid" else "moderate")

    return {
        "status": "ready",
        "families": families[:3],
        "scent_profiles": profiles[:3],
        "occasion": occasions[:3],
        "longevity_preference": preferences.get("fragrance_longevity") or "any",
        "budget": budget,
        "intensity": intensity,
        "reason": (
            "The scent direction is constrained by your selected families, scent profiles, occasion and budget. "
            "Longevity is a target preference; actual wear time varies by formula, skin, climate and application."
        ),
        "product_claim_boundary": "A specific perfume's longevity, price and availability must come from verified catalogue or merchant data.",
    }

"""Backward-compatible facade for the modular Complementer intelligence domains."""
from __future__ import annotations

from typing import Any

from app.intelligence.accessories import compose_accessories
from app.intelligence.aesthetic import compose_aesthetic, complete_existing_look
from app.intelligence.colour import coordinate_colours
from app.intelligence.fragrance import compose_fragrance

CONTRACT_VERSION = "2.0.0"


def compose_complementary_look(payload: dict[str, Any]) -> dict[str, Any]:
    """Coordinate one look from explicit preferences and user-supplied context."""
    preferences = payload["preferences"]
    look = payload["look"]

    colours = coordinate_colours(preferences, look)
    fragrance = compose_fragrance(preferences, look)
    accessories = compose_accessories(preferences, look)
    aesthetic_result = compose_aesthetic(preferences)

    # Preserve the v1 response key while expanding it into domain-level colour advice.
    palette = {
        "status": "ready" if colours["clothing"]["base_colors"] and colours["clothing"]["accent_options"] else "needs_input",
        "base_colors": colours["clothing"]["base_colors"],
        "accent_colors": colours["clothing"]["accent_options"],
        "reason": colours["clothing"]["reason"],
    }
    ready_aesthetics = [item for item in aesthetic_result["directions"] if item.get("status") == "ready"]
    first_aesthetic = ready_aesthetics[0] if ready_aesthetics else None
    aesthetic = {
        "status": "ready" if first_aesthetic else "needs_input",
        "direction": (
            f'{first_aesthetic["style"].replace("_", " ").title()} — {first_aesthetic["direction"]}.'
            if first_aesthetic else None
        ),
        "finishing_note": first_aesthetic.get("finishing_note") if first_aesthetic else (
            "Choose the mood you want the look to express."
        ),
        "reason": first_aesthetic["reason"] if first_aesthetic else (
            "No aesthetic or cultural context has been inferred."
        ),
        "directions": aesthetic_result["directions"],
    }

    completion = complete_existing_look(
        preferences, look, colours, fragrance, accessories
    )
    next_inputs: list[str] = []
    if palette["status"] != "ready":
        next_inputs.append("current outfit colours or favourite colours")
    if fragrance["status"] == "needs_input":
        next_inputs.append("preferred fragrance families or scent profiles")
    if aesthetic["status"] != "ready":
        next_inputs.append("one or more preferred aesthetics")
    if accessories["glasses"]["status"] == "needs_input":
        next_inputs.append("optional glasses style or self-reported face shape")

    return {
        "schema_version": "2.0",
        "contract_version": CONTRACT_VERSION,
        "request_id": payload["request_id"],
        "user_id": payload["user_id"],
        "status": "needs_input" if next_inputs else "ready",
        "palette": palette,
        "colour_coordination": colours,
        "fragrance": fragrance,
        "earrings": accessories["earrings"],
        "necklaces": accessories["necklaces"],
        "glasses": accessories["glasses"],
        "other_accessories": accessories["other_accessories"],
        "aesthetic": aesthetic,
        "look_completion": completion,
        "next_inputs": next_inputs,
        "limits": [
            "These are styling directions, not professional colour analysis or a guarantee of personal preference.",
            "Fragrance longevity is a preference target, not a guarantee of actual wear time; no allergy-safety claim is made.",
            "No gender, culture, religion, modesty, skin tone, undertone or facial feature is inferred from appearance.",
            "Cultural styling is used only when the user explicitly selects the cultural context.",
            "Specific products, brands, SKUs, prices and stock must come from the canonical Catalog/Commerce sources and pass CaTaCaCi/CAL before display.",
        ],
        "persistence": "stateless_request_only",
    }

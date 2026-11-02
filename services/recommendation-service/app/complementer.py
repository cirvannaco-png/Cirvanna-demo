"""Deterministic, preference-led look composition for Complementer v1."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "1.0.0"

COLOR_COMPLEMENTS = {
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

AESTHETICS = {
    "minimalist": ("clean, edited and intentional", "keep one focal accent and let the silhouette breathe"),
    "classic": ("polished and timeless", "repeat one metal or colour detail for a pulled-together finish"),
    "romantic": ("soft and expressive", "use gentle contrast and a delicate or fluid finishing detail"),
    "bold": ("confident and high-contrast", "choose one statement element rather than competing focal points"),
    "bohemian": ("relaxed and textured", "combine tactile materials with a restrained colour anchor"),
    "streetwear": ("graphic and relaxed", "use one crisp shape or hardware detail to sharpen the look"),
    "editorial": ("considered and directional", "build around one deliberate contrast in colour, shape or texture"),
    "natural": ("understated and easy", "keep the palette close and use texture instead of extra ornament"),
}

NECKLINE_EARRINGS = {
    "high": ("stud", "huggie", "compact hoop"),
    "crew": ("stud", "huggie", "compact hoop"),
    "collared": ("stud", "huggie", "small geometric drop"),
    "v_neck": ("slim drop", "small hoop", "elongated geometric"),
    "strapless": ("drop", "sculptural statement", "hoop"),
    "off_shoulder": ("drop", "sculptural statement", "hoop"),
    "scoop": ("hoop", "drop", "stud"),
    "unknown": ("stud", "small hoop", "drop"),
}


def _clean(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result, seen = [], set()
    for raw in values or []:
        value = " ".join(str(raw).strip().casefold().split())
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def compose_complementary_look(payload: dict[str, Any]) -> dict[str, Any]:
    """Return explainable style directions from explicit preferences and look context."""
    prefs, look = payload["preferences"], payload["look"]
    aesthetics = _clean(prefs.get("aesthetics"))
    aesthetic_key = aesthetics[0] if aesthetics else None
    aesthetic_pair = AESTHETICS.get(aesthetic_key or "")

    outfit = _clean(look.get("outfit_colors"))
    favourites = _clean(prefs.get("favorite_colors"))
    avoided = set(_clean(prefs.get("avoid_colors")))
    base = outfit[0] if outfit else (favourites[0] if favourites else None)
    preferred_accents = [c for c in favourites if c not in avoided and c not in outfit]
    curated = [c for c in COLOR_COMPLEMENTS.get(base or "", ()) if c not in avoided]
    accents = preferred_accents[:2] if preferred_accents else curated[:2]
    palette_ready = bool(base and accents)
    palette = {
        "status": "ready" if palette_ready else "needs_input",
        "base_colors": [base] if base else [],
        "accent_colors": accents,
        "reason": (
            "Accents come from your stated favourites and respect your exclusions."
            if preferred_accents else
            f"Curated harmony options for {base}; treat them as choices, not rules."
            if accents else
            "Share your current outfit colours or favourite colours for a grounded palette."
        ),
    }

    families = _clean(prefs.get("favorite_fragrance_families"))
    if prefs.get("fragrance_sensitive") or prefs.get("fragrance_free"):
        fragrance = {
            "status": "fragrance_free", "families": [], "intensity": "none",
            "direction": "Skip perfume and keep the look fragrance-free.",
            "reason": "Your stated preference takes precedence over occasion or aesthetic suggestions.",
        }
    elif families:
        intensity = prefs.get("fragrance_intensity") or (
            "light" if look.get("climate") == "hot_humid" else "moderate"
        )
        fragrance = {
            "status": "ready", "families": families[:2], "intensity": intensity,
            "direction": "Explore the scent families you selected; sample before choosing a full-size product.",
            "reason": "Scent direction follows your declared preferences; none is inferred.",
        }
    else:
        fragrance = {
            "status": "needs_input", "families": [], "intensity": None, "direction": None,
            "reason": "Choose scent families you enjoy, or select fragrance-free; no scent preference is assumed.",
        }

    if prefs.get("earrings_preference") == "avoid":
        earrings = {
            "status": "omitted_by_preference", "shape": None, "metal": None,
            "direction": "No earrings suggested.", "reason": "Your no-earrings preference is respected.",
        }
    else:
        neckline = look.get("neckline", "unknown")
        hairstyle = look.get("hairstyle", "unknown")
        shapes = _clean(prefs.get("preferred_earring_shapes"))
        options = list(NECKLINE_EARRINGS.get(neckline, NECKLINE_EARRINGS["unknown"]))
        if hairstyle in {"up", "short"} and neckline in {"v_neck", "strapless", "off_shoulder", "scoop"}:
            options = ["drop", "sculptural statement", "hoop", "stud"]
        shape = shapes[0] if shapes else options[0]
        metals = _clean(prefs.get("preferred_metals"))
        metal = metals[0] if metals else "coordinate with the metal already worn"
        earrings = {
            "status": "ready", "shape": shape, "metal": metal,
            "direction": f"Try {shape} earrings in {metal}.",
            "reason": "Your selected earring preference takes priority; neckline and hairstyle are secondary context.",
        }

    next_inputs = []
    if not palette_ready:
        next_inputs.append("current outfit colours or favourite colours")
    if fragrance["status"] == "needs_input":
        next_inputs.append("preferred fragrance families or fragrance-free choice")
    if not aesthetic_pair:
        next_inputs.append("one or more preferred aesthetics")

    if aesthetic_pair:
        finish, detail = aesthetic_pair
        aesthetic = {
            "status": "ready",
            "direction": f"{aesthetic_key.title()} — {finish}.",
            "finishing_note": detail,
            "reason": "This direction follows the aesthetic you selected.",
        }
    else:
        aesthetic = {
            "status": "needs_input", "direction": None,
            "finishing_note": "Choose the mood you want the look to express.",
            "reason": "No aesthetic has been inferred.",
        }

    return {
        "schema_version": "1.0", "contract_version": CONTRACT_VERSION,
        "request_id": payload["request_id"], "user_id": payload["user_id"],
        "status": "needs_input" if next_inputs else "ready",
        "palette": palette, "fragrance": fragrance,
        "earrings": earrings, "aesthetic": aesthetic, "next_inputs": next_inputs,
        "limits": [
            "These are styling directions, not professional colour analysis or a guarantee of personal preference.",
            "No fragrance is described as allergy-safe or hypoallergenic; this service does not diagnose allergies.",
            "No brand, SKU, price, stock, product benefit or purchase link is generated.",
            "Specific catalog products must be retrieved from Catalog and pass Cirvanna's existing decision/display controls before being shown.",
        ],
        "persistence": "stateless_request_only",
    }

"""Curated, explainable dress-code guidance for PNELLY occasion styling.

This module explains public fashion aesthetics; it never infers identity or
replaces the user's declared preferences and hard exclusions.
"""
from __future__ import annotations

import re
from typing import Any


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[_-]+", " ", value.casefold()).split())


THEME_PROFILES: dict[str, dict[str, Any]] = {
    "old_money": {
        "label": "Old money",
        "aliases": ("old money", "old-money", "heritage luxury", "classic country club"),
        "explanation": (
            "An understated, heritage-inspired look: timeless tailoring, refined fabrics, "
            "careful fit and quiet details rather than visible logos or flashy status symbols. "
            "It is a style reference, not a statement about anyone's wealth or background."
        ),
        "palette": ["navy", "cream", "ivory", "camel", "beige", "chocolate brown", "white", "muted green", "burgundy"],
        "fabrics": ["cotton", "linen", "wool", "cashmere", "silk", "tweed"],
        "silhouettes": ["tailored trousers", "crisp shirts", "knitwear", "structured blazers", "simple dresses", "classic skirts"],
        "finishing": ["loafers or polished flats", "a simple leather belt", "understated watch", "small jewellery", "structured bag"],
        "avoid": ["large visible logos", "neon colour blocking", "excessive embellishment", "overly distressed pieces"],
        "ranking_terms": ["classic", "tailored", "elegant", "preppy", "linen", "cotton", "knitwear", "navy", "cream", "beige", "neutral", "loafers", "leather", "wool", "silk", "tweed", "white", "brown"],
        "look_directions": {
            "everyday": "Relaxed heritage",
            "elevated": "Classic tailoring",
            "explore": "Polished evening",
        },
    },
    "quiet_luxury": {
        "label": "Quiet luxury",
        "aliases": ("quiet luxury", "stealth wealth"),
        "explanation": "A restrained, modern approach built around excellent fit, simple shapes, tactile fabrics and a coordinated palette rather than prominent branding.",
        "palette": ["black", "white", "cream", "stone", "taupe", "navy", "charcoal"],
        "fabrics": ["cotton", "linen", "wool", "silk", "leather"],
        "silhouettes": ["clean tailoring", "straight-leg trousers", "simple knitwear", "minimal dresses"],
        "finishing": ["minimal leather accessories", "simple jewellery", "clean footwear"],
        "avoid": ["prominent logos", "busy embellishment", "clashing statement pieces"],
        "ranking_terms": ["minimal", "classic", "tailored", "clean", "neutral", "linen", "cotton", "wool", "silk", "leather", "black", "white", "cream", "navy"],
        "look_directions": {"everyday": "Relaxed minimal", "elevated": "Clean tailoring", "explore": "Soft statement"},
    },
    "black_tie": {
        "label": "Black tie",
        "aliases": ("black tie", "black-tie"),
        "explanation": "A formal evening dress code. It usually calls for a tuxedo or a floor-length/elegant evening dress, refined shoes and restrained accessories; check the invitation for local or event-specific guidance.",
        "palette": ["black", "midnight navy", "white", "deep jewel tones"],
        "fabrics": ["wool", "silk", "satin", "velvet"],
        "silhouettes": ["tuxedo tailoring", "evening gown", "formal long dress"],
        "finishing": ["formal shoes", "small evening bag", "polished jewellery"],
        "avoid": ["casual denim", "sportswear", "everyday sneakers"],
        "ranking_terms": ["formal", "evening", "tailored", "suit", "tuxedo", "gown", "dress", "satin", "silk", "velvet", "black", "navy"],
        "look_directions": {"everyday": "Formal foundation", "elevated": "Evening classic", "explore": "Statement formal"},
    },
    "cocktail": {
        "label": "Cocktail attire",
        "aliases": ("cocktail", "cocktail attire", "cocktail dress code"),
        "explanation": "Polished party attire that sits between business formal and black tie: a cocktail dress, elegant separates or a tailored suit with dress shoes and considered accessories.",
        "palette": ["black", "navy", "jewel tones", "cream", "metallic accents"],
        "fabrics": ["silk", "satin", "crepe", "velvet", "fine cotton"],
        "silhouettes": ["knee-length or midi dress", "tailored separates", "smart suit"],
        "finishing": ["dress shoes", "small bag", "one focal accessory"],
        "avoid": ["beachwear", "sportswear", "overly casual denim"],
        "ranking_terms": ["evening", "formal", "elegant", "dress", "tailored", "silk", "satin", "crepe", "velvet", "heels", "clutch"],
        "look_directions": {"everyday": "Polished party", "elevated": "Cocktail classic", "explore": "Evening statement"},
    },
}


def resolve_theme(occasion: str | None) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(occasion, str) or not occasion.strip():
        return None
    normalized = _normalise(occasion)
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for key, profile in THEME_PROFILES.items():
        for alias in profile["aliases"]:
            candidate = _normalise(alias)
            if candidate == normalized or candidate in normalized:
                matches.append((len(candidate), key, profile))
    if not matches:
        return None
    _, key, profile = max(matches, key=lambda item: item[0])
    return key, profile


def build_theme_guide(occasion: str | None) -> dict[str, Any] | None:
    resolved = resolve_theme(occasion)
    if resolved is None:
        return None
    key, profile = resolved
    return {
        "status": "recognized",
        "theme_id": key,
        "label": profile["label"],
        "explanation": profile["explanation"],
        "palette": list(profile["palette"]),
        "fabrics": list(profile["fabrics"]),
        "silhouettes": list(profile["silhouettes"]),
        "finishing": list(profile["finishing"]),
        "avoid": list(profile["avoid"]),
        "look_directions": dict(profile["look_directions"]),
        "source": "curated_style_knowledge",
        "purchase_required": False,
    }


def theme_ranking_signals(occasion: str | None) -> list[str]:
    resolved = resolve_theme(occasion)
    if resolved is None:
        return []
    key, profile = resolved
    return [f"theme:{key}", *(f"style:{term}" for term in profile["ranking_terms"])]

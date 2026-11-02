"""Expanded, identity-preserving personal aesthetic composition for Complementer v2.

This module produces advisory directions only. It does not retrieve products,
infer personal identity, or authorize marketplace display.
"""
from __future__ import annotations

from typing import Any

from app.complementer import compose_complementary_look

AESTHETIC_DIRECTIONS = {
    "elegant": ("refined and composed", "repeat one finish or metal and keep the silhouette uncluttered"),
    "cultural": ("rooted in the style context you selected", "use only the motifs, materials or dress conventions you explicitly chose"),
    "sporty": ("functional and energetic", "keep the practical anchor and add one coordinated accent"),
    "professional": ("considered and work-appropriate", "keep the existing structure and use one restrained finishing detail"),
    "artsy": ("expressive and individual", "let one intentional colour, shape or texture carry the look"),
    "vintage": ("character-led and nostalgic", "combine one vintage focal piece with a cleaner supporting element"),
    "glam": ("polished and expressive", "choose one high-impact finish and keep the other details coordinated"),
}

NECKLACE_BY_NECKLINE = {
    "high": ("short chain", "keep the neckline clean; use a visible pendant only if it is a signature piece"),
    "crew": ("short pendant or collar-length chain", "a compact necklace follows the neckline without competing with it"),
    "collared": ("fine chain or short pendant", "leave the collar as the structure and use a restrained layer"),
    "v_neck": ("pendant or lariat", "a vertical line echoes the neckline"),
    "strapless": ("collar or short statement necklace", "the open neckline can carry one clear focal point"),
    "off_shoulder": ("collar or delicate pendant", "a close-set line follows the exposed neckline"),
    "scoop": ("rounded pendant or short layered chain", "a curved line echoes the neckline"),
    "unknown": ("simple chain", "a restrained chain is a low-commitment starting point"),
}

MAKEUP_BY_UNDERTONE = {
    "warm": ("terracotta", "warm rose", "soft bronze"),
    "cool": ("berry", "mauve", "soft plum"),
    "neutral": ("rose", "soft bronze", "muted berry"),
    "olive": ("rosewood", "copper", "muted plum"),
}

FRAME_DIRECTIONS = {
    "round": ("angular or geometric", "a defined edge adds contrast to the round frame of the face you selected"),
    "oval": ("soft-square or geometric", "both structured and rounded silhouettes are useful options to compare"),
    "square": ("rounded or softly curved", "a softer frame shape contrasts with the angular shape you selected"),
    "heart": ("lightweight oval or subtle lower-rim emphasis", "a lighter lower half can balance the frame shape you selected"),
    "unknown": ("choose from your preferred frame shapes", "face-shape matching is not assumed; your stated preference leads"),
}


def _clean(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = " ".join(str(raw).strip().casefold().split())
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _choice(values: list[str], fallback: str) -> str:
    return values[0] if values else fallback


def compose_personal_aesthetic(payload: dict[str, Any]) -> dict[str, Any]:
    """Coordinate fragrance, colour, jewellery and aesthetic from declared inputs."""
    prefs, look = payload["preferences"], payload["look"]
    baseline = compose_complementary_look(payload)
    chosen_aesthetics = _clean(prefs.get("aesthetics"))
    aesthetic_key = chosen_aesthetics[0] if chosen_aesthetics else None

    # Fragrance preferences are parameters, not claims about product performance.
    fragrance = dict(baseline["fragrance"])
    fragrance.update({
        "preferred_notes": _clean(prefs.get("preferred_scent_notes"))[:8],
        "occasion": look.get("occasion"),
        "projection_preference": prefs.get("fragrance_projection"),
        "longevity_preference": prefs.get("fragrance_longevity"),
        "budget": (
            {"amount_minor": prefs.get("fragrance_budget_minor"),
             "currency": prefs.get("fragrance_budget_currency")}
            if prefs.get("fragrance_budget_minor") is not None else None
        ),
        "performance_claim": None,
    })
    if fragrance["status"] == "ready":
        fragrance["reason"] = (
            "Family and notes come from your declared scent preferences; occasion, "
            "projection, longevity and budget are treated as selection filters, not guarantees."
        )

    # Colour advice is split by use so one palette is not blindly applied everywhere.
    base_colors = baseline["palette"]["base_colors"]
    accent_colors = baseline["palette"]["accent_colors"]
    makeup_colors = _clean(prefs.get("preferred_makeup_colors"))[:4]
    undertone = prefs.get("self_described_undertone")
    if not makeup_colors and undertone in MAKEUP_BY_UNDERTONE:
        makeup_colors = list(MAKEUP_BY_UNDERTONE[undertone])
        makeup_reason = (
            f"These are optional colour directions based on the undertone you selected ({undertone}); "
            "they are not a skin analysis or a product-suitability claim."
        )
    elif makeup_colors:
        makeup_reason = "These colours come directly from your makeup preferences."
    else:
        makeup_reason = "Choose makeup colours you enjoy or optionally provide a self-described undertone."

    metal = _choice(_clean(prefs.get("preferred_metals")), "coordinate with your existing jewellery")
    colour_intelligence = {
        "clothing": {
            "base": base_colors,
            "accents": accent_colors,
            "reason": baseline["palette"]["reason"],
        },
        "makeup": {
            "colours": makeup_colors,
            "reason": makeup_reason,
            "status": "ready" if makeup_colors else "needs_input",
        },
        "jewellery": {
            "metals": [metal] if metal else [],
            "colour_echo": accent_colors[:1],
            "reason": "The metal follows your stated preference; one accent can repeat a colour already in the outfit.",
        },
        "accessories": {
            "colour_direction": accent_colors[:2],
            "reason": "Repeat one existing outfit accent rather than adding an unrelated new colour.",
        },
    }

    # Earrings use the v1 precedence rules.
    earrings = baseline["earrings"]

    # Necklace direction respects a no-necklace instruction and uses neckline only as secondary context.
    if prefs.get("necklace_preference") == "avoid":
        necklace = {
            "status": "omitted_by_preference", "shape": None, "metal": None,
            "reason": "Your no-necklace preference is respected.",
        }
    else:
        preferred = _clean(prefs.get("preferred_necklace_shapes"))
        shape, why = NECKLACE_BY_NECKLINE.get(look.get("neckline", "unknown"), NECKLACE_BY_NECKLINE["unknown"])
        selected_shape = _choice(preferred, shape)
        necklace = {
            "status": "ready",
            "shape": selected_shape,
            "metal": metal,
            "reason": (
                "Your selected necklace style takes priority over neckline guidance."
                if preferred else why
            ),
        }

    # Glasses styling is optional. Never require face-shape inference or a photograph.
    if prefs.get("glasses_preference") == "avoid":
        glasses = {
            "status": "omitted_by_preference", "frame_direction": None,
            "reason": "Your no-glasses preference is respected.",
        }
    else:
        frame_shapes = _clean(prefs.get("preferred_frame_shapes"))
        face_shape = prefs.get("self_described_face_shape") or "unknown"
        direction, why = FRAME_DIRECTIONS.get(face_shape, FRAME_DIRECTIONS["unknown"])
        glasses = {
            "status": "ready" if frame_shapes or face_shape != "unknown" else "needs_input",
            "frame_direction": frame_shapes[:2] if frame_shapes else direction,
            "reason": "Your preferred frame shapes take priority." if frame_shapes else why,
        }

    other = _clean(prefs.get("preferred_finishing_accessories"))[:6]
    accessories = {
        "selected_items": other,
        "status": "ready" if other else "needs_input",
        "reason": (
            "These finishing pieces are drawn from your selected accessory interests."
            if other else
            "Choose which accessory types you actually wear; no bag, scarf, belt or watch is assumed."
        ),
    }

    # Cultural styling is only available from an explicitly selected style context.
    cultural_tags = _clean(prefs.get("user_declared_cultural_style_tags"))
    if aesthetic_key == "cultural" and not cultural_tags:
        aesthetic = {
            "status": "needs_input",
            "direction": "Choose the cultural style, tradition or design references you want included.",
            "reason": "Cirvanna does not infer cultural identity or affiliation.",
            "cultural_context_used": False,
        }
    elif aesthetic_key:
        finish, detail = AESTHETIC_DIRECTIONS.get(
            aesthetic_key,
            (baseline["aesthetic"].get("direction") or aesthetic_key, baseline["aesthetic"].get("finishing_note") or ""),
        )
        aesthetic = {
            "status": "ready",
            "direction": f"{aesthetic_key.replace('_', ' ').title()} — {finish}.",
            "finishing_note": detail,
            "reason": (
                "This direction uses only the cultural style references you selected."
                if aesthetic_key == "cultural" else
                "This direction follows the aesthetic you selected."
            ),
            "cultural_context_used": aesthetic_key == "cultural",
        }
    else:
        aesthetic = baseline["aesthetic"]

    # Make the smallest useful intervention by default; preserve user-selected anchors.
    additions = []
    if accent_colors:
        additions.append({"area": "colour", "suggestion": f"Repeat {accent_colors[0]} once as an accent.", "reason": "It connects to your stated palette."})
    if earrings.get("status") == "ready":
        additions.append({"area": "earrings", "suggestion": earrings.get("direction"), "reason": earrings.get("reason")})
    if necklace.get("status") == "ready":
        additions.append({"area": "necklace", "suggestion": necklace.get("shape"), "reason": necklace.get("reason")})
    if other:
        additions.append({"area": "accessories", "suggestion": ", ".join(other), "reason": accessories["reason"]})
    look_completion = {
        "strategy": "minimal_change",
        "preserve": {
            "existing_outfit_colours": _clean(look.get("outfit_colors")),
            "selected_aesthetics": chosen_aesthetics,
            "existing_signature_items": _clean(look.get("signature_items")),
            "silhouette": "preserve_unless_user_requests_change",
        },
        "suggestions": additions,
        "reason": "The goal is to complete the look with the fewest useful changes, not replace the user's identity or existing style.",
    }

    return {
        "schema_version": "2.0",
        "contract_version": "2.0.0",
        "request_id": payload["request_id"],
        "user_id": payload["user_id"],
        "status": "needs_input" if (
            baseline["status"] == "needs_input"
            or colour_intelligence["makeup"]["status"] == "needs_input"
            or accessories["status"] == "needs_input"
            or aesthetic["status"] == "needs_input"
        ) else "ready",
        "fragrance": fragrance,
        "colour_intelligence": colour_intelligence,
        "jewellery": {"earrings": earrings, "necklace": necklace, "glasses": glasses},
        "accessories": accessories,
        "aesthetic": aesthetic,
        "look_completion": look_completion,
        "limits": [
            "Advice is based on declared preferences and supplied context; it is not a judgement of appearance.",
            "Undertone and face shape are optional self-descriptions, never inferred by this service.",
            "No cultural identity or affiliation is inferred; cultural references must be explicitly selected.",
            "Fragrance longevity and projection are preferences, not guarantees about a product.",
            "No brand, SKU, price, stock, safety, skin-health or product-performance claim is created.",
            "Specific products must come from Catalog and pass the existing CaTaCaCi/CAL display gate.",
        ],
        "persistence": "profile_hydration_and_feedback_storage_not_yet_integrated",
    }

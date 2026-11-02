"""Aesthetic direction and conservative look-completion suggestions."""
from __future__ import annotations

from typing import Any

AESTHETICS = {
    "minimalist": ("clean, edited and intentional", "Keep one focal accent and let the silhouette breathe."),
    "elegant": ("refined and composed", "Repeat one material, metal or colour detail for a deliberate finish."),
    "classic": ("polished and timeless", "Choose durable shapes and repeat one quiet detail."),
    "romantic": ("soft and expressive", "Use gentle contrast and a delicate or fluid finishing detail."),
    "bold": ("confident and high-contrast", "Choose one statement element rather than competing focal points."),
    "streetwear": ("graphic and relaxed", "Use one crisp shape or hardware detail to sharpen the look."),
    "editorial": ("considered and directional", "Build around one deliberate contrast in colour, shape or texture."),
    "natural": ("understated and easy", "Keep the palette close and use texture instead of extra ornament."),
    "bohemian": ("relaxed and textured", "Combine tactile materials with a restrained colour anchor."),
    "cultural": ("rooted in a context you choose", "Use only the cultural references, craft traditions or styling cues you explicitly select."),
}


def compose_aesthetic(preferences: dict[str, Any]) -> dict[str, Any]:
    selected = list(dict.fromkeys(preferences.get("aesthetics") or []))
    if not selected:
        return {"status": "needs_input", "directions": [],
                "reason": "Choose the aesthetic you want to express; no identity or style is inferred."}
    contexts = list(dict.fromkeys(preferences.get("cultural_contexts") or []))
    directions = []
    for key in selected[:3]:
        if key == "cultural" and not contexts:
            directions.append({
                "style": key, "status": "needs_input",
                "reason": "Cultural styling is opt-in. Select the specific context or references you want included.",
            })
            continue
        finish, note = AESTHETICS[key]
        directions.append({
            "style": key, "status": "ready", "direction": finish, "finishing_note": note,
            "cultural_contexts": contexts[:5] if key == "cultural" else [],
            "reason": "This direction follows the style you selected; it does not define or replace your identity.",
        })
    return {"status": "ready" if any(d["status"] == "ready" for d in directions) else "needs_input",
            "directions": directions}


def complete_existing_look(preferences: dict[str, Any], look: dict[str, Any],
                           colour_result: dict[str, Any], fragrance_result: dict[str, Any],
                           accessory_result: dict[str, Any]) -> dict[str, Any]:
    suggestions = []
    if look.get("outfit_colors") and not look.get("accessory_colors"):
        accent = (colour_result.get("clothing", {}).get("accent_options") or [])
        if accent:
            suggestions.append({
                "addition": f"Consider one {accent[0]} accent through an accessory.",
                "reason": "It connects the current outfit palette without replacing the clothes or changing the overall direction.",
                "optional": True,
            })
    if accessory_result.get("earrings", {}).get("status") == "ready" and not look.get("jewellery_current_style"):
        shape = accessory_result["earrings"].get("shape")
        if shape:
            suggestions.append({
                "addition": f"Consider {shape} earrings as a single finishing detail.",
                "reason": "It adds a focal point while keeping the rest of the look intact.",
                "optional": True,
            })
    if fragrance_result.get("status") == "ready" and not preferences.get("fragrance_occasions"):
        suggestions.append({
            "addition": "Set the fragrance occasion before choosing a specific scent.",
            "reason": "The same scent profile can feel different in work, daytime and evening settings.",
            "optional": True,
        })
    return {
        "keep": ["The user's chosen silhouette, identity and existing statement pieces."],
        "suggestions": suggestions[:2],
        "principle": "Improve the look with the smallest useful adjustment; never treat personal identity as a defect to correct.",
    }

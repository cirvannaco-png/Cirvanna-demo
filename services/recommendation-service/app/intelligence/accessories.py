"""Accessory coordination using explicit preferences and current-look context."""
from __future__ import annotations

from typing import Any

EARRING_BY_NECKLINE = {
    "high": ("stud", "huggie", "compact hoop"),
    "crew": ("stud", "huggie", "compact hoop"),
    "collared": ("stud", "huggie", "small geometric drop"),
    "v_neck": ("slim drop", "small hoop", "elongated geometric"),
    "strapless": ("drop", "sculptural statement", "hoop"),
    "off_shoulder": ("drop", "sculptural statement", "hoop"),
    "scoop": ("hoop", "drop", "stud"),
    "unknown": ("stud", "small hoop", "drop"),
}
GLASSES_BY_FACE_SHAPE = {
    "round": ("square", "rectangular", "geometric"),
    "square": ("round", "oval", "soft cat-eye"),
    "oval": ("round", "square", "cat_eye", "aviator"),
    "heart": ("oval", "round", "lightweight rectangular"),
    "oblong": ("oversized", "round", "deep rectangular"),
}


def _clean(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(" ".join(str(v).strip().casefold().split()) for v in (values or []) if str(v).strip()))


def compose_accessories(preferences: dict[str, Any], look: dict[str, Any]) -> dict[str, Any]:
    shapes = _clean(preferences.get("preferred_earring_shapes"))
    if preferences.get("earrings_preference") == "avoid":
        earrings = {"status": "omitted_by_preference", "shape": None, "metal": None,
                    "reason": "You asked not to receive earring suggestions."}
    else:
        options = EARRING_BY_NECKLINE.get(look.get("neckline", "unknown"), EARRING_BY_NECKLINE["unknown"])
        if look.get("hairstyle") in {"up", "short"} and look.get("neckline") in {"v_neck", "strapless", "off_shoulder", "scoop"}:
            options = ("drop", "sculptural statement", "hoop")
        shape = shapes[0] if shapes else options[0]
        metals = _clean(preferences.get("preferred_metals"))
        earrings = {
            "status": "ready", "shape": shape,
            "alternatives": list(options[:3]),
            "metal": metals[0] if metals else None,
            "reason": "Your chosen earring style and metal lead; neckline and hairstyle only refine the options.",
        }

    necklace_styles = _clean(preferences.get("preferred_necklace_styles"))
    if preferences.get("necklace_preference") == "avoid":
        necklaces = {"status": "omitted_by_preference", "styles": [],
                     "reason": "You asked not to receive necklace suggestions."}
    elif necklace_styles:
        necklaces = {"status": "ready", "styles": necklace_styles[:3],
                     "reason": "These necklace styles come directly from your saved preferences."}
    elif look.get("neckline") in {"high", "crew", "collared"}:
        necklaces = {"status": "optional", "styles": ["short pendant", "delicate chain"],
                     "reason": "A short, low-profile necklace can sit neatly with this neckline; skip it if you prefer a clean neckline."}
    else:
        necklaces = {"status": "needs_input", "styles": [],
                     "reason": "No necklace preference is assumed; choose whether you want a necklace direction."}

    if preferences.get("glasses_preference") == "avoid":
        glasses = {"status": "omitted_by_preference", "shapes": [],
                   "reason": "You asked not to receive glasses suggestions."}
    else:
        preferred = _clean(preferences.get("preferred_glasses_shapes"))
        face_shape = preferences.get("self_reported_face_shape")
        contextual = list(GLASSES_BY_FACE_SHAPE.get(face_shape or "", ()))
        if preferred:
            shapes_out = preferred[:3]
            why = "Your selected frame shapes take priority."
        elif contextual:
            shapes_out = contextual[:3]
            why = "These are optional frame-shape contrasts based only on the face shape you chose to report."
        else:
            shapes_out = []
            why = "No face-shape assumption is made; select a frame style or optionally describe your face shape."
        glasses = {"status": "ready" if shapes_out else "needs_input", "shapes": shapes_out, "reason": why}

    other = [v for v in _clean(preferences.get("preferred_accessories"))
             if v not in set(_clean(preferences.get("avoid_accessory_categories")))]
    return {
        "earrings": earrings,
        "necklaces": necklaces,
        "glasses": glasses,
        "other_accessories": {
            "preferred_categories": other[:5],
            "reason": "Only accessory categories you selected are included; explicit exclusions take precedence.",
        },
    }

"""Pure scoring functions for outfit compatibility."""
from __future__ import annotations

from common.domain import ColorVector


def color_score(a: dict, b: dict) -> float:
    sa, sb = a.get("surface_properties"), b.get("surface_properties")
    if not sa or not sb:
        return 0.5
    c1 = ColorVector.from_dict(sa["dominant_color"])
    c2 = ColorVector.from_dict(sb["dominant_color"])
    return 1.0 - min(1.0, c1.distance_to(c2) / 100.0)


def fit_score(a: dict, b: dict) -> float:
    ga, gb = a.get("geometry_profile"), b.get("geometry_profile")
    if not ga or not gb:
        return 0.5
    score = 0.5
    if ga["silhouette_class"] == gb["silhouette_class"]:
        score += 0.3
    v1, v2 = ga["volume_distribution"], gb["volume_distribution"]
    sim = 1.0 - sum(abs(x - y) for x, y in zip(v1, v2)) / 2.0
    score += sim * 0.2
    return min(1.0, score)


def style_score(a: dict, b: dict) -> float:
    ra = set(a.get("category_constraints", {}).get("secondary_roles", []))
    rb = set(b.get("category_constraints", {}).get("secondary_roles", []))
    if not ra or not rb:
        return 0.5
    overlap = len(ra & rb) / max(len(ra | rb), 1)
    return 0.5 + overlap * 0.4


def occasion_score(a: dict, b: dict) -> float:
    aa = set(a.get("wearability_context", {}).get("activity_affinity", []))
    ab = set(b.get("wearability_context", {}).get("activity_affinity", []))
    if not aa or not ab:
        return 0.5
    return 0.5 + (len(aa & ab) / max(len(aa), len(ab))) * 0.4


def compute_outfit_scores(a: dict, b: dict) -> dict[str, float]:
    return {
        "color": color_score(a, b),
        "fit": fit_score(a, b),
        "style": style_score(a, b),
        "occasion": occasion_score(a, b),
    }

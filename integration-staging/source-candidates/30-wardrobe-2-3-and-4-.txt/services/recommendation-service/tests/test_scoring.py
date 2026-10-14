from __future__ import annotations

from app.scoring import compute_outfit_scores


def test_scores_within_bounds() -> None:
    a = {"surface_properties": {"dominant_color": {"l": 50, "a": 0, "b": 0}}}
    b = {"surface_properties": {"dominant_color": {"l": 60, "a": 5, "b": 5}}}
    scores = compute_outfit_scores(a, b)
    assert all(0.0 <= v <= 1.0 for v in scores.values())

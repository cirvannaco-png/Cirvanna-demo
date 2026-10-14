from __future__ import annotations

import datetime as dt

from common.domain import IngestionMethod, PrimaryCategory, WardrobeObject
from app.conflict_resolver import resolve


def test_lww_newer_wins() -> None:
    a = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    b = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    b.id = a.id
    a.last_updated = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    b.last_updated = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    b.total_wears = 5
    winner = resolve(a, b)
    assert winner is b


def test_merges_confidence() -> None:
    a = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    b = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
    a.confidence_envelope.geometry_confidence = 0.5
    b.confidence_envelope.geometry_confidence = 0.7
    winner = resolve(a, b)
    assert winner.confidence_envelope.geometry_confidence == 0.7

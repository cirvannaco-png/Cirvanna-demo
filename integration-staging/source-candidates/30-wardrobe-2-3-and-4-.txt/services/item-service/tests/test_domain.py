"""Unit tests for pure domain logic (no I/O)."""
from __future__ import annotations

import pytest

from common.domain import (
    ColorVector,
    ConfidenceEnvelope,
    EventType,
    GeometryProfile,
    IngestionMethod,
    LifecycleState,
    PrimaryCategory,
    RegretSignals,
    SilhouetteClass,
    TemporalValue,
    WardrobeObject,
)


class TestColorVector:
    def test_rgb_to_lab_black(self):
        c = ColorVector.from_rgb(0, 0, 0)
        assert c.l == 0
        assert -1 < c.a < 1 and -1 < c.b < 1

    def test_rgb_to_lab_white(self):
        c = ColorVector.from_rgb(255, 255, 255)
        assert c.l == pytest.approx(100, abs=1)
        assert abs(c.a) < 1 and abs(c.b) < 1

    def test_hex_roundtrip(self):
        c = ColorVector.from_hex("#ff8800")
        r, g, b = c.to_rgb()
        assert (r, g, b) == (255, 136, 0)

    def test_distance_identity(self):
        a = ColorVector.from_rgb(100, 100, 100)
        b = ColorVector.from_rgb(100, 100, 100)
        assert a.distance_to(b) == pytest.approx(0.0, abs=1e-6)

    def test_serialization(self):
        c = ColorVector.from_rgb(50, 100, 150)
        c2 = ColorVector.from_dict(c.to_dict())
        assert c2.l == c.l and c2.a == c.a and c2.b == c.b


class TestTemporalValue:
    def test_smoothing(self):
        tv = TemporalValue(current=0.0, smoothing_factor=0.5)
        tv.update(1.0)
        assert tv.current == 1.0
        tv.update(1.0)
        assert tv.current == pytest.approx(1.0)

    def test_decay(self):
        tv = TemporalValue(current=1.0)
        tv.apply_decay(0.9)
        assert tv.current == pytest.approx(0.9)

    def test_trend_flat(self):
        tv = TemporalValue()
        for _ in range(5):
            tv.update(0.5)
        assert tv.get_trend() == pytest.approx(0.0, abs=1e-6)


class TestConfidenceEnvelope:
    def test_ceiling_enforced(self):
        env = ConfidenceEnvelope(ingestion_method=IngestionMethod.MANUAL)
        env.update(geometry_confidence=0.99)
        assert env.geometry_confidence <= 0.35

    def test_overall_is_min(self):
        env = ConfidenceEnvelope(ingestion_method=IngestionMethod.CAMERA)
        env.update(
            geometry_confidence=0.5,
            surface_confidence=0.3,
            category_confidence=0.55,
            context_confidence=0.5,
        )
        assert env.overall_confidence == 0.3

    def test_decay(self):
        env = ConfidenceEnvelope(
            geometry_confidence=1.0,
            surface_confidence=1.0,
            category_confidence=1.0,
            context_confidence=1.0,
        )
        env.decay(30)
        assert env.geometry_confidence < 1.0


class TestWardrobeObject:
    def test_creation(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
        assert o.owner_id == "u1"
        assert o.lifecycle_state == LifecycleState.PROVISIONAL

    def test_wear_increases_confidence(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP, 0.2)
        before = o.confidence_envelope.overall_confidence
        o.record_wear_event(accepted=True, duration_estimate=120)
        assert o.confidence_envelope.overall_confidence >= before
        assert o.total_wears == 1 and o.successful_wears == 1

    def test_rejection_accumulates_regret(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
        o.record_wear_event(accepted=False, duration_estimate=10)
        assert o.regret_signals.get_weighted_regret() > 0

    def test_lifecycle_transition(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP, 0.2)
        for _ in range(5):
            o.record_wear_event(accepted=True, duration_estimate=120)
        assert o.lifecycle_state in (LifecycleState.ACTIVE_LEARNING, LifecycleState.STABLE)

    def test_retire(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
        o.retire()
        assert o.lifecycle_state == LifecycleState.RETIRED
        assert not o.get_safe_for_exploration()

    def test_serialization_roundtrip(self):
        o = WardrobeObject("u1", IngestionMethod.CAMERA, PrimaryCategory.BOTTOM, 0.15)
        o.record_wear_event(accepted=True, duration_estimate=60)
        d = o.to_dict()
        o2 = WardrobeObject.from_dict(d)
        assert o2.id == o.id
        assert o2.total_wears == 1
        assert o2.ingestion_method == IngestionMethod.CAMERA

    def test_catalog_metadata_size_guard(self):
        o = WardrobeObject("u1", IngestionMethod.MANUAL, PrimaryCategory.TOP)
        with pytest.raises(ValueError):
            o.catalog_metadata = {"data": "x" * 200_000}

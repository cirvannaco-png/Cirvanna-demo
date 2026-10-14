from __future__ import annotations

import random

import numpy as np
import pytest

from app.imperfection_engine import ImperfectionEngine


def test_meta_fields_present() -> None:
    engine = ImperfectionEngine(
        noise_level=0.05,
        rng=random.Random(42),
        np_rng=np.random.default_rng(42),
    )
    scores, meta = engine.process({"color": 0.8, "fit": 0.7, "style": 0.6, "occasion": 0.5})
    assert set(scores) == {"color", "fit", "style", "occasion"}
    assert {"confidence", "risk_level", "dominant_strength", "dominant_weakness"} <= meta.keys()
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_deterministic_with_seed() -> None:
    e1 = ImperfectionEngine(rng=random.Random(1), np_rng=np.random.default_rng(1))
    e2 = ImperfectionEngine(rng=random.Random(1), np_rng=np.random.default_rng(1))
    s1, _ = e1.process({"color": 0.5, "fit": 0.5, "style": 0.5, "occasion": 0.5})
    s2, _ = e2.process({"color": 0.5, "fit": 0.5, "style": 0.5, "occasion": 0.5})
    assert s1 == s2

"""Unit tests for perception (mock heavy model loading)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app import perception


@pytest.mark.asyncio
async def test_analyze_returns_expected_keys(monkeypatch) -> None:
    fake_img = Image.new("RGB", (64, 64), color=(120, 80, 200))
    fake_bytes = MagicMock()
    fake_bytes.content = b""

    # Skip actual model loading
    monkeypatch.setattr(perception, "CLIPPerception", lambda: None)

    # This is a structural smoke test — full inference tests run in integration
    assert hasattr(perception, "SIL_CLASSES")
    assert hasattr(perception, "TEX_CLASSES")
    assert len(perception.SIL_CLASSES) == 5
    assert len(perception.TEX_CLASSES) == 5

"""Compatibility import shim; PNELLY owns canonical route contracts."""
from __future__ import annotations

import sys
from pathlib import Path

canonical_root = Path(__file__).resolve().parents[2] / "pnelly"
sys.path.insert(0, str(canonical_root))
from pnelly import routing as canonical_routing  # noqa: E402

sys.modules[__name__] = canonical_routing

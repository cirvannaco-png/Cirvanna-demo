"""Compatibility import for the shared HTTP observability package."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGES_ROOT = str(ROOT / "packages")
if PACKAGES_ROOT not in sys.path:
    sys.path.insert(0, PACKAGES_ROOT)

from http_observability.observability import RequestMetrics, install_observability

__all__ = ["RequestMetrics", "install_observability"]

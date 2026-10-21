"""Cirvanna API-gateway application package.

Register the repository's domain-package roots before importing any gateway
module. This keeps existing contract composition importable both in tests and
when the gateway is launched from its own service directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for package_path in (
    ROOT / "packages" / "identity-intelligence",
    ROOT / "packages" / "preferences",
    ROOT / "packages" / "fit-intelligence",
):
    resolved = str(package_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

from .decision_pipeline import DecisionPipelineResult, arbitrate_candidate  # noqa: E402

__all__ = ["DecisionPipelineResult", "arbitrate_candidate"]

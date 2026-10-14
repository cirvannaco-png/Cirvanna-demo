"""
CDIC v5.0 - Canonical Decision & Identity Core
Unified high-performance, production-ready engine.
"""

__version__ = "5.0.0"

from .core.engine import CDICEngine
from .config import CDICConfig

__all__ = ["CDICEngine", "CDICConfig"]

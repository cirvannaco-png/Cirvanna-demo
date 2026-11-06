"""Compatibility import shim; canonical runtime lives in services/pnelly."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

xari_service_root = Path(__file__).resolve().parents[1]
canonical_root = xari_service_root.parent / "pnelly"
canonical_main = canonical_root / "app" / "main.py"
sys.path.insert(0, str(canonical_root))
spec = importlib.util.spec_from_file_location("_cirvanna_pnelly_runtime", canonical_main)
if spec is None or spec.loader is None:
    raise RuntimeError("Canonical PNELLY runtime could not be loaded")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
sys.modules[__name__] = module

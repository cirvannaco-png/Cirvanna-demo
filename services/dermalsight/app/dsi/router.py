"""Read-only DSI capability surface; inference and profile routes remain gated."""
from __future__ import annotations

from fastapi import APIRouter

from .readiness import dsi_capabilities

router = APIRouter()


@router.get("/api/v1/dsi/capabilities", tags=["dsi", "operations"])
def get_dsi_capabilities() -> dict[str, object]:
    """Expose implemented capability state, not a promise of future inference."""
    return dsi_capabilities()

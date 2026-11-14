"""User-autonomy policy for discovery and cosmetic experimentation.

This module plans optional DSI work. It does not authorize media processing,
verify consent receipts, or persist user preferences.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisReadiness(str, Enum):
    NOT_REQUESTED = "not_requested"
    CONSENT_REQUIRED = "consent_required"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


class DiscoveryRequest(BaseModel):
    """A user's requested exploration, independent of previous preference state."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    requested_direction: str = Field(min_length=1, max_length=240)
    experiments: list[str] = Field(default_factory=list, max_length=24)
    prior_preferences: list[str] = Field(default_factory=list, max_length=64)
    analysis_requested: bool = False
    current_purpose_consent_verified: bool = False
    task_specific_model_ready: bool = False
    explicitly_save_preference: bool = False


class DiscoveryPlan(BaseModel):
    """A non-vetoing plan that preserves the user's chosen direction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_direction: str
    experiments: list[str]
    analysis_readiness: AnalysisReadiness
    discovery_continues: Literal[True] = True
    requested_direction_preserved: Literal[True] = True
    prior_preferences_are_advisory: Literal[True] = True
    dsi_may_veto_user_choices: Literal[False] = False
    automatic_profile_update: Literal[False] = False
    explicit_save_requested: bool = False
    fallback: Literal["non_dsi_discovery", "optional_dsi_analysis"]


def plan_discovery(request: DiscoveryRequest) -> DiscoveryPlan:
    """Keep self-discovery available even when DSI analysis is unavailable.

    The caller must derive consent/model readiness from trusted server-side
    services. These booleans do not themselves authorize image processing.
    A mismatch with prior preferences is deliberately not a denial condition.
    """
    if not request.analysis_requested:
        analysis = AnalysisReadiness.NOT_REQUESTED
    elif not request.current_purpose_consent_verified:
        analysis = AnalysisReadiness.CONSENT_REQUIRED
    elif not request.task_specific_model_ready:
        analysis = AnalysisReadiness.UNAVAILABLE
    else:
        analysis = AnalysisReadiness.AVAILABLE

    return DiscoveryPlan(
        requested_direction=request.requested_direction,
        experiments=list(request.experiments),
        analysis_readiness=analysis,
        explicit_save_requested=request.explicitly_save_preference,
        fallback=(
            "optional_dsi_analysis"
            if analysis == AnalysisReadiness.AVAILABLE
            else "non_dsi_discovery"
        ),
    )

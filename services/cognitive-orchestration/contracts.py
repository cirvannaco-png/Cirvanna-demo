"""Typed contracts for Cirvanna's PAMASMMA-derived cognitive service boundary."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class CognitiveSystem(str, Enum):
    EXECUTIVE_OPERATIONS = "executive_operations"
    MARKETING_INTELLIGENCE = "marketing_intelligence"
    RELATIONSHIP_MANAGEMENT = "relationship_management"
    NARRATIVE_GOVERNANCE = "narrative_governance"
    CREATOR_ECONOMY = "creator_economy"
    AUDIENCE_PSYCHOLOGY = "audience_psychology"
    BEHAVIORAL_CONSISTENCY = "behavioral_consistency"
    PERSUASION_GOVERNANCE = "persuasion_governance"
    VOICE_PRESENCE = "voice_presence"
    STRATEGIC_NARRATIVE = "strategic_narrative"


class CognitiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    system: CognitiveSystem
    context: dict[str, Any]
    priority: str = "normal"
    requester: str = "cirvanna"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CognitiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    system: CognitiveSystem
    action: str
    rationale: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    requires_founder_approval: bool
    estimated_impact: str
    # Optional only when supplied by a calibrated, documented implementation.
    quality_score: float | None = Field(default=None, ge=0, le=10)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

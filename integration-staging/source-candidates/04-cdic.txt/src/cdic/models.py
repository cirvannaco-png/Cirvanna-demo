"""
Data models for CDIC v4.0
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator
from .enums import ResponseType, RiskLevel


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit entry"""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    operation: str = ""
    data_hash: str = ""
    request_id: str = ""
    user_id: str = ""
    session_id: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WDLSignal:
    """Weighted Decision Learning Signal"""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    input_pattern: str = ""
    user_response: ResponseType = ResponseType.DEFAULT
    weight: float = 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    decay_rate: float = 0.1
    trend_impact: float = 0.0
    confidence: float = 1.0
    source: str = "user"


@dataclass
class DecisionOption:
    """Decision option with scoring"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = ""
    confidence: float = 0.0
    rationale: str = ""
    risk_score: float = 0.0
    diversity_score: float = 0.0
    generation_cost: float = 0.0
    doctrine_compliant: bool = True
    doctrine_violations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionContext(BaseModel):
    """Validated decision context"""
    intent: str = Field(..., min_length=1, max_length=200)
    input_snapshot: Dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cultural_context: Optional[str] = None
    coverage_required: bool = False
    exploration_allowed: bool = True
    temporal_scope: str = "session"
    risk_tolerance: RiskLevel = RiskLevel.MEDIUM
    ethical_constraints: List[str] = Field(default_factory=list)
    priority: int = 1
    
    @validator('input_snapshot')
    def sanitize_snapshot(cls, v):
        """Remove potentially dangerous keys"""
        dangerous_patterns = ['__', 'eval', 'exec', 'import', 'open']
        safe_dict = {}
        for key, value in v.items():
            if not any(pattern in str(key).lower() for pattern in dangerous_patterns):
                if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    safe_dict[key] = value
        return safe_dict
    
    @validator('intent')
    def sanitize_intent(cls, v):
        """Sanitize intent string"""
        import re
        return re.sub(r'[^\w\s\-]', '', v)[:100]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Enum: lambda v: v.value
        }
        use_enum_values = True


class CDICResponse(BaseModel):
    """Response from CDIC Engine according to spec 2.1"""
    options: List[DecisionOption]
    confidence: float
    clarification_needed: bool
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Enum: lambda v: v.value
        }
        use_enum_values = True

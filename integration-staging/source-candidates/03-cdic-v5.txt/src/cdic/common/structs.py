import time
import uuid
import json
import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from .enums import QuestionType, ResponseType

# Global prompt cache (populated by create method)
_prompt_cache = {}

@dataclass(slots=True, frozen=True)
class DecisionContext:
    intent: str
    input_hash: int
    user_id: int
    session_id: int
    timestamp: float = field(default_factory=time.time)
    request_id: int = field(default_factory=lambda: uuid.uuid4().int)
    cultural_hash: int = 0
    coverage_flag: bool = False
    exploration_flag: bool = False
    temporal_hash: int = 0
    priority: int = 0
    # Precomputed vector for CTIF (optional, set later)
    vector: Optional[np.ndarray] = None

    @classmethod
    def create(cls, intent: str, input_data: Dict, user_id: str, session_id: str,
               cultural_context: Optional[str] = None, coverage_required: bool = False,
               exploration_allowed: bool = False, temporal_scope: str = "session"):
        """Factory method with hashing."""
        return cls(
            intent=intent,
            input_hash=hash(json.dumps(input_data, sort_keys=True)),
            user_id=hash(user_id) % (2**32),
            session_id=hash(session_id) % (2**32),
            cultural_hash=hash(cultural_context or "") % (2**32),
            coverage_flag=coverage_required,
            exploration_flag=exploration_allowed,
            temporal_hash=hash(temporal_scope) % (2**32)
        )

@dataclass(slots=True)
class ClarificationQuestion:
    question_type: int
    prompt_hash: int
    allowed_responses: Tuple[int, ...]
    persistence: int
    question_id: int
    created_at: float
    response_effects: bytes = b''

    @property
    def prompt(self) -> str:
        return _prompt_cache.get(self.prompt_hash, "Unknown prompt")

    @classmethod
    def create(cls, qtype: QuestionType, prompt: str, responses: List[ResponseType],
               persistence: int, effects: Optional[Dict] = None):
        prompt_hash = hash(prompt)
        _prompt_cache[prompt_hash] = prompt
        return cls(
            question_type=qtype.value,
            prompt_hash=prompt_hash,
            allowed_responses=tuple(r.value for r in responses),
            persistence=persistence,
            question_id=uuid.uuid4().int,
            created_at=time.time(),
            response_effects=pickle.dumps(effects or {})
        )

    def is_valid_response(self, response: int) -> bool:
        return response in self.allowed_responses

@dataclass(slots=True)
class ClarificationResponse:
    question_id: int
    response: int
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    metadata: Optional[Dict] = None

@dataclass(slots=True)
class WDLSSignal:
    signal_id: int
    intent_hash: int
    pattern_hash: int
    response_code: int
    weight: float
    timestamp: float
    decay_rate: float = 0.1
    trend_impact: float = 0.0

    def apply_decay(self, current_time: float) -> float:
        elapsed_days = (current_time - self.timestamp) / 86400.0
        decay_factor = 1.0 / (1.0 + self.decay_rate * elapsed_days)
        self.weight *= decay_factor
        self.timestamp = current_time
        return self.weight

@dataclass(slots=True)
class AuditEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    operation: str = ""
    data_hash: str = ""
    request_id: str = ""
    user_id: str = ""
    session_id: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""
    metadata: Dict = field(default_factory=dict)

"""
Enumerations for CDIC v4.0
"""

from enum import Enum, auto


class QuestionType(Enum):
    COVERAGE = auto()
    CULTURAL = auto()
    EXPLORATION = auto()
    TEMPORAL = auto()
    CONFIDENCE = auto()
    RESOURCE = auto()
    STAKEHOLDER = auto()
    REVERSIBILITY = auto()
    RISK_TOLERANCE = auto()
    ETHICAL = auto()


class ResponseType(Enum):
    YES = auto()
    NO = auto()
    FLEXIBLE = auto()
    EXPLORE = auto()
    CONSERVATIVE = auto()
    SAFE = auto()
    VARIETY = auto()
    DEFAULT = auto()
    TODAY = auto()
    REMEMBER = auto()
    DONT_SAVE = auto()
    PROCEED = auto()
    ABORT = auto()
    AFFECTED = auto()
    UNAFFECTED = auto()
    REVERSIBLE = auto()
    IRREVERSIBLE = auto()
    ASK_LATER = auto()
    DEPENDS = auto()
    DECIDE = auto()


class DecisionStatus(Enum):
    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()

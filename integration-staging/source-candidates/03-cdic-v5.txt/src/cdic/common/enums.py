from enum import IntEnum

class QuestionType(IntEnum):
    COVERAGE = 0
    CULTURAL = 1
    EXPLORATION = 2
    TEMPORAL = 3
    CONFIDENCE = 4
    RESOURCE = 5
    STAKEHOLDER = 6
    REVERSIBILITY = 7

class ResponseType(IntEnum):
    YES = 0
    NO = 1
    FLEXIBLE = 2
    ASK_LATER = 3
    DEPENDS = 4
    EXPLORE = 5
    CONSERVATIVE = 6
    DECIDE = 7
    TODAY = 8
    REMEMBER = 9
    DONT_SAVE = 10
    SAFE = 11
    VARIETY = 12
    DEFAULT = 13
    PROCEED = 14
    ABORT = 15
    AFFECTED = 16
    UNAFFECTED = 17
    REVERSIBLE = 18
    IRREVERSIBLE = 19

class DecisionState(IntEnum):
    INITIAL = 0
    CLARIFICATION_PENDING = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4
    EARLY_EXIT = 5

class HybridResolution(IntEnum):
    CONFLICT = 0
    CONSENSUS = 1
    DOMINANT = 2
    UNDECIDED = 3

class ModestyCompliance(IntEnum):
    NONE = 0
    PARTIAL = 1
    FULL = 2

class TrendAuthority(IntEnum):
    SOFT = 0
    HARD = 1
    IMMUTABLE = 2

class CoverageDeviationLevel(IntEnum):
    ZERO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

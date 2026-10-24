"""Explicit startup registration for the initial deterministic handlers."""
try:
    from .contracts import CognitiveSystem
    from .handlers import HANDLERS
    from .registry import register_handler
except ImportError:
    from contracts import CognitiveSystem
    from handlers import HANDLERS
    from registry import register_handler


def register_initial_handlers() -> None:
    """Register only the four implemented domains; leave other domains unavailable."""
    for system in (
        CognitiveSystem.EXECUTIVE_OPERATIONS,
        CognitiveSystem.RELATIONSHIP_MANAGEMENT,
        CognitiveSystem.NARRATIVE_GOVERNANCE,
        CognitiveSystem.PERSUASION_GOVERNANCE,
    ):
        register_handler(system, HANDLERS[system])

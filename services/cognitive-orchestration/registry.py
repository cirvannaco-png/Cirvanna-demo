"""Fail-closed registry: unconfigured cognitive domains cannot fabricate outcomes."""
from collections.abc import Awaitable, Callable
try:
    from .contracts import CognitiveRequest, CognitiveResponse, CognitiveSystem
except ImportError:  # Supports direct loading in the current monorepo validation harness.
    from contracts import CognitiveRequest, CognitiveResponse, CognitiveSystem

CognitiveHandler = Callable[[CognitiveRequest], Awaitable[CognitiveResponse]]
_handlers: dict[CognitiveSystem, CognitiveHandler] = {}


def register_handler(system: CognitiveSystem, handler: CognitiveHandler) -> None:
    """Register a real, tested implementation during application startup."""
    if system in _handlers:
        raise ValueError(f"handler already registered for {system.value}")
    _handlers[system] = handler


def clear_handlers_for_tests() -> None:
    """Test-only helper. Do not call from production request paths."""
    _handlers.clear()


async def dispatch(request: CognitiveRequest) -> CognitiveResponse:
    handler = _handlers.get(request.system)
    if handler is None:
        raise CognitiveSystemUnavailable(request.system.value)
    return await handler(request)


class CognitiveSystemUnavailable(RuntimeError):
    def __init__(self, system: str) -> None:
        super().__init__(f"Cognitive system '{system}' has no configured implementation")
        self.system = system

"""Circuit breaker with gradual (sliding-scale) traffic restoration."""
from __future__ import annotations

import logging
import random
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SlidingCircuitBreaker:
    """Recovery ramp: 10% → 25% → 50% → 100% on consecutive successes."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        initial_ratio: float = 0.1,
        ramp_factor: float = 2.5,
    ) -> None:
        self.name = name
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.initial_ratio = initial_ratio
        self.ramp_factor = ramp_factor

        self._state = State.CLOSED
        self._failures = 0
        self._last_failure_ts = 0.0
        self._traffic_ratio = 1.0
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    @property
    def traffic_ratio(self) -> float:
        return self._traffic_ratio

    def allow(self) -> bool:
        with self._lock:
            if self._state is State.CLOSED:
                return True
            if self._state is State.OPEN:
                if time.monotonic() - self._last_failure_ts >= self.recovery_timeout:
                    self._state = State.HALF_OPEN
                    self._traffic_ratio = self.initial_ratio
                    logger.info(f"CB {self.name}: OPEN → HALF_OPEN (ratio={self._traffic_ratio})")
                    return random.random() < self._traffic_ratio
                return False
            # HALF_OPEN
            return random.random() < self._traffic_ratio

    def record(self, success: bool) -> None:
        with self._lock:
            if success:
                self._failures = 0
                if self._state is State.HALF_OPEN:
                    self._traffic_ratio = min(1.0, self._traffic_ratio * self.ramp_factor)
                    if self._traffic_ratio >= 1.0:
                        self._state = State.CLOSED
                        logger.info(f"CB {self.name}: HALF_OPEN → CLOSED")
            else:
                self._failures += 1
                if self._state is State.HALF_OPEN:
                    self._state = State.OPEN
                    self._last_failure_ts = time.monotonic()
                    self._traffic_ratio = self.initial_ratio
                    logger.warning(f"CB {self.name}: HALF_OPEN → OPEN")
                elif self._failures >= self.threshold:
                    self._state = State.OPEN
                    self._last_failure_ts = time.monotonic()
                    logger.warning(f"CB {self.name}: CLOSED → OPEN after {self._failures} failures")

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failures": self._failures,
            "traffic_ratio": self._traffic_ratio,
        }

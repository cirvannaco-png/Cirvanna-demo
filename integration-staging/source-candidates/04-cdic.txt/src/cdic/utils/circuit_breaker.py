"""
Circuit breaker pattern implementation
"""

import time
import threading
from typing import Callable, Any


class CircuitBreaker:
    """Smart circuit breaker pattern"""
    
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = 0
        self.lock = threading.RLock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        with self.lock:
            current_state = self._get_state()
            if current_state == "OPEN":
                raise Exception("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except Exception as e:
                self._record_failure()
                raise e
    
    def _get_state(self) -> str:
        """Get current circuit breaker state"""
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.failures = self.failure_threshold // 2
            return self.state
    
    def _record_success(self):
        """Record successful call"""
        with self.lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
    
    def _record_failure(self):
        """Record failed call"""
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"

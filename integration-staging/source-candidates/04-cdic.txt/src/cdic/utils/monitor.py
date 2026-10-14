"""
Performance monitoring utilities
"""

import time
import threading
from typing import Dict, Any
from collections import deque, defaultdict
import numpy as np
import psutil


class PerformanceMonitor:
    """Real-time performance monitoring"""
    
    def __init__(self, engine: 'CDICEngine'):
        self.engine = engine
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.lock = threading.RLock()
        self.start_time = time.time()
    
    def record_metric(self, name: str, value: float):
        """Record a metric"""
        with self.lock:
            self.metrics[name].append((time.time(), value))
    
    def get_percentile(self, name: str, percentile: float) -> float:
        """Get percentile value for a metric"""
        with self.lock:
            values = [v for _, v in self.metrics[name]]
            if not values:
                return 0.0
            return float(np.percentile(values, percentile))
    
    def check_sla_violations(self) -> Dict[str, Any]:
        """Check for SLA violations"""
        sla_checks = {
            "decision_latency_95th": (self.get_percentile("decision_latency", 95) > 1.0),
            "error_rate": (self.engine._get_error_rate() > 0.01),
            "memory_usage": (psutil.Process().memory_percent() > 80.0)
        }
        
        violations = [name for name, violated in sla_checks.items() if violated]
        
        return {
            "violations": violations,
            "requires_intervention": len(violations) > 0,
            "metrics": {
                "uptime": time.time() - self.start_time,
                "active_sessions": len(self.engine.session_data),
                "queue_depth": self.engine._get_queue_depth(),
                "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024
            }
        }

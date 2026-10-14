"""
Real-time performance monitoring and optimization.
"""
import time
from collections import deque
import numpy as np

class RealTimeOptimizer:
    def __init__(self, config):
        self.config = config
        self.metrics_buffer = deque(maxlen=1000)
        self.optimization_history = []
        self.last_optimization = time.time()
        self.optimization_cooldown = 60
        self.thresholds = {
            "p95_response_ms": config.P95_RESPONSE_MS,
            "error_rate": 0.01,
            "cache_hit_rate": 0.7,
            "memory_usage_percent": 80,
        }
        self.system_state = {
            "mode": config.MODE,
            "ml_timeout": config.ML_TIMEOUT_MS,
            "cache_ttl": config.CACHE_TTL_SECONDS,
            "batch_size": config.VECTOR_SIMILARITY_BATCH_SIZE,
        }

    def record_metrics(self, metrics):
        self.metrics_buffer.append({
            **metrics,
            "timestamp": time.time()
        })
        if time.time() - self.last_optimization > self.optimization_cooldown:
            self.analyze_and_optimize()

    def analyze_and_optimize(self):
        if len(self.metrics_buffer) < 100:
            return
        recent_metrics = list(self.metrics_buffer)[-100:]
        p95 = np.percentile([m.get('latency', 0) for m in recent_metrics], 95)
        error_rate = np.mean([m.get('error_rate', 0) for m in recent_metrics])
        cache_hit_rate = np.mean([m.get('cache_hit_rate', 0) for m in recent_metrics])
        optimizations = []
        if p95 > self.thresholds["p95_response_ms"]:
            optimizations.append(self._apply_latency_optimizations(p95))
        if error_rate > self.thresholds["error_rate"]:
            optimizations.append(self._apply_error_optimizations(error_rate))
        if cache_hit_rate < self.thresholds["cache_hit_rate"]:
            optimizations.append(self._apply_cache_optimizations(cache_hit_rate))
        if optimizations:
            self.last_optimization = time.time()

    def _apply_latency_optimizations(self, current_p95):
        optimizations = {}
        new_ml_timeout = max(20, self.system_state["ml_timeout"] - 10)
        if new_ml_timeout != self.system_state["ml_timeout"]:
            self.system_state["ml_timeout"] = new_ml_timeout
            self.config.ML_TIMEOUT_MS = new_ml_timeout
            optimizations["ml_timeout_reduced"] = new_ml_timeout
        new_cache_ttl = min(3600, self.system_state["cache_ttl"] + 60)
        if new_cache_ttl != self.system_state["cache_ttl"]:
            self.system_state["cache_ttl"] = new_cache_ttl
            self.config.CACHE_TTL_SECONDS = new_cache_ttl
            optimizations["cache_ttl_increased"] = new_cache_ttl
        if current_p95 > self.config.MAX_RESPONSE_MS:
            self.system_state["mode"] = "mvp"
            self.config.MODE = "mvp"
            optimizations["mode_switched"] = "mvp"
        return {"type": "latency", "actions": optimizations}

    def _apply_error_optimizations(self, error_rate):
        optimizations = {}
        self.config.ENABLE_CIRCUIT_BREAKERS = True
        new_batch_size = max(10, int(self.system_state["batch_size"] * 0.8))
        if new_batch_size != self.system_state["batch_size"]:
            self.system_state["batch_size"] = new_batch_size
            self.config.VECTOR_SIMILARITY_BATCH_SIZE = new_batch_size
            optimizations["batch_size_reduced"] = new_batch_size
        return {"type": "error_rate", "actions": optimizations}

    def _apply_cache_optimizations(self, cache_hit_rate):
        optimizations = {}
        new_ttl = min(3600, self.system_state["cache_ttl"] + 120)
        if new_ttl != self.system_state["cache_ttl"]:
            self.system_state["cache_ttl"] = new_ttl
            self.config.CACHE_TTL_SECONDS = new_ttl
            optimizations["cache_ttl_increased"] = new_ttl
        if not self.config.ENABLE_PREDICTIVE_LOADING:
            self.config.ENABLE_PREDICTIVE_LOADING = True
            optimizations["predictive_loading_enabled"] = True
        return {"type": "cache", "actions": optimizations}

    def get_system_state(self):
        return {
            **self.system_state,
            "buffer_size": len(self.metrics_buffer),
            "optimizations_applied": len(self.optimization_history),
            "last_optimization": self.last_optimization,
        }

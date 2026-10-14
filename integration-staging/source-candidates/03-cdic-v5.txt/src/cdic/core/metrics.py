import time
import threading
from collections import deque, defaultdict
from ..common.utils import lazy_import

class PerfMetrics:
    def __init__(self, buffer_size: int = 1000):
        self.buffer_size = buffer_size
        self.latency_buffer = deque(maxlen=buffer_size)
        self.error_buffer = deque(maxlen=buffer_size)
        self.counters = defaultdict(int)
        self.gauges = {}
        self.timers = {}

    def start_timer(self, name: str):
        timer_id = f"{name}_{time.perf_counter_ns()}"
        self.timers[timer_id] = time.perf_counter()
        return TimerContext(self, timer_id)

    def stop_timer(self, timer_id: str) -> float:
        if timer_id in self.timers:
            elapsed = time.perf_counter() - self.timers[timer_id]
            self.latency_buffer.append(elapsed * 1000)
            del self.timers[timer_id]
            return elapsed
        return 0.0

    def record_audit_batch(self, size: int):
        self.counters['audit_batches'] += 1
        self.counters['audit_entries'] += size

    def update_gauge(self, name: str, value: float):
        self.gauges[name] = value

    def collect_system_metrics(self):
        try:
            psutil = lazy_import('psutil')
            if psutil:
                self.gauges['cpu_percent'] = psutil.cpu_percent()
                self.gauges['memory_mb'] = psutil.Process().memory_info().rss / 1024 / 1024
                self.gauges['thread_count'] = threading.active_count()
        except:
            pass

    def get_summary(self) -> Dict:
        if not self.latency_buffer:
            return {'empty': True}
        np = lazy_import('numpy')
        latencies = np.array(list(self.latency_buffer))
        return {
            'latency_ms': {
                'mean': float(np.mean(latencies)),
                'p50': float(np.percentile(latencies, 50)),
                'p95': float(np.percentile(latencies, 95)),
                'p99': float(np.percentile(latencies, 99)),
                'max': float(np.max(latencies)),
            },
            'counters': dict(self.counters),
            'gauges': dict(self.gauges),
        }

class TimerContext:
    def __init__(self, metrics: PerfMetrics, timer_id: str):
        self.metrics = metrics
        self.timer_id = timer_id

    def stop(self):
        return self.metrics.stop_timer(self.timer_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

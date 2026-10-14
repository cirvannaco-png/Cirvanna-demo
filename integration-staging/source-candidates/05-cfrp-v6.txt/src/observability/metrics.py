"""
CFRPMetrics – Prometheus metrics.
"""
from prometheus_client import Counter, Histogram, Gauge

class CFRPMetrics:
    def __init__(self):
        self.requests_total = Counter('cfrp_requests_total', 'Total requests',
                                       ['method', 'endpoint', 'status', 'region', 'shard'])
        self.request_duration = Histogram('cfrp_request_duration_seconds', 'Request duration',
                                          ['method', 'endpoint'],
                                          buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
        self.reinforcements_total = Counter('cfrp_reinforcements_total', 'Total reinforcements',
                                            ['signal_type', 'success', 'user_segment'])
        self.confidence_changes = Histogram('cfrp_confidence_changes', 'Confidence change',
                                            buckets=[0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5])
        self.queue_size = Gauge('cfrp_queue_size', 'Queue size', ['actor_id', 'shard'])
        self.active_connections = Gauge('cfrp_active_connections', 'Active connections', ['database', 'region'])
        self.error_budget = Gauge('cfrp_error_budget', 'Error budget', ['slo_name', 'time_window'])
        self.latency_sli = Histogram('cfrp_latency_sli', 'Latency SLI', buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1])
        self.chaos_injections = Counter('cfrp_chaos_injections_total', 'Chaos injections',
                                        ['injection_type', 'component', 'severity'])
        self.bias_alerts = Counter('cfrp_bias_alerts_total', 'Bias alerts',
                                   ['bias_type', 'severity', 'signal_category'])

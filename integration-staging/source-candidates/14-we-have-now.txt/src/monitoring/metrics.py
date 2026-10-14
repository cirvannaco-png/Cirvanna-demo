# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from typing import List, Optional
from uuid import UUID
from src.core.eepl import CandidateItem

request_counter = Counter('eepl_requests_total', 'Total EEPL requests', ['status'])
ranking_latency = Histogram('eepl_ranking_latency_seconds', 'Time to rank items')
fci_fallback_counter = Counter('eepl_fci_fallback_total', 'FCI fallback calls')
ab_experiment_counter = Counter('eepl_ab_experiment', 'A/B experiment assignments', ['experiment', 'variant'])

def track_request(user_id: UUID, status: str):
    request_counter.labels(status=status).inc()

def track_ranking(user_id: UUID, candidates: List[CandidateItem], experiment: Optional[str], variant: Optional[str]):
    # Track metrics per candidate – simplified
    for c in candidates:
        # Gauge for scores
        pass

def track_ab_assignment(experiment: str, variant: str):
    ab_experiment_counter.labels(experiment=experiment, variant=variant).inc()

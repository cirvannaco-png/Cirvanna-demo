# config/config.py
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class Config:
    vector_dimensions: int = 128
    api_keys: Dict[str, Optional[str]] = None
    enable_gpu: bool = False
    gpu_backend: str = "cuda"
    virtual_twin_url: str = "http://virtual-twin:8001"
    marketplace_url: str = "http://marketplace:8002"
    cfrp_url: str = "http://cfrp:8003"
    fci_url: str = "http://fci:8004"
    redis_url: str = "redis://redis:6379/0"
    mlflow_tracking_uri: str = "http://mlflow:5000"

    # EEPL THRESHOLDS
    CONF_THRESHOLD: float = 0.55
    HIGH_ENV_THRESHOLD: float = 0.7
    MAX_ENVIRONMENTAL_INFLUENCE: float = 0.20
    MAX_SEGMENT_INFLUENCE: float = 0.40
    MAX_REVIVAL_BOOST: float = 0.15
    MAX_TOTAL_BOOST: float = 0.25
    CULTURAL_SEVERITY_CAP: float = 0.05
    MAX_SCORE: float = 1.0

    # FEEDBACK
    FEEDBACK_DECAY_LAMBDA: float = 0.1

    # DETERMINISM
    RANKING_SEED: int = 42
    GPU_DETERMINISTIC: bool = True

    # CACHING
    SIMULATION_CACHE_TTL_HOURS: int = 24
    ESV_CACHE_TTL_MINUTES: int = 15
    USER_CACHE_TTL_MINUTES: int = 60
    ITEM_CACHE_TTL_MINUTES: int = 60

    # SEGMENT PRIOR
    SEGMENT_VARIANCE_THRESHOLD: float = 0.3
    SEGMENT_INACTIVITY_DECAY_DAYS: int = 30

    # CIRCUIT BREAKERS
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30

    # A/B TESTING
    AB_EXPERIMENTS: Dict[str, Dict] = None

config = Config()

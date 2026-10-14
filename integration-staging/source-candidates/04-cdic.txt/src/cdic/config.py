"""
Configuration management for CDIC v4.0
"""

import os
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class CDICConfig(BaseModel):
    """Validated configuration for CDIC Engine"""
    
    secret_key: str = Field(..., min_length=32)
    redis_url: str = "redis://localhost:6379/0"
    postgres_url: Optional[str] = None
    max_audit_log_size: int = 100_000
    max_session_age_hours: int = 24
    max_wdls_signals: int = 10_000
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    enable_background_workers: bool = True
    log_level: str = "INFO"
    cache_ttl: int = 300
    max_concurrent_decisions: int = 100
    enable_prometheus: bool = True
    enable_compression: bool = True
    cors_origins: List[str] = ["*"]
    trusted_hosts: List[str] = ["*"]
    
    # New: Clarification fatigue control
    clarification_budget_per_session: int = 2
    
    # New: Decision timeout
    decision_timeout_seconds: float = 30.0
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters")
        return v.encode() if isinstance(v, str) else v


class Config:
    env_file = ".env"
    env_prefix = "CDIC_"


VERSION = "4.0.0"
MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)
DEFAULT_CACHE_TTL = 300
AUDIT_CHUNK_SIZE = 1000

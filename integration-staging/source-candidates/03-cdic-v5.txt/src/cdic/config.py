import os
from typing import List, Optional
from pydantic import BaseSettings, Field, validator

class CDICConfig(BaseSettings):
    secret_key: str = Field(..., env='CDIC_SECRET_KEY', min_length=32)
    redis_url: Optional[str] = Field(None, env='REDIS_URL')
    postgres_url: Optional[str] = Field(None, env='DATABASE_URL')

    max_workers: int = Field(4, env='CDIC_MAX_WORKERS')
    use_gpu: bool = Field(True, env='CDIC_USE_GPU')
    circuit_breaker_threshold: int = Field(5, env='CDIC_CB_THRESHOLD')
    circuit_breaker_timeout: int = Field(60, env='CDIC_CB_TIMEOUT')
    max_session_age_hours: int = Field(24, env='CDIC_SESSION_HOURS')
    rate_limit_requests: int = Field(100, env='CDIC_RATE_LIMIT')
    log_level: str = Field("INFO", env='LOG_LEVEL')
    enable_compression: bool = Field(True, env='CDIC_COMPRESSION')
    enable_prometheus: bool = Field(True, env='CDIC_PROMETHEUS')
    cors_origins: List[str] = Field(["*"], env='CDIC_CORS_ORIGINS')
    trusted_hosts: List[str] = Field(["*"], env='CDIC_TRUSTED_HOSTS')
    api_key_required: bool = Field(False, env='CDIC_API_KEY_REQUIRED')
    api_key: Optional[str] = Field(None, env='CDIC_API_KEY')

    @validator('secret_key', pre=True)
    def validate_secret_key(cls, v):
        if isinstance(v, str) and len(v) < 32:
            raise ValueError('secret_key must be at least 32 characters')
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

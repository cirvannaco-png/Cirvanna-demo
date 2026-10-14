"""Configuration management for all Cirvanna services.

Settings are loaded from environment variables (with `.env` fallback)
via pydantic-settings. Every service imports the same singleton `settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object. Immutable at runtime."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ────────────────────────────────────────
    service_name: str = Field(default="cirvanna", alias="SERVICE_NAME")
    service_namespace: str = Field(default="cirvanna", alias="SERVICE_NAMESPACE")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")

    # ── Service URLs ────────────────────────────────────────────
    item_service_url: str = Field(default="http://localhost:8001", alias="ITEM_SERVICE_URL")
    graph_service_url: str = Field(default="http://localhost:8002", alias="GRAPH_SERVICE_URL")
    recommendation_service_url: str = Field(
        default="http://localhost:8003", alias="RECOMMENDATION_SERVICE_URL"
    )
    perception_service_url: str = Field(
        default="http://localhost:8004", alias="PERCEPTION_SERVICE_URL"
    )
    sync_service_url: str = Field(default="http://localhost:8005", alias="SYNC_SERVICE_URL")

    # ── PostgreSQL ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://cirvanna:cirvanna@localhost:5432/cirvanna",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE", ge=1, le=200)
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW", ge=0, le=100)
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    # ── Redis ───────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_max_connections: int = Field(default=50, alias="REDIS_MAX_CONNECTIONS")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND"
    )

    # ── RabbitMQ ────────────────────────────────────────────────
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost/", alias="RABBITMQ_URL")
    rabbitmq_exchange: str = Field(default="cirvanna.events", alias="RABBITMQ_EXCHANGE")
    rabbitmq_prefetch_count: int = Field(default=10, alias="RABBITMQ_PREFETCH_COUNT", ge=1, le=500)

    # ── Neo4j ───────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(default=SecretStr("password"), alias="NEO4J_PASSWORD")
    neo4j_max_pool_size: int = Field(default=50, alias="NEO4J_MAX_POOL_SIZE", ge=1, le=500)

    # ── Qdrant ──────────────────────────────────────────────────
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="item_embeddings", alias="QDRANT_COLLECTION")
    qdrant_vector_size: int = Field(default=512, alias="QDRANT_VECTOR_SIZE")

    # ── Observability ───────────────────────────────────────────
    otlp_endpoint: str = Field(default="http://localhost:4317", alias="OTLP_ENDPOINT")
    otlp_insecure: bool = Field(default=True, alias="OTLP_INSECURE")

    # ── Security ────────────────────────────────────────────────
    jwt_secret: SecretStr = Field(default=SecretStr("dev-secret"), alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_hours: int = Field(default=24, alias="JWT_EXPIRY_HOURS", ge=1, le=720)
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    circuit_breaker_enabled: bool = Field(default=True, alias="CIRCUIT_BREAKER_ENABLED")

    # ── ML / Perception ─────────────────────────────────────────
    clip_model: str = Field(default="openai/clip-vit-base-patch32", alias="CLIP_MODEL")
    clip_device: Literal["auto", "cpu", "cuda", "mps"] = Field(default="auto", alias="CLIP_DEVICE")
    mlflow_tracking_uri: str = Field(default="http://mlflow:5000", alias="MLFLOW_TRACKING_URI")
    model_artifact_path: str = Field(default="/models", alias="MODEL_ARTIFACT_PATH")

    # ── Business Logic ──────────────────────────────────────────
    max_active_slice: int = Field(default=30, alias="MAX_ACTIVE_SLICE", ge=1, le=1000)
    bootstrap_confidence_min: float = Field(default=0.0, alias="BOOTSTRAP_CONFIDENCE_MIN", ge=0.0, le=1.0)
    bootstrap_confidence_max: float = Field(default=0.2, alias="BOOTSTRAP_CONFIDENCE_MAX", ge=0.0, le=1.0)
    confidence_base_camera: float = Field(default=0.55, alias="CONFIDENCE_BASE_CAMERA", ge=0.0, le=1.0)
    confidence_base_sku_assisted: float = Field(default=0.65, alias="CONFIDENCE_BASE_SKU_ASSISTED", ge=0.0, le=1.0)
    confidence_base_manual: float = Field(default=0.35, alias="CONFIDENCE_BASE_MANUAL", ge=0.0, le=1.0)
    confidence_base_catalog_import: float = Field(default=0.45, alias="CONFIDENCE_BASE_CATALOG_IMPORT", ge=0.0, le=1.0)

    # ── Resilience ──────────────────────────────────────────────
    cb_failure_threshold: int = Field(default=5, alias="CB_FAILURE_THRESHOLD", ge=1, le=100)
    cb_recovery_timeout_seconds: int = Field(default=60, alias="CB_RECOVERY_TIMEOUT_SECONDS", ge=1, le=3600)
    cb_initial_traffic_ratio: float = Field(default=0.1, alias="CB_INITIAL_TRAFFIC_RATIO", gt=0.0, le=1.0)
    sync_batch_size: int = Field(default=100, alias="SYNC_BATCH_SIZE", ge=1, le=1000)
    sync_max_retries: int = Field(default=5, alias="SYNC_MAX_RETRIES", ge=0, le=20)
    sync_retry_backoff_seconds: int = Field(default=30, alias="SYNC_RETRY_BACKOFF_SECONDS", ge=1, le=3600)

    # ────────────────────────────────────────────────────────────
    @field_validator("bootstrap_confidence_max")
    @classmethod
    def _validate_bootstrap_range(cls, v: float, info) -> float:
        min_v = info.data.get("bootstrap_confidence_min", 0.0)
        if v < min_v:
            raise ValueError("BOOTSTRAP_CONFIDENCE_MAX must be >= BOOTSTRAP_CONFIDENCE_MIN")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url_sync(self) -> str:
        """Synchronous variant for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "")

    def confidence_base_map(self) -> dict[str, float]:
        """Return confidence base keyed by IngestionMethod value."""
        return {
            "camera": self.confidence_base_camera,
            "sku_assisted": self.confidence_base_sku_assisted,
            "manual": self.confidence_base_manual,
            "catalog_import": self.confidence_base_catalog_import,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings factory. Use this for dependency injection."""
    return Settings()


# Module-level singleton for convenience
settings = get_settings()

import os
from pydantic_settings import BaseSettings
from typing import Optional

class AISConfig(BaseSettings):
    """AIS Configuration"""

    # Service settings
    service_name: str = "ais"
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # AWS S3
    s3_bucket: str = os.getenv("S3_BUCKET", "cirvanna-meshes")
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")

    # Model paths
    smpl_model_path: str = os.getenv("SMPL_MODEL_PATH", "/models/smpl")
    deeplab_weights_path: str = os.getenv("DEEPLAB_WEIGHTS_PATH", "/models/deeplab")
    movenet_weights_path: str = os.getenv("MOVENET_WEIGHTS_PATH", "/models/movenet")

    # GPU settings
    gpu_enabled: bool = os.getenv("GPU_ENABLED", "false").lower() == "true"
    gpu_device: int = int(os.getenv("GPU_DEVICE", "0"))

    # Performance
    batch_size: int = int(os.getenv("BATCH_SIZE", "4"))
    cache_ttl: int = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "100"))

    # Image preprocessing
    target_image_size: int = 512
    normalize_histogram: bool = True
    enhance_edges: bool = True

    # Confidence thresholds
    tier_a_threshold: float = 1.0  # cm
    tier_b_threshold: float = 2.0  # cm

    # SMPL fitting
    smpl_optimization_steps: int = 100
    smpl_learning_rate: float = 0.01
    silhouette_weight: float = 1.0
    landmark_weight: float = 1.0
    height_weight: float = 0.5

    # Monte Carlo dropout for uncertainty
    mc_dropout_samples: int = 10
    mc_dropout_rate: float = 0.1

    class Config:
        env_file = ".env"
        case_sensitive = False

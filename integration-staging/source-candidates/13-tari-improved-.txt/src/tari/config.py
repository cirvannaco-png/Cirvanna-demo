"""
Unified configuration for Tari V5 (integrated with face/body modules).
"""
import secrets
from dataclasses import dataclass, field
from typing import List, Tuple
from cryptography.fernet import Fernet

@dataclass
class TariConfig:
    # Performance Targets
    MAX_RESPONSE_MS: int = 180
    P95_RESPONSE_MS: int = 150
    CACHE_TTL_SECONDS: int = 300
    DB_POOL_SIZE: int = 20
    CONCURRENCY_LIMIT: int = 1000

    # Hybrid Strategy
    MODE: str = "adaptive"
    MVP_TIMEOUT_MS: int = 50
    ML_TIMEOUT_MS: int = 100
    CONFIDENCE_THRESHOLD: float = 0.75

    # Resource Limits
    MAX_CONCURRENT_ML: int = 10
    MAX_CACHE_SIZE: int = 10000
    MAX_EMBEDDING_DIM: int = 256
    MAX_BATCH_SIZE: int = 500

    # Privacy Settings
    ANONYMIZE_USER_IDS: bool = True
    ENCRYPT_SENSITIVE_DATA: bool = True
    DATA_RETENTION_DAYS: int = 30
    DIFFERENTIAL_PRIVACY_EPSILON: float = 1.0
    MAX_LOG_SIZE_BYTES: int = 100_000_000

    # Feature Flags
    ENABLE_BATCH_PROCESSING: bool = True
    ENABLE_REQUEST_DEDUPLICATION: bool = True
    ENABLE_CIRCUIT_BREAKERS: bool = True
    ENABLE_PREDICTIVE_LOADING: bool = True
    ENABLE_DIFFERENTIAL_PRIVACY: bool = True
    ENABLE_REAL_TIME_OPTIMIZATION: bool = True

    # Dialogue Settings
    MAX_DIALOGUE_HISTORY: int = 100
    TIER_DEPTHS: List[str] = field(default_factory=lambda: ["summary", "detailed", "scientific"])
    EMOTIONAL_MODULATION: bool = True

    # Security Settings
    JWT_SECRET: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    ENCRYPTION_KEY: bytes = field(default_factory=lambda: Fernet.generate_key())
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60

    # Face Analysis Settings
    ENABLE_FACE_ANALYSIS: bool = True
    FACE_DETECTOR_METHOD: str = "mediapipe"  # "mediapipe", "haar", "dnn", "hog"
    FACE_MIN_DETECTION_CONFIDENCE: float = 0.5

    # Body Calibration Settings
    ENABLE_BODY_CALIBRATION: bool = True
    BODY_MIN_FRAMES_FOR_FUSION: int = 2
    BODY_OUTLIER_Z_SCORE: float = 2.5
    BODY_SMOOTHING_WINDOW: int = 5
    BODY_TARGET_FPS: int = 30
    BODY_MAX_MEMORY_MB: int = 200

    # Illumination Profile Settings (from face module)
    FACE_MIN_SIZE_RATIO: float = 0.2
    FACE_MAX_SIZE_RATIO: float = 0.8
    FACE_CENTER_MARGIN: float = 0.2
    EYE_SHADOW_THRESHOLD: float = 15.0
    CHEEK_HIGHLIGHT_THRESHOLD: float = 85.0
    TARGET_EXPOSURE_MEAN: float = 0.5
    SHADOW_THRESHOLD: float = 30.0
    HIGHLIGHT_THRESHOLD: float = 80.0
    GAMMA_CLIP_RANGE: Tuple[float, float] = (0.5, 2.0)

    # ========== Xyra Marketplace + Virtual Try-On Additions ==========
    # Retrieval & Ranking
    MAX_RETRIEVAL_MS: int = 120
    MAX_OUTFIT_GENERATION_MS: int = 250
    MAX_TRYON_QUEUE_DELAY_MS: int = 1000
    MAX_TOTAL_RESPONSE_MS: int = 2200
    VECTOR_DB_TYPE: str = "qdrant"  # qdrant, weaviate, pinecone, faiss
    VECTOR_DB_URL: str = "http://localhost:6333"
    EMBEDDING_MODEL: str = "clip/ViT-B-32"
    RETRIEVAL_TOP_K: int = 200
    FINAL_TOP_K: int = 12
    DIVERSITY_LAMBDA: float = 0.3

    # Outfit Composition
    COMPATIBILITY_WEIGHTS: Tuple[float, float, float, float] = (0.4, 0.3, 0.2, 0.1)
    MAX_OUTFIT_SIZE: int = 6

    # XARI Ranking Weights
    RANKING_SIMILARITY_WEIGHT: float = 0.30
    RANKING_COMPATIBILITY_WEIGHT: float = 0.25
    RANKING_USER_PREFERENCE_WEIGHT: float = 0.20
    RANKING_NOVELTY_WEIGHT: float = 0.10
    RANKING_CONFIDENCE_WEIGHT: float = 0.10
    RANKING_DIVERSITY_WEIGHT: float = 0.05

    # Try-On
    TRYON_ASYNC_QUEUE: str = "redis"  # redis, rabbitmq, kafka, sqs
    TRYON_GPU_WORKERS: int = 4
    TRYON_MODEL: str = "idm-vton"  # idm-vton, catvton, kolors, outfitanyone, ootd
    TRYON_IMAGE_SIZE: Tuple[int, int] = (512, 512)

    # Memory & Knowledge Graph
    ENABLE_FASHION_KNOWLEDGE_GRAPH: bool = True
    KNOWLEDGE_GRAPH_URL: str = "bolt://localhost:7687"
    MEMORY_TIERS: List[str] = field(default_factory=lambda: ["session", "preference", "behavioral", "semantic"])

    # Evaluation & Observability
    ENABLE_DISTRIBUTED_TRACING: bool = True
    TRACING_ENDPOINT: str = "http://localhost:14268/api/traces"
    OFFLINE_EVAL_METRICS: List[str] = field(default_factory=lambda: ["recall@10", "ndcg@10", "mrr"])
    ONLINE_EVAL_EXPERIMENTS: List[str] = field(default_factory=lambda: ["ranking_weights", "diversity_lambda"])

    # Cost Governance
    FREE_TIER_TRYON_RESOLUTION: Tuple[int, int] = (256, 256)
    PREMIUM_TIER_TRYON_RESOLUTION: Tuple[int, int] = (1024, 1024)

    def __post_init__(self):
        assert self.MAX_RESPONSE_MS >= self.MVP_TIMEOUT_MS + self.ML_TIMEOUT_MS + 30, \
            "Timeouts too aggressive for response target"
        assert self.DIFFERENTIAL_PRIVACY_EPSILON > 0, "Epsilon must be positive"
        if self.ENCRYPT_SENSITIVE_DATA:
            self.cipher = Fernet(self.ENCRYPTION_KEY)

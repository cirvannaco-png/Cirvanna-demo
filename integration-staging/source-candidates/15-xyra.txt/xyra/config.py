"""
Unified configuration for Xyra.
"""
import secrets
from dataclasses import dataclass, field
from typing import List, Tuple
from cryptography.fernet import Fernet

@dataclass
class XyraConfig:
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
    FACE_DETECTOR_METHOD: str = "mediapipe"
    FACE_MIN_DETECTION_CONFIDENCE: float = 0.5

    # Body Calibration Settings
    ENABLE_BODY_CALIBRATION: bool = True
    BODY_MIN_FRAMES_FOR_FUSION: int = 2
    BODY_OUTLIER_Z_SCORE: float = 2.5
    BODY_SMOOTHING_WINDOW: int = 5
    BODY_TARGET_FPS: int = 30
    BODY_MAX_MEMORY_MB: int = 200
    BODY_ENABLE_SHAPE_CLASSIFICATION: bool = True
    BODY_ENABLE_WEIGHT_DISTRIBUTION: bool = True
    BODY_ENABLE_STATISTICAL_MODEL: bool = True
    BODY_ENABLE_AVATAR_GENERATION: bool = True
    BODY_ENABLE_MOTION_ANALYSIS: bool = True
    USE_ANTHROPOMETRIC_DATASET: bool = False
    ANTHROPOMETRIC_DATASET_PATH: str = "data/USExtractedAnthro.xlsx"

    # Illumination Profile Settings
    FACE_MIN_SIZE_RATIO: float = 0.2
    FACE_MAX_SIZE_RATIO: float = 0.8
    FACE_CENTER_MARGIN: float = 0.2
    EYE_SHADOW_THRESHOLD: float = 15.0
    CHEEK_HIGHLIGHT_THRESHOLD: float = 85.0
    TARGET_EXPOSURE_MEAN: float = 0.5
    SHADOW_THRESHOLD: float = 30.0
    HIGHLIGHT_THRESHOLD: float = 80.0
    GAMMA_CLIP_RANGE: Tuple[float, float] = (0.5, 2.0)

    # Skin Analysis Model Settings
    SKIN_MODEL_PATH: str = "models/skin/"
    SKIN_SEGMENTATION_MODEL: str = "unet_skin.pth"
    SKIN_TONE_MODEL: str = "fitzpatrick17k_resnet50.pth"
    SKIN_CONDITION_MODEL: str = "ham10000_efficientnet.pth"
    SKIN_TEXTURE_MODEL: str = "texture_cnn.pth"
    SKIN_PIGMENTATION_MODEL: str = "pigmentation_cnn.pth"
    SKIN_GENETIC_MODEL: str = "genetic_phenotypes.pth"
    SKIN_ENVIRONMENTAL_MODEL: str = "environmental_effects.pth"
    SKIN_USE_GPU: bool = True
    SKIN_BATCH_SIZE: int = 8
    SKIN_MIN_CONFIDENCE: float = 0.6

    # Learning & Feedback Settings
    ENABLE_USER_EMBEDDING: bool = True
    USER_EMBEDDING_DIM: int = 128
    FEEDBACK_STORAGE_DAYS: int = 90
    ENABLE_AUTOMATIC_RETRAINING: bool = True
    RETRAINING_SCHEDULE_HOURS: int = 168  # weekly

    # A/B Testing
    ENABLE_AB_TESTING: bool = True
    AB_TEST_COOKIE_NAME: str = "xyra_exp"
    DEFAULT_EXPERIMENT: str = "control"

    def __post_init__(self):
        assert self.MAX_RESPONSE_MS >= self.MVP_TIMEOUT_MS + self.ML_TIMEOUT_MS + 30
        assert self.DIFFERENTIAL_PRIVACY_EPSILON > 0
        if self.ENCRYPT_SENSITIVE_DATA:
            self.cipher = Fernet(self.ENCRYPTION_KEY)

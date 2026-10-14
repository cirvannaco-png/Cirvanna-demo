import numpy as np
from typing import Optional, Dict, Any

class SkinAnalysisConfig:
    """Immutable configuration per specification thresholds"""
    
    # Gate thresholds (Specification Section 3)
    LIGHTING_CONFIDENCE_THRESHOLD: float = 0.85
    BODY_STABILITY_THRESHOLD: float = 0.9
    MIN_SKIN_VISIBILITY: float = 0.7
    SENSOR_QUALITY_THRESHOLD: float = 0.8
    
    # Vector dimensions (Specification Section 4)
    VECTOR_DIMENSIONS: int = 5
    
    # Output schema (Specification Section 4)
    OUTPUT_SCHEMA: Dict[str, Any] = {
        "skin_state_vector": Optional[list],
        "confidence_score": float,
        "contamination_flags": list
    }
    
    # Sensor quality bounds
    SENSOR_EXPOSURE_MIN: int = 100
    SENSOR_EXPOSURE_MAX: int = 800
    SENSOR_ISO_MAX: int = 1600
    SENSOR_FOCUS_MIN: float = 0.8
    
    # Image quality bounds
    IMAGE_INTENSITY_MIN: int = 10
    IMAGE_INTENSITY_MAX: int = 240
    
    # Lighting bounds
    LIGHTING_AMBIENT_MIN: int = 50

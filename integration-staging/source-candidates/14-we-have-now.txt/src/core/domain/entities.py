# src/core/domain/entities.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Set, Optional, Dict, Any
from uuid import UUID
import numpy as np

@dataclass
class Vector:
    values: np.ndarray

    def cosine_similarity(self, other: 'Vector') -> float:
        norm = np.linalg.norm(self.values) * np.linalg.norm(other.values)
        return float(np.dot(self.values, other.values) / norm) if norm != 0 else 0.0

    def to_list(self) -> List[float]:
        return self.values.tolist()

@dataclass
class ItemFeatures:
    color: str = 'unknown'
    material: str = 'unknown'
    style_tags: List[str] = field(default_factory=list)
    pattern: Optional[str] = None
    silhouette: Optional[str] = None
    formality: float = 0.5
    trendiness: float = 0.5
    versatility: float = 0.5
    thermal_rating: float = 0.5
    water_resistance: float = 0.0
    uv_protection: float = 0.0
    breathability: float = 0.5
    wind_resistance: float = 0.0
    brand: str = 'unknown'

@dataclass
class Item:
    item_id: UUID
    category: str
    features: ItemFeatures
    embedding: Vector
    created_at: datetime
    updated_at: datetime
    revival_score: float = 0.5
    trend_score: float = 0.5
    climate_compatibility: Set[str] = field(default_factory=set)
    confidence: float = 0.8
    thermal_rating: float = 0.5
    water_resistance: float = 0.0
    uv_protection: float = 0.0
    breathability: float = 0.5
    wind_resistance: float = 0.0
    brand: str = 'unknown'

@dataclass
class UserProfile:
    user_id: UUID
    style_vector: Vector
    archetype: str
    created_at: datetime
    updated_at: datetime
    negative_preferences: Set[str] = field(default_factory=set)
    cultural_constraints: Dict[str, Any] = field(default_factory=dict)
    location: Optional[Dict[str, float]] = None
    style_history: List[Dict] = field(default_factory=list)
    engagement_rate: float = 0.5
    exploration_rate: float = 0.5
    body_measurements: Optional[Dict[str, float]] = None

@dataclass
class FeedbackEvent:
    event_id: UUID
    user_id: UUID
    item_id: UUID
    event_type: str
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    recency_weight: float = 1.0
    engagement_weight: float = 1.0
    effective_weight: float = 1.0

    @property
    def base_weight(self) -> float:
        weights = {
            'purchase': 1.0,
            'save': 0.7,
            'tryon': 0.6,
            'view': 0.3,
            'skip': -0.2
        }
        return weights.get(self.event_type, 0.0)

@dataclass
class CulturalTrend:
    trend_id: UUID
    name: str
    embedding: Vector
    confidence: float
    created_at: datetime
    expires_at: datetime

@dataclass
class SegmentPrior:
    segment_id: str
    embedding: np.ndarray
    confidence: float
    variance: float
    last_updated: datetime
    sample_size: int

@dataclass
class StyleSnapshot:
    user_id: UUID
    timestamp: datetime
    dominant_style_embedding: List[float]
    confidence_trend: float
    revival_trend: float

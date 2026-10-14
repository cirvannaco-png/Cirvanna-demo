"""
Probabilistic body model with shape classification and weight distribution.
"""
import time
import json
import zlib
import base64
import numpy as np
from typing import Dict, List, Any, Optional
from collections import defaultdict
from ..math.core import fast_bayesian_update
from ..data_structures import RingBuffer
from .body import BodySegment, AnthropometricDatabase, BodyShape

class ProbabilisticSegment:
    __slots__ = ['mean', 'std', 'confidence', 'sources', 'flags', '_ring_buffer']

    def __init__(self, mean: float = 0.0, std: float = 0.1,
                 confidence: float = 0.0, window_size: int = 5):
        self.mean = mean
        self.std = std
        self.confidence = confidence
        self.sources = []
        self.flags = []
        self._ring_buffer = RingBuffer(window_size)

    def update(self, observation: float, obs_std: float,
               source_id: int, obs_confidence: float) -> bool:
        if obs_confidence < 0.1:
            return False
        new_mean, new_std = fast_bayesian_update(
            self.mean, self.std,
            observation, obs_std
        )
        self._ring_buffer.push(observation)
        if self._ring_buffer.size >= 3:
            smoothed_mean = self._ring_buffer.get_smoothed(0.3)
            blend_factor = min(0.3, 1.0 / (len(self.sources) + 1))
            self.mean = (1 - blend_factor) * new_mean + blend_factor * smoothed_mean
        else:
            self.mean = new_mean
        self.std = new_std
        if len(self.sources) == 0:
            self.confidence = obs_confidence
        else:
            alpha = 0.3
            self.confidence = (1 - alpha) * self.confidence + alpha * obs_confidence
        self.sources.append(source_id)
        return True

    @property
    def reliability_score(self) -> float:
        if self.confidence < 0.3:
            return 0.0
        consistency = 1.0 / (1.0 + self.std / (abs(self.mean) + 1e-6))
        source_factor = min(1.0, len(self.sources) / 5.0)
        return self.confidence * 0.6 + consistency * 0.3 + source_factor * 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'mean': float(self.mean),
            'std': float(self.std),
            'confidence': float(self.confidence),
            'reliability': float(self.reliability_score),
            'sources_count': len(self.sources),
            'flags': self.flags.copy()
        }

class PBody:
    def __init__(self, config):
        self.config = config
        self.segments: Dict[BodySegment, ProbabilisticSegment] = {}
        self.height: Optional[ProbabilisticSegment] = None
        self.weight: Optional[ProbabilisticSegment] = None
        self.posture: Dict[str, np.ndarray] = {}
        self.overall_confidence = 0.0
        self.flags: List[str] = []
        self.metadata: Dict[str, Any] = {}
        for segment in BodySegment:
            if segment == BodySegment.HEIGHT:
                self.height = ProbabilisticSegment(window_size=config.smoothing_window)
            elif segment == BodySegment.WEIGHT:
                self.weight = ProbabilisticSegment(window_size=config.smoothing_window)
            else:
                self.segments[segment] = ProbabilisticSegment(window_size=config.smoothing_window)
        self.update_times = RingBuffer(100)
        self._last_update = time.time()
        self.shape: Optional[BodyShape] = None
        self.visceral_fat: Optional[float] = None
        self.subcutaneous_fat: Optional[float] = None
        self.ratios: Dict[str, float] = {}

    def update_segment(self, segment: BodySegment, observation: float,
                       obs_std: float, source_id: int, obs_confidence: float) -> bool:
        start = time.time()
        if segment == BodySegment.HEIGHT:
            success = self.height.update(observation, obs_std, source_id, obs_confidence)
        elif segment == BodySegment.WEIGHT:
            success = self.weight.update(observation, obs_std, source_id, obs_confidence)
        elif segment in self.segments:
            success = self.segments[segment].update(observation, obs_std, source_id, obs_confidence)
        else:
            success = False
        self.update_times.push(time.time() - start)
        return success

    def compute_overall_confidence(self) -> float:
        if not self.segments:
            self.overall_confidence = 0.0
            return 0.0
        importance_weights = {
            BodySegment.CHEST: 0.20,
            BodySegment.WAIST: 0.20,
            BodySegment.HIPS: 0.15,
            BodySegment.HEIGHT: 0.15,
            BodySegment.SHOULDER_WIDTH: 0.10,
            BodySegment.INSEAM: 0.10,
            BodySegment.LEFT_UPPER_ARM: 0.05,
            BodySegment.LEFT_THIGH: 0.05,
        }
        total_weight = 0.0
        weighted_conf = 0.0
        for segment, weight in importance_weights.items():
            if segment == BodySegment.HEIGHT:
                seg_confidence = self.height.confidence if self.height else 0.0
            elif segment in self.segments:
                seg_confidence = self.segments[segment].confidence
            else:
                continue
            weighted_conf += seg_confidence * weight
            total_weight += weight
        if total_weight > 0:
            self.overall_confidence = weighted_conf / total_weight
        else:
            self.overall_confidence = 0.0
        return self.overall_confidence

    def check_plausibility(self, anthropo_db) -> List[str]:
        issues = []
        if not self.height or self.height.mean < 0.1:
            return ["Missing or invalid height"]
        height = self.height.mean
        for segment, constraint in anthropo_db.height_constraints.items():
            if segment in self.segments:
                segment_val = self.segments[segment].mean
                ratio = segment_val / height
                if ratio < constraint.min_ratio or ratio > constraint.max_ratio:
                    issues.append(
                        f"{segment.value}: ratio {ratio:.3f} outside range "
                        f"[{constraint.min_ratio:.3f}, {constraint.max_ratio:.3f}]"
                    )
        bilateral_pairs = [
            (BodySegment.LEFT_UPPER_ARM, BodySegment.RIGHT_UPPER_ARM),
            (BodySegment.LEFT_THIGH, BodySegment.RIGHT_THIGH),
            (BodySegment.LEFT_CALF, BodySegment.RIGHT_CALF),
        ]
        for left, right in bilateral_pairs:
            if left in self.segments and right in self.segments:
                left_val = self.segments[left].mean
                right_val = self.segments[right].mean
                asymmetry = abs(left_val - right_val) / ((left_val + right_val) / 2 + 1e-6)
                if asymmetry > 0.15:
                    issues.append(f"Asymmetry in {left.value.replace('left_', '')}: {asymmetry:.1%}")
        self.flags.extend(issues)
       

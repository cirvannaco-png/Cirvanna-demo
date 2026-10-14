import numpy as np
from typing import Optional, List, Dict

try:
    from scipy.ndimage import uniform_filter, sobel
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from .config import SkinAnalysisConfig

class PurePerceptionEngine:
    """PURE PERCEPTION - NO INTERPRETATION"""
    
    @staticmethod
    def compute_skin_state_vector(frame: np.ndarray) -> np.ndarray:
        if frame.size == 0:
            return np.full(SkinAnalysisConfig.VECTOR_DIMENSIONS, 0.5, 
                          dtype=np.float32)
        
        if len(frame.shape) == 3:
            gray = np.mean(frame, axis=2).astype(np.float32)
            color_channels = frame.astype(np.float32)
        else:
            gray = frame.astype(np.float32)
            color_channels = None
        
        texture_uniformity = PurePerceptionEngine._compute_texture_uniformity(gray)
        surface_reflectance = PurePerceptionEngine._compute_surface_reflectance(gray)
        chromatic_deviation = PurePerceptionEngine._compute_chromatic_deviation(
            color_channels)
        moisture_proxy = PurePerceptionEngine._compute_moisture_proxy(gray)
        micro_variation = PurePerceptionEngine._compute_micro_variation(gray)
        
        vector = np.array([
            texture_uniformity,
            surface_reflectance,
            chromatic_deviation,
            moisture_proxy,
            micro_variation
        ], dtype=np.float32)
        
        return np.clip(vector, 0.0, 1.0)
    
    @staticmethod
    def _compute_texture_uniformity(gray: np.ndarray) -> float:
        if gray.size == 0:
            return 0.5
        
        if SCIPY_AVAILABLE:
            local_mean = uniform_filter(gray, size=5)
            local_var = uniform_filter(gray**2, size=5) - local_mean**2
            local_std = np.sqrt(np.maximum(local_var, 0))
            uniformity = 1.0 - np.clip(np.mean(local_std) / 20.0, 0, 1)
        else:
            uniformity = 1.0 - np.clip(np.std(gray) / 50.0, 0, 1)
        
        return float(uniformity)
    
    @staticmethod
    def _compute_surface_reflectance(gray: np.ndarray) -> float:
        if gray.size == 0:
            return 0.5
        
        if gray.max() > 0:
            reflectance = np.mean(gray) / 255.0
        else:
            reflectance = 0.5
        
        return float(np.clip(reflectance, 0, 1))
    
    @staticmethod
    def _compute_chromatic_deviation(color_channels: Optional[np.ndarray]) -> float:
        if color_channels is None or color_channels.size == 0:
            return 0.5
        
        r_mean = np.mean(color_channels[..., 0])
        g_mean = np.mean(color_channels[..., 1])
        b_mean = np.mean(color_channels[..., 2])
        
        max_val = max(r_mean, g_mean, b_mean)
        if max_val == 0:
            return 0.5
        
        ratios = [r_mean / max_val, g_mean / max_val, b_mean / max_val]
        deviation = np.std(ratios)
        return float(np.clip(deviation, 0, 1))
    
    @staticmethod
    def _compute_moisture_proxy(gray: np.ndarray) -> float:
        if gray.size == 0:
            return 0.5
        
        bright_threshold = 0.9 * 255
        bright_ratio = np.sum(gray > bright_threshold) / gray.size
        return float(np.clip(bright_ratio * 3, 0, 1))
    
    @staticmethod
    def _compute_micro_variation(gray: np.ndarray) -> float:
        if gray.size == 0:
            return 0.5
        
        if SCIPY_AVAILABLE:
            grad_x = sobel(gray, axis=0)
            grad_y = sobel(gray, axis=1)
            grad_mag = np.sqrt(grad_x**2 + grad_y**2)
            variation = np.clip(np.mean(grad_mag) / 30.0, 0, 1)
        else:
            grad_x = np.diff(gray, axis=0)
            grad_y = np.diff(gray, axis=1)
            if grad_x.size > 0 and grad_y.size > 0:
                grad_x = np.pad(grad_x, ((0, 1), (0, 0)))
                grad_y = np.pad(grad_y, ((0, 0), (0, 1)))
                grad_mag = np.sqrt(grad_x**2 + grad_y**2)
                variation = np.clip(np.mean(grad_mag) / 30.0, 0, 1)
            else:
                variation = 0.5
        
        return float(variation)
    
    @staticmethod
    def detect_contamination(frame: np.ndarray, 
                           sensor_metadata: Dict) -> List[str]:
        flags = []
        
        if frame.size > 0 and frame.mean() > 230:
            flags.append("SENSOR_SATURATION")
        
        if sensor_metadata.get("motion_blur_estimate", 0) > 0.5:
            flags.append("MOTION_BLUR")
        
        if sensor_metadata.get("noise_estimate", 0) > 0.3:
            flags.append("ENVIRONMENTAL_NOISE")
        
        if len(frame.shape) == 3:
            color_std = np.std(frame, axis=(0, 1))
            if np.any(color_std < 10):
                flags.append("MAKEUP_INTERFERENCE")
        
        if frame.size > 0:
            lighting_variance = np.var(frame)
            if lighting_variance > 5000:
                flags.append("HARSH_LIGHT_DISTORTION")
        
        return flags
    
    @staticmethod
    def compute_confidence_score(signal_quality: float,
                               contamination_flags: List[str]) -> float:
        if signal_quality == 0:
            return 0.0
        
        base_confidence = signal_quality
        if contamination_flags:
            penalty = 0.8 ** len(contamination_flags)
            base_confidence *= penalty
        
        return float(np.clip(base_confidence, 0, 1))

import numpy as np
from typing import Dict
from dataclasses import dataclass

@dataclass(frozen=True)
class SkinAnalysisInput:
    """IMMUTABLE INPUT CONTRACT"""
    
    raw_frame: np.ndarray
    body_calibration: Dict[str, float]
    lighting_metadata: Dict[str, float]
    sensor_metadata: Dict[str, float]
    environmental_confidence: float
    
    def __post_init__(self):
        if not isinstance(self.raw_frame, np.ndarray):
            raise TypeError("raw_frame must be a numpy array")
        
        if self.raw_frame.dtype not in [np.uint8, np.float32, np.float64]:
            raise TypeError("raw_frame must be uint8, float32, or float64")
        
        if self.raw_frame.ndim not in [2, 3]:
            raise ValueError("raw_frame must be 2D (grayscale) or 3D (color)")
        
        self._validate_no_forbidden_inputs()
    
    def _validate_no_forbidden_inputs(self):
        if hasattr(self, 'timestamp') and self.timestamp != 'PRESENT_MOMENT_ONLY':
            raise ValueError("Historical data forbidden")
        
        forbidden_calibration_keys = {'age', 'ethnicity', 'gender', 'skin_type'}
        if any(key in self.body_calibration for key in forbidden_calibration_keys):
            raise ValueError("Demographic inference forbidden")
        
        product_indicators = ['product', 'brand', 'skincare', 'treatment']
        all_metadata = str(self.lighting_metadata) + str(self.sensor_metadata)
        if any(indicator in all_metadata.lower() for indicator in product_indicators):
            raise ValueError("Product/brand data forbidden")

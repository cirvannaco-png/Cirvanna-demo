import numpy as np
from typing import Optional, Tuple
from .input import SkinAnalysisInput
from .config import SkinAnalysisConfig

class PreconditionGates:
    """EXACT IMPLEMENTATION OF SPECIFICATION SECTION 3"""
    
    @staticmethod
    def check_all_gates(input_data: SkinAnalysisInput, 
                       config: SkinAnalysisConfig) -> Tuple[bool, Optional[str]]:
        gates = [
            ("LIGHTING_INSUFFICIENT", PreconditionGates._check_lighting_gate, 
             [input_data, config]),
            ("BODY_UNSTABLE", PreconditionGates._check_body_stability_gate, 
             [input_data, config]),
            ("OCCLUSION_TOO_HIGH", PreconditionGates._check_skin_visibility_gate, 
             [input_data, config]),
            ("SENSOR_NOISE", PreconditionGates._check_sensor_quality_gate, 
             [input_data, config]),
            ("CONFIDENCE_LAYER_VETO", PreconditionGates._check_confidence_layer_gate, 
             [input_data, config])
        ]
        
        for flag_name, gate_func, args in gates:
            if not gate_func(*args):
                return False, flag_name
        
        return True, None
    
    @staticmethod
    def _check_lighting_gate(input_data: SkinAnalysisInput, 
                           config: SkinAnalysisConfig) -> bool:
        if input_data.environmental_confidence < config.LIGHTING_CONFIDENCE_THRESHOLD:
            return False
        
        ambient = input_data.lighting_metadata.get('ambient_light', 0)
        if ambient < config.LIGHTING_AMBIENT_MIN:
            return False
        
        return True
    
    @staticmethod
    def _check_body_stability_gate(input_data: SkinAnalysisInput,
                                 config: SkinAnalysisConfig) -> bool:
        cal = input_data.body_calibration
        pose_stable = cal.get('pose_stability', 0) >= config.BODY_STABILITY_THRESHOLD
        low_motion = cal.get('motion_magnitude', 1.0) <= 0.1
        return pose_stable and low_motion
    
    @staticmethod
    def _check_skin_visibility_gate(input_data: SkinAnalysisInput,
                                  config: SkinAnalysisConfig) -> bool:
        visible_ratio = input_data.body_calibration.get('skin_visible_ratio', 0)
        return visible_ratio >= config.MIN_SKIN_VISIBILITY
    
    @staticmethod
    def _check_sensor_quality_gate(input_data: SkinAnalysisInput,
                                 config: SkinAnalysisConfig) -> bool:
        sensor = input_data.sensor_metadata
        exposure = sensor.get('exposure', 0)
        iso = sensor.get('iso', 0)
        focus_confidence = sensor.get('focus_confidence', 0)
        
        exposure_valid = (config.SENSOR_EXPOSURE_MIN <= exposure <= 
                         config.SENSOR_EXPOSURE_MAX)
        iso_valid = iso <= config.SENSOR_ISO_MAX
        focus_valid = focus_confidence >= config.SENSOR_FOCUS_MIN
        
        return exposure_valid and iso_valid and focus_valid
    
    @staticmethod
    def _check_confidence_layer_gate(input_data: SkinAnalysisInput,
                                   config: SkinAnalysisConfig) -> bool:
        if input_data.raw_frame.size > 0:
            frame_quality = np.mean(input_data.raw_frame)
            internal_confidence = 1.0 if (config.IMAGE_INTENSITY_MIN < 
                                        frame_quality < 
                                        config.IMAGE_INTENSITY_MAX) else 0.0
        else:
            internal_confidence = 0.0
        
        combined_confidence = (input_data.environmental_confidence + 
                             internal_confidence) / 2
        return combined_confidence >= config.LIGHTING_CONFIDENCE_THRESHOLD

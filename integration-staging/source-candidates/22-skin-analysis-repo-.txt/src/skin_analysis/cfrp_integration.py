import time
import numpy as np
from typing import Optional, List, Dict
from .output import SkinAnalysisOutput

class CFRPIntegration:
    """COMPLETE CFRP INTEGRATION PER SPECIFICATION SECTION 8"""
    
    @staticmethod
    def process_skin_analysis(skin_output: SkinAnalysisOutput,
                            confidence_layer_result: Dict,
                            body_calibration: Dict,
                            lighting_metadata: Dict) -> Dict:
        if (confidence_layer_result.get("confidence_score", 0) == 0 or
            confidence_layer_result.get("confidence_layer_action") == "VETO_APPLIED"):
            return CFRPIntegration._create_fallback_output(
                body_calibration,
                lighting_metadata,
                "SKIN_ANALYSIS_IGNORED"
            )
        
        contamination_flags = confidence_layer_result.get("contamination_flags", [])
        weighting_factor = 1.0
        if contamination_flags:
            weighting_factor = 0.8 ** len(contamination_flags)
        
        composite_vector = CFRPIntegration._create_composite_vector(
            skin_output,
            body_calibration,
            lighting_metadata,
            weighting_factor
        )
        
        return {
            "composite_perception_vector": composite_vector,
            "skin_analysis_weight": weighting_factor,
            "confidence_score": confidence_layer_result.get("confidence_score", 0),
            "contamination_flags": contamination_flags,
            "body_calibration_used": body_calibration,
            "lighting_adjustment_used": lighting_metadata,
            "integration_timestamp": time.time()
        }
    
    @staticmethod
    def _create_fallback_output(body_calibration: Dict,
                              lighting_metadata: Dict,
                              reason: str) -> Dict:
        return {
            "composite_perception_vector": None,
            "skin_analysis_weight": 0.0,
            "fallback_reason": reason,
            "body_calibration_used": body_calibration,
            "lighting_adjustment_used": lighting_metadata,
            "confidence_score": 0.0,
            "contamination_flags": [reason],
            "timestamp": time.time()
        }
    
    @staticmethod
    def _create_composite_vector(skin_output: SkinAnalysisOutput,
                               body_calibration: Dict,
                               lighting_metadata: Dict,
                               weighting_factor: float) -> Optional[List[float]]:
        if skin_output.skin_state_vector is None:
            return None
        
        body_vector = [
            body_calibration.get('pose_stability', 0.5),
            body_calibration.get('orientation_confidence', 0.5),
            body_calibration.get('surface_mapping_confidence', 0.5)
        ]
        
        lighting_vector = [
            lighting_metadata.get('ambient_light', 0.5) / 100.0,
            lighting_metadata.get('light_uniformity', 0.5),
            lighting_metadata.get('intensity_correction', 1.0)
        ]
        
        skin_vector = skin_output.skin_state_vector.tolist()
        combined = skin_vector + body_vector + lighting_vector
        
        for i in range(len(skin_vector)):
            combined[i] = combined[i] * weighting_factor
        
        return combined

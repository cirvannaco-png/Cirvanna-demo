import time
import numpy as np
from typing import Dict
from .output import SkinAnalysisOutput

class ConfidenceLayer:
    """SEPARATE MODULE with veto authority"""
    
    def __init__(self, veto_threshold: float = 0.1):
        self.veto_threshold = veto_threshold
    
    def evaluate(self, skin_output: SkinAnalysisOutput,
                additional_data: Dict) -> Dict:
        if skin_output.is_refusal():
            return {
                "skin_state_vector": None,
                "confidence_score": 0.0,
                "contamination_flags": skin_output.contamination_flags,
                "confidence_layer_action": "PASS_THROUGH_REFUSAL",
                "timestamp": time.time()
            }
        
        layer_confidence = self._internal_evaluation(skin_output, additional_data)
        
        if layer_confidence < self.veto_threshold:
            return {
                "skin_state_vector": None,
                "confidence_score": 0.0,
                "contamination_flags": ["CONFIDENCE_LAYER_VETO"],
                "confidence_layer_action": "VETO_APPLIED",
                "veto_reason": f"layer_confidence={layer_confidence:.3f}",
                "timestamp": time.time()
            }
        
        weighted_confidence = skin_output.confidence_score * layer_confidence
        
        return {
            "skin_state_vector": (
                skin_output.skin_state_vector.tolist() 
                if skin_output.skin_state_vector is not None 
                else None
            ),
            "confidence_score": weighted_confidence,
            "contamination_flags": skin_output.contamination_flags,
            "confidence_layer_action": "APPROVED",
            "weighting_factor": layer_confidence,
            "timestamp": time.time()
        }
    
    def _internal_evaluation(self, skin_output: SkinAnalysisOutput,
                           additional_data: Dict) -> float:
        base_confidence = additional_data.get("environmental_confidence", 1.0)
        
        if skin_output.contamination_flags:
            contamination_penalty = 0.8 ** len(skin_output.contamination_flags)
            base_confidence *= contamination_penalty
        
        temporal_consistency = additional_data.get("temporal_consistency", 1.0)
        multi_modal_agreement = additional_data.get("multi_modal_agreement", 1.0)
        
        combined_confidence = (base_confidence * temporal_consistency * 
                             multi_modal_agreement)
        return float(np.clip(combined_confidence, 0, 1))

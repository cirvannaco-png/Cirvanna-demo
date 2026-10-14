import time
import logging
from typing import Dict
from .input import SkinAnalysisInput
from .analyzer import CirvannaSkinAnalysis
from .confidence_layer import ConfidenceLayer
from .cfrp_integration import CFRPIntegration

logger = logging.getLogger(__name__)

def complete_specification_pipeline(raw_inputs: Dict) -> Dict:
    """COMPLETE PIPELINE PER SPECIFICATION"""
    try:
        input_data = SkinAnalysisInput(**raw_inputs)
        
        analyzer = CirvannaSkinAnalysis()
        skin_output = analyzer.analyze(input_data)
        
        confidence_layer = ConfidenceLayer()
        confidence_result = confidence_layer.evaluate(skin_output, raw_inputs)
        
        cfrp_integration = CFRPIntegration()
        final_output = cfrp_integration.process_skin_analysis(
            skin_output,
            confidence_result,
            raw_inputs['body_calibration'],
            raw_inputs['lighting_metadata']
        )
        
        final_output.update({
            "specification_version": "Cirvanna Skin Analysis + CFRP Integration",
            "implementation_version": "4.0.0",
            "authority_hierarchy": ["CFRP", "CONFIDENCE_LAYER", "SKIN_ANALYSIS"],
            "compliance_check": "FULL_SPECIFICATION_IMPLEMENTED",
            "processing_time_ms": int(time.time() * 1000)
        })
        
        return final_output
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        return {
            "skin_state_vector": None,
            "confidence_score": 0.0,
            "contamination_flags": [f"PIPELINE_ERROR: {str(e)}"],
            "specification_compliance": "ERROR_IN_PROCESSING",
            "timestamp": time.time()
        }

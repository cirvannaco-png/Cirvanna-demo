import numpy as np
from typing import Optional, List, Dict
from dataclasses import dataclass
from .config import SkinAnalysisConfig

@dataclass(frozen=True)
class SkinAnalysisOutput:
    """EXACT OUTPUT SCHEMA FROM SPECIFICATION SECTION 4"""
    
    skin_state_vector: Optional[np.ndarray]
    confidence_score: float
    contamination_flags: List[str]
    
    refusal_flag: Optional[str] = None
    gate_failure: bool = False
    
    def __post_init__(self):
        if self.skin_state_vector is not None:
            if len(self.skin_state_vector) != SkinAnalysisConfig.VECTOR_DIMENSIONS:
                raise ValueError(
                    f"skin_state_vector must have {SkinAnalysisConfig.VECTOR_DIMENSIONS} "
                    f"dimensions, got {len(self.skin_state_vector)}"
                )
    
    def to_specification_format(self) -> Dict:
        output = {
            "skin_state_vector": (
                None if self.skin_state_vector is None 
                else self.skin_state_vector.tolist()
            ),
            "confidence_score": float(self.confidence_score),
            "contamination_flags": self.contamination_flags.copy()
        }
        
        required_keys = SkinAnalysisConfig.OUTPUT_SCHEMA.keys()
        if not all(key in output for key in required_keys):
            raise ValueError(f"Output missing required keys: {required_keys}")
        
        return output
    
    def is_refusal(self) -> bool:
        return self.confidence_score == 0 or self.skin_state_vector is None

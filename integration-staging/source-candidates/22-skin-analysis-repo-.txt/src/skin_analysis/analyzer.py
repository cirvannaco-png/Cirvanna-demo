import numpy as np
from typing import Optional, Dict
from .config import SkinAnalysisConfig
from .input import SkinAnalysisInput
from .output import SkinAnalysisOutput
from .gates import PreconditionGates
from .perception import PurePerceptionEngine
from .sandbox import AnalysisSandbox

class CirvannaSkinAnalysis:
    """COMPLETE SPECIFICATION IMPLEMENTATION"""
    
    def __init__(self, config: Optional[SkinAnalysisConfig] = None):
        self.config = config or SkinAnalysisConfig()
        self.gates = PreconditionGates()
        self.engine = PurePerceptionEngine()
        self.sandbox = AnalysisSandbox()
        
        if not self.sandbox.validate_no_side_effects(self):
            raise RuntimeError("Module has side effects - violates specification")
    
    def analyze(self, input_data: SkinAnalysisInput) -> SkinAnalysisOutput:
        with self.sandbox.isolated_execution():
            return self._analyze_isolated(input_data)
    
    def _analyze_isolated(self, input_data: SkinAnalysisInput) -> SkinAnalysisOutput:
        gates_passed, refusal_flag = self.gates.check_all_gates(
            input_data, self.config
        )
        
        if not gates_passed:
            return SkinAnalysisOutput(
                skin_state_vector=None,
                confidence_score=0.0,
                contamination_flags=[refusal_flag] if refusal_flag else ["GATE_FAILURE"],
                refusal_flag=refusal_flag,
                gate_failure=True
            )
        
        skin_vector = self.engine.compute_skin_state_vector(input_data.raw_frame)
        
        contamination_flags = self.engine.detect_contamination(
            input_data.raw_frame,
            input_data.sensor_metadata
        )
        
        frame_quality = self._compute_frame_quality(input_data.raw_frame)
        sensor_quality = self._compute_sensor_quality(input_data.sensor_metadata)
        signal_quality = (frame_quality + sensor_quality) / 2
        
        confidence_score = self.engine.compute_confidence_score(
            signal_quality,
            contamination_flags
        )
        
        if confidence_score == 0:
            return SkinAnalysisOutput(
                skin_state_vector=None,
                confidence_score=0.0,
                contamination_flags=contamination_flags + ["CONFIDENCE_ZERO_REFUSAL"],
                gate_failure=False
            )
        
        if confidence_score < 0.5:
            neutral = np.full(self.config.VECTOR_DIMENSIONS, 0.5, dtype=np.float32)
            compression_factor = confidence_score * 2
            skin_vector = (compression_factor * skin_vector + 
                          (1 - compression_factor) * neutral)
        
        return SkinAnalysisOutput(
            skin_state_vector=skin_vector,
            confidence_score=confidence_score,
            contamination_flags=contamination_flags,
            refusal_flag=None,
            gate_failure=False
        )
    
    def _compute_frame_quality(self, frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        
        mean_intensity = np.mean(frame)
        if (mean_intensity < self.config.IMAGE_INTENSITY_MIN or 
            mean_intensity > self.config.IMAGE_INTENSITY_MAX):
            return 0.0
        
        if mean_intensity > 0:
            contrast = np.std(frame) / 128.0
        else:
            contrast = 0
        
        return float(np.clip(contrast, 0, 1))
    
    def _compute_sensor_quality(self, sensor_metadata: Dict) -> float:
        iso = sensor_metadata.get('iso', 0)
        focus = sensor_metadata.get('focus_confidence', 0)
        exposure = sensor_metadata.get('exposure', 0)
        
        iso_quality = max(0, 1 - iso / 3200.0)
        exposure_quality = (1.0 if (self.config.SENSOR_EXPOSURE_MIN <= exposure <= 
                                  self.config.SENSOR_EXPOSURE_MAX) 
                          else 0.0)
        
        return float(np.clip((iso_quality + focus + exposure_quality) / 3, 0, 1))

import numpy as np
import time
from src.skin_analysis import (
    validate_specification_compliance,
    complete_specification_pipeline
)

if __name__ == "__main__":
    print("CIRVANNA SKIN ANALYSIS - COMPLETE SPECIFICATION IMPLEMENTATION")
    print("Version 4.0.0 | All Specification Sections Implemented\n")
    
    validation = validate_specification_compliance()
    
    if all(validation.values()):
        print("\n" + "=" * 70)
        print("DEMONSTRATING COMPLETE SPECIFICATION PIPELINE")
        
        sample_input = {
            'raw_frame': np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8),
            'body_calibration': {
                'pose_stability': 0.97,
                'motion_magnitude': 0.03,
                'skin_visible_ratio': 0.85,
                'orientation_confidence': 0.95
            },
            'lighting_metadata': {
                'ambient_light': 78.0,
                'light_uniformity': 0.98,
                'intensity_correction': 1.05
            },
            'sensor_metadata': {
                'iso': 200,
                'exposure': 180,
                'focus_confidence': 0.96,
                'white_balance_deviation': 0.08,
                'motion_blur_estimate': 0.2,
                'noise_estimate': 0.1
            },
            'environmental_confidence': 0.92
        }
        
        start_time = time.time()
        final_result = complete_specification_pipeline(sample_input)
        processing_time = time.time() - start_time
        
        print(f"\nFinal CFRP Output:")
        print(f"Status: {'VALID' if final_result.get('composite_perception_vector') else 'REFUSED'}")
        print(f"Confidence Score: {final_result.get('confidence_score', 0):.3f}")
        print(f"Skin Analysis Weight: {final_result.get('skin_analysis_weight', 0):.2f}")
        print(f"Contamination Flags: {final_result.get('contamination_flags', [])}")
        print(f"Processing Time: {processing_time * 1000:.1f} ms")
        print(f"Specification Compliance: {final_result.get('compliance_check', 'UNKNOWN')}")

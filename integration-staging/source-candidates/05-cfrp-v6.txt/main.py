"""
Main entry point for CFRP with skin and body intelligence.
"""
import asyncio
import numpy as np
from src.core.cfrp_manager import CFRPManager
from src.usi.usi_integration import USIIntegration
from src.skin.skin_analysis import SkinAnalyzer
from src.body.anthropometry import BodyMeasurements, Anthropometry
from src.body.body_shape import BodyShapeClassifier
from src.observability.logger import StructuredLogger

async def main():
    logger = StructuredLogger("cfrp_main")
    logger.info("Starting CFRP with Skin & Body Intelligence")

    # Initialize CFRP
    manager = CFRPManager()
    await manager.start()
    usi = USIIntegration(manager)

    # Simulate a user
    user_id = "user_123"

    # Simulate skin image (random RGB)
    fake_image = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)

    # Skin analysis
    skin_analyzer = SkinAnalyzer()
    skin_result = await skin_analyzer.analyze(fake_image)
    logger.info("Skin analysis complete",
                fitzpatrick=skin_result.fitzpatrick.name,
                undertone=skin_result.undertone.value if skin_result.undertone else None)

    # Body measurements (simulated)
    measurements = BodyMeasurements(
        height=170, weight=65,
        chest_circ=90, waist_circ=75, hip_circ=95,
        shoulder_width=40, arm_length=60, leg_length=80,
        thigh_circ=55, calf_circ=35, neck_circ=35
    )
    bmi = Anthropometry.bmi(measurements.weight, measurements.height)
    whr = Anthropometry.waist_to_hip(measurements.waist_circ, measurements.hip_circ)
    body_shape = BodyShapeClassifier.classify(measurements)
    logger.info("Body analysis complete", bmi=bmi, whr=whr, body_shape=body_shape.value)

    # Define signals based on skin/body features
    signals = [
        {"signal": "fitzpatrick", "usi_weight": 0.8},
        {"signal": "undertone", "usi_weight": 0.6},
        {"signal": "pore_density", "usi_weight": 0.4},
        {"signal": "body_shape", "usi_weight": 0.7},
        {"signal": "bmi", "usi_weight": 0.5}
    ]

    # Get CFRP advice
    enhanced = await usi.get_weighted_suggestions(user_id, signals)
    logger.info("Weighted suggestions", suggestions=enhanced)

    # Simulate feedback (user liked a product based on Fitzpatrick)
    result = await usi.process_feedback(user_id, "fitzpatrick", success=True, value=0.9)
    logger.info("Reinforcement result", result=result)

    # Shutdown
    await manager.shutdown()
    logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())

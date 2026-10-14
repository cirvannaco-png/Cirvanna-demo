"""
Body shape classification and ratios.
"""
from enum import Enum
from src.body.anthropometry import BodyMeasurements

class BodyShape(Enum):
    HOURGLASS = "hourglass"
    PEAR = "pear"
    RECTANGLE = "rectangle"
    INVERTED_TRIANGLE = "inverted_triangle"

class BodyShapeClassifier:
    @staticmethod
    def classify(measurements: BodyMeasurements) -> BodyShape:
        whr = measurements.waist_circ / measurements.hip_circ
        shoulder_hip_ratio = measurements.shoulder_width / measurements.hip_circ

        if whr < 0.75 and shoulder_hip_ratio < 0.9:
            return BodyShape.HOURGLASS
        elif whr < 0.75 and shoulder_hip_ratio > 1.1:
            return BodyShape.INVERTED_TRIANGLE
        elif whr > 0.85:
            return BodyShape.PEAR
        else:
            return BodyShape.RECTANGLE

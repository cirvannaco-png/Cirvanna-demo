"""
Body segment definitions and anthropometric constraints.
Now includes all measurements, shape classification, weight distribution, and ratios.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List

class BodySegment(Enum):
    HEIGHT = "height"
    WEIGHT = "weight"
    CHEST = "chest"
    WAIST = "waist"
    HIPS = "hips"
    SHOULDER_WIDTH = "shoulder_width"
    NECK = "neck"
    LEFT_UPPER_ARM = "left_upper_arm"
    RIGHT_UPPER_ARM = "right_upper_arm"
    LEFT_FOREARM = "left_forearm"
    RIGHT_FOREARM = "right_forearm"
    LEFT_THIGH = "left_thigh"
    RIGHT_THIGH = "right_thigh"
    LEFT_CALF = "left_calf"
    RIGHT_CALF = "right_calf"
    INSEAM = "inseam"
    ARM_LENGTH = "arm_length"
    LEG_LENGTH = "leg_length"
    TORSO_LENGTH = "torso_length"
    VISCERAL_FAT = "visceral_fat"
    SUBCUTANEOUS_FAT = "subcutaneous_fat"
    POSTURE_SPINE = "posture_spine"
    POSTURE_SHOULDERS = "posture_shoulders"
    POSTURE_PELVIS = "posture_pelvis"

class BodyShape(Enum):
    HOURGLASS = "hourglass"
    PEAR = "pear"
    RECTANGLE = "rectangle"
    INVERTED_TRIANGLE = "inverted_triangle"
    APPLE = "apple"

@dataclass
class SegmentConstraint:
    min_ratio: float
    max_ratio: float
    typical_value: float
    importance: float
    bilateral: bool = False

class AnthropometricDatabase:
    def __init__(self):
        self.height_constraints = {
            BodySegment.CHEST: SegmentConstraint(0.23, 0.28, 0.255, 0.9),
            BodySegment.WAIST: SegmentConstraint(0.18, 0.23, 0.205, 0.9),
            BodySegment.HIPS: SegmentConstraint(0.19, 0.24, 0.215, 0.9),
            BodySegment.SHOULDER_WIDTH: SegmentConstraint(0.20, 0.25, 0.225, 0.8),
            BodySegment.INSEAM: SegmentConstraint(0.45, 0.50, 0.475, 0.7),
            BodySegment.NECK: SegmentConstraint(0.10, 0.13, 0.115, 0.6),
        }
        self.segment_constraints = {
            (BodySegment.LEFT_UPPER_ARM, BodySegment.HEIGHT): SegmentConstraint(0.16, 0.19, 0.175, 0.6),
            (BodySegment.LEFT_THIGH, BodySegment.HEIGHT): SegmentConstraint(0.22, 0.26, 0.240, 0.7),
        }
        self.gender_adjustments = {
            'male': {
                'shoulder_to_hip_ratio': (1.1, 1.3),
                'chest_to_waist_ratio': (1.05, 1.15),
                'waist_to_hip_ratio': (0.85, 0.95),
            },
            'female': {
                'shoulder_to_hip_ratio': (0.85, 1.0),
                'chest_to_waist_ratio': (0.95, 1.05),
                'waist_to_hip_ratio': (0.70, 0.80),
            }
        }

    def get_constraint(self, segment: BodySegment, height: float = None) -> Optional[SegmentConstraint]:
        if segment in self.height_constraints and height:
            return self.height_constraints[segment]
        for (seg1, seg2), constraint in self.segment_constraints.items():
            if segment == seg1:
                return constraint
        return None

    def compute_ratios(self, measurements: Dict[BodySegment, float]) -> Dict[str, float]:
        ratios = {}
        if BodySegment.WAIST in measurements and BodySegment.HIPS in measurements:
            ratios["waist_to_hip"] = measurements[BodySegment.WAIST] / measurements[BodySegment.HIPS]
        if BodySegment.WAIST in measurements and BodySegment.HEIGHT in measurements:
            ratios["waist_to_height"] = measurements[BodySegment.WAIST] / measurements[BodySegment.HEIGHT]
        if BodySegment.SHOULDER_WIDTH in measurements and BodySegment.HIPS in measurements:
            ratios["shoulder_to_hip"] = measurements[BodySegment.SHOULDER_WIDTH] / measurements[BodySegment.HIPS]
        if BodySegment.SHOULDER_WIDTH in measurements and BodySegment.WAIST in measurements:
            ratios["shoulder_to_waist"] = measurements[BodySegment.SHOULDER_WIDTH] / measurements[BodySegment.WAIST]
        if BodySegment.LEG_LENGTH in measurements and BodySegment.TORSO_LENGTH in measurements:
            ratios["leg_to_torso"] = measurements[BodySegment.LEG_LENGTH] / measurements[BodySegment.TORSO_LENGTH]
        return ratios

"""
Core body measurements.
"""
from dataclasses import dataclass

@dataclass
class BodyMeasurements:
    height: float          # cm
    weight: float          # kg
    chest_circ: float      # cm
    waist_circ: float
    hip_circ: float
    shoulder_width: float
    arm_length: float
    leg_length: float
    thigh_circ: float
    calf_circ: float
    neck_circ: float

class Anthropometry:
    @staticmethod
    def bmi(weight: float, height: float) -> float:
        return weight / ((height/100) ** 2)

    @staticmethod
    def waist_to_hip(waist: float, hip: float) -> float:
        return waist / hip

    @staticmethod
    def shoulder_to_waist(shoulder: float, waist: float) -> float:
        return shoulder / waist

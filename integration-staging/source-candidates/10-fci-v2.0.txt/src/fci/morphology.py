from dataclasses import dataclass
from enum import Enum
from typing import Optional

class BodyShape(Enum):
    HOURGLASS = "hourglass"
    PEAR = "pear"
    RECTANGLE = "rectangle"
    INVERTED_TRIANGLE = "inverted_triangle"
    APPLE = "apple"  # additional common shape

@dataclass(frozen=True)
class BodyMorphology:
    # Height & weight
    height_cm: float
    weight_kg: float
    bmi: Optional[float] = None  # can be computed if not provided

    # Circumferences (cm)
    chest_circumference: Optional[float] = None
    waist_circumference: Optional[float] = None
    hip_circumference: Optional[float] = None
    neck_circumference: Optional[float] = None
    thigh_circumference: Optional[float] = None
    calf_circumference: Optional[float] = None
    arm_circumference: Optional[float] = None
    forearm_circumference: Optional[float] = None

    # Lengths (cm)
    arm_length: Optional[float] = None
    forearm_length: Optional[float] = None
    leg_length: Optional[float] = None
    torso_length: Optional[float] = None
    shoulder_width: Optional[float] = None

    # Ratios (often derived, can be stored for convenience)
    shoulder_waist_ratio: Optional[float] = None
    waist_hip_ratio: Optional[float] = None
    limb_torso_ratio: Optional[float] = None

    # Body shape classification (from measurements or external input)
    body_shape: Optional[BodyShape] = None

    # Weight distribution (optional)
    visceral_fat_index: Optional[float] = None   # 0-1 or other scale
    subcutaneous_fat_distribution: Optional[float] = None

    def __post_init__(self):
        # Auto‑compute BMI if not provided
        if self.bmi is None and self.height_cm > 0 and self.weight_kg > 0:
            height_m = self.height_cm / 100
            object.__setattr__(self, 'bmi', self.weight_kg / (height_m * height_m))

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

class FitzpatrickType(Enum):
    I = 1   # Pale white skin, always burns, never tans
    II = 2  # Fair skin, usually burns, tans minimally
    III = 3 # Medium white skin, sometimes burns, tans uniformly
    IV = 4  # Olive/light brown skin, rarely burns, tans easily
    V = 5   # Brown skin, very rarely burns, tans very easily
    VI = 6  # Dark brown/black skin, never burns

class Undertone(Enum):
    WARM = "warm"
    COOL = "cool"
    NEUTRAL = "neutral"
    OLIVE = "olive"

class DermatologicalCondition(Enum):
    ACNE = "acne"
    ECZEMA = "eczema"
    DERMATITIS = "dermatitis"
    ROSACEA = "rosacea"
    HYPERPIGMENTATION = "hyperpigmentation"
    VITILIGO = "vitiligo"
    ALBINISM = "albinism"
    NONE = "none"

@dataclass(frozen=True)
class SkinProfile:
    # Skin tone
    fitzpatrick_type: FitzpatrickType
    undertone: Undertone
    ita_angle: Optional[float] = None          # Individual Typology Angle (degrees)
    colorimetric_class: Optional[str] = None   # e.g., "light", "medium", "dark"

    # Pigmentation
    melanin_density: Optional[float] = None    # 0-1 scale
    eumelanin_ratio: Optional[float] = None    # 0-1 (eumelanin vs pheomelanin)
    melanin_distribution_uniformity: Optional[float] = None  # 0-1

    # Texture
    pore_density: Optional[float] = None       # pores per cm²
    wrinkle_depth_avg: Optional[float] = None  # mm
    micro_line_topology: Optional[float] = None
    surface_roughness: Optional[float] = None  # Ra value (μm)

    # Skin state
    hydration_level: Optional[float] = None    # 0-1 (moisture index)
    sebum_production: Optional[float] = None   # 0-1 (oiliness)
    elasticity_metrics: Optional[float] = None # 0-1 (firmness)
    barrier_function: Optional[float] = None   # 0-1 (TEWL inverse)

    # Dermatological conditions
    conditions: List[DermatologicalCondition] = None  # active conditions

    # Environmental effects
    uv_exposure_index: Optional[float] = None  # 0-1 (cumulative damage)
    pollution_impact: Optional[float] = None   # 0-1
    humidity_effect: Optional[float] = None    # -1 to 1 (negative = dehydration)

    def __post_init__(self):
        if self.conditions is None:
            object.__setattr__(self, 'conditions', [])

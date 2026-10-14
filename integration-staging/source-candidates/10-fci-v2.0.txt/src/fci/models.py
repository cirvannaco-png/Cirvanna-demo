from dataclasses import dataclass, field
from typing import Optional, Any
from .morphology import BodyMorphology
from .skin import SkinProfile

@dataclass(frozen=True)
class BodyModel:
    bmc: float  # [0,1] – base body model confidence
    morphology: Optional[BodyMorphology] = None  # rich anthropometric data
    skin: Optional[SkinProfile] = None           # skin analysis data

    def __post_init__(self):
        if not 0.0 <= self.bmc <= 1.0:
            raise ValueError("BMC must be in [0,1]")

@dataclass(frozen=True)
class GarmentModel:
    gsr: float                # [0,1] – garment simulation reliability
    price_bucket: int          # categorical, e.g., 0=budget,1=mid,2=premium
    rigidity_index: float      # numeric, higher = more rigid
    # Additional fields for skin‑garment interaction
    fabric_texture: Optional[float] = None       # e.g., roughness (0-1)
    breathability: Optional[float] = None        # e.g., permeability (0-1)
    size_chart: Optional[dict] = None            # brand size chart for this garment

    def __post_init__(self):
        if not 0.0 <= self.gsr <= 1.0:
            raise ValueError("GSR must be in [0,1]")

@dataclass(frozen=True)
class BrandData:
    bfs: float                 # [0,1] – brand fit stability
    brand_volatility: float    # [0,1] – variability of brand's sizing over time

    def __post_init__(self):
        if not 0.0 <= self.bfs <= 1.0:
            raise ValueError("BFS must be in [0,1]")
        if not 0.0 <= self.brand_volatility <= 1.0:
            raise ValueError("brand_volatility must be in [0,1]")

@dataclass(frozen=True)
class UserHistory:
    phfa: float                # [0,1] – personal historical fit accuracy
    user_tolerance_index: float # [0,1] – optional responsiveness to friction

    def __post_init__(self):
        if not 0.0 <= self.phfa <= 1.0:
            raise ValueError("PHFA must be in [0,1]")
        if not 0.0 <= self.user_tolerance_index <= 1.0:
            raise ValueError("user_tolerance_index must be in [0,1]")

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class BodyModel:
    bmc: float  # [0,1]
    def __post_init__(self):
        if not 0.0 <= self.bmc <= 1.0:
            raise ValueError("BMC must be in [0,1]")

@dataclass(frozen=True)
class GarmentModel:
    gsr: float
    price_bucket: int
    rigidity_index: float
    def __post_init__(self):
        if not 0.0 <= self.gsr <= 1.0:
            raise ValueError("GSR must be in [0,1]")

@dataclass(frozen=True)
class BrandData:
    bfs: float
    brand_volatility: float
    def __post_init__(self):
        if not 0.0 <= self.bfs <= 1.0:
            raise ValueError("BFS must be in [0,1]")
        if not 0.0 <= self.brand_volatility <= 1.0:
            raise ValueError("brand_volatility must be in [0,1]")

@dataclass(frozen=True)
class UserHistory:
    phfa: float
    user_tolerance_index: float
    def __post_init__(self):
        if not 0.0 <= self.phfa <= 1.0:
            raise ValueError("PHFA must be in [0,1]")
        if not 0.0 <= self.user_tolerance_index <= 1.0:
            raise ValueError("user_tolerance_index must be in [0,1]")

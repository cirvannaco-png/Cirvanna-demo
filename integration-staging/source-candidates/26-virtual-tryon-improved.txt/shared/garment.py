from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional
from enum import Enum

class FitClass(str, Enum):
    """Garment fit classification"""
    SLIM = "slim"
    REGULAR = "regular"
    RELAXED = "relaxed"
    OVERSIZED = "oversized"

class FabricWeight(str, Enum):
    """Fabric weight classification"""
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"

class PatternDimensions(BaseModel):
    """Garment pattern measurements in cm"""
    chest: float = Field(..., ge=30, le=300)
    waist: float = Field(..., ge=20, le=300)
    hip: float = Field(..., ge=30, le=300)
    shoulder: float = Field(..., ge=20, le=150)
    sleeve_length: float = Field(..., ge=10, le=150)
    length: float = Field(..., ge=20, le=300)

class EaseAllowance(BaseModel):
    """Ease allowance in cm"""
    chest: float = Field(0, ge=-10, le=50)
    waist: float = Field(0, ge=-10, le=50)
    hip: float = Field(0, ge=-10, le=50)

class GarmentDescriptor(BaseModel):
    """Garment Descriptor Object (GDO)"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "garment_id": "G12345",
            "size": "M",
            "pattern_dimensions_cm": {
                "chest": 100, "waist": 78, "hip": 102,
                "shoulder": 46, "sleeve_length": 61, "length": 70
            },
            "stretch_ratio": 0.35,
            "fit_class": "regular",
            "fabric_weight": "medium",
            "ease_allowance_cm": {
                "chest": 2, "waist": 2, "hip": 2
            },
            "optional_CAD_pattern": "G12345.step"
        }
    })
    
    garment_id: str = Field(..., min_length=1, max_length=100)
    size: str = Field(..., min_length=1, max_length=20)
    pattern_dimensions: PatternDimensions
    stretch_ratio: float = Field(..., ge=0, le=2)
    fit_class: FitClass
    fabric_weight: FabricWeight
    ease_allowance: EaseAllowance
    optional_CAD_pattern: Optional[str] = None

    @validator('pattern_dimensions')
    def validate_dimensions(cls, v, values):
        if v.waist > v.chest * 1.1:
            raise ValueError('Waist suspiciously larger than chest')
        return v

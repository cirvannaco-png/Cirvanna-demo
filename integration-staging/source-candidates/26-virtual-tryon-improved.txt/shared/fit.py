from pydantic import BaseModel, Field, ConfigDict

class SizeAdjustment(BaseModel):
    """Recommended size adjustments in cm"""
    chest_cm: float = 0
    waist_cm: float = 0
    hip_cm: float = 0

class RiskHeatmap(BaseModel):
    """Regional risk scores (0-1)"""
    chest: float = Field(..., ge=0, le=1)
    waist: float = Field(..., ge=0, le=1)
    shoulder: float = Field(..., ge=0, le=1)

class FitConfidence(BaseModel):
    """Fit confidence output"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "FP": 0.87,
            "size_adjustment": {"chest_cm": 1.5, "waist_cm": 0.0, "hip_cm": 0.0},
            "MCR": 8.4,
            "OAS": 9.2,
            "movement_risk": 0.3,
            "risk_heatmap": {"chest": 0.7, "waist": 0.2, "shoulder": 0.6},
            "confidence_tier": "A"
        }
    })
    
    FP: float = Field(..., ge=0, le=1, description="Fit Probability")
    size_adjustment: SizeAdjustment
    MCR: float = Field(..., ge=0, le=10, description="Movement Comfort Rating")
    OAS: float = Field(..., ge=0, le=10, description="Occasion Appropriateness")
    movement_risk: float = Field(..., ge=0, le=1, description="Movement risk factor")
    risk_heatmap: RiskHeatmap
    confidence_tier: str = Field(..., regex="^[ABC]$")

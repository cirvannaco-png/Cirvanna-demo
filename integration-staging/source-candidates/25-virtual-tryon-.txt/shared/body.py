from pydantic import BaseModel, Field, validator, ConfigDict
from typing import List, Optional
from enum import Enum

class CameraMetadata(BaseModel):
    """Camera calibration metadata"""
    focal_length_mm: float = Field(..., gt=0, description="Focal length in mm")
    sensor_size_mm: List[float] = Field(
        ..., min_items=2, max_items=2,
        description="Sensor width and height in mm"
    )

    @validator('sensor_size_mm')
    def validate_sensor_size(cls, v):
        if v[0] <= 0 or v[1] <= 0:
            raise ValueError('Sensor dimensions must be positive')
        return v

class BodyCapture(BaseModel):
    """Input schema for body capture request"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "images": ["front.jpg", "side.jpg"],
            "height_cm": 170,
            "camera_metadata": {
                "focal_length_mm": 4.15,
                "sensor_size_mm": [6.3, 4.7]
            },
            "optional_weight_kg": 65
        }
    })

    images: List[str] = Field(
        ..., min_items=2, max_items=3,
        description="Paths to input images"
    )
    height_cm: float = Field(..., ge=50, le=300, description="Height in cm")
    camera_metadata: CameraMetadata
    optional_weight_kg: Optional[float] = Field(
        None, ge=10, le=300,
        description="Optional weight in kg"
    )

    @validator('images')
    def validate_images(cls, v):
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        for img_path in v:
            if not any(img_path.lower().endswith(ext) for ext in valid_extensions):
                raise ValueError(f'Invalid image format: {img_path}')
        return v

class Measurements(BaseModel):
    """Body measurements in cm"""
    chest_cm: float = Field(..., ge=30, le=200)
    waist_cm: float = Field(..., ge=20, le=200)
    hip_cm: float = Field(..., ge=30, le=200)
    shoulder_cm: float = Field(..., ge=20, le=100)
    torso_length_cm: float = Field(..., ge=30, le=100)
    inseam_cm: float = Field(..., ge=30, le=150)
    arm_length_cm: float = Field(..., ge=30, le=100)

class MeasurementUncertainty(BaseModel):
    """Standard deviation for measurements"""
    chest_cm: float = Field(..., ge=0, le=10)
    waist_cm: float = Field(..., ge=0, le=10)
    hip_cm: float = Field(..., ge=0, le=10)

class PostureClass(str, Enum):
    """Posture classification"""
    NEUTRAL = "neutral"
    FORWARD = "forward"
    ATHLETIC = "athletic"
    RELAXED = "relaxed"

class BodyMesh(BaseModel):
    """Output schema from AIS"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "mesh_url": "https://s3.amazonaws.com/cirvanna/meshes/mesh.obj",
            "measurements": {
                "chest_cm": 98.2, "waist_cm": 76.5, "hip_cm": 101.0,
                "shoulder_cm": 45.2, "torso_length_cm": 52.1,
                "inseam_cm": 79.0, "arm_length_cm": 61.2
            },
            "proportion_vector": [0.48, 0.39, 0.13],
            "shoulder_angle_index": 12.5,
            "posture_class": "neutral",
            "measurement_uncertainty": {
                "chest_cm": 0.9, "waist_cm": 1.1, "hip_cm": 1.0
            },
            "confidence_tier": "A"
        }
    })

    id: str = Field(..., description="Unique mesh identifier")
    mesh_url: str = Field(..., description="URL to download mesh file")
    measurements: Measurements
    proportion_vector: List[float] = Field(
        ..., min_items=3, max_items=3,
        description="Body proportions [torso/legs/arms]"
    )
    shoulder_angle_index: float = Field(
        ..., description="Shoulder slope in degrees"
    )
    posture_class: PostureClass
    measurement_uncertainty: MeasurementUncertainty
    confidence_tier: str = Field(
        ..., regex="^[ABC]$",
        description="Confidence tier: A (<1cm), B (1-2cm), C (>2cm)"
    )

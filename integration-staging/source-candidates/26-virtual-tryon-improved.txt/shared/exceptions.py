from typing import Optional, Dict, Any

class CirvannaException(Exception):
    """Base exception for all Cirvanna services"""
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

class AISException(CirvannaException):
    """Anthropometric Intelligence Service exceptions"""
    pass

class LowConfidenceError(AISException):
    """Raised when confidence tier is C"""
    def __init__(
        self,
        message: str = "Low confidence in measurements",
        details: Optional[Dict] = None
    ):
        super().__init__(message, "LOW_CONFIDENCE", 422, details)

class SilhouetteError(AISException):
    """Raised when silhouette cannot be extracted"""
    def __init__(
        self,
        message: str = "Could not extract silhouette from images",
        details: Optional[Dict] = None
    ):
        super().__init__(message, "SILHOUETTE_ERROR", 400, details)

class GSISException(CirvannaException):
    """Garment Structural Intelligence Service exceptions"""
    pass

class InvalidGarmentDataError(GSISException):
    """Raised when garment data validation fails"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "INVALID_GARMENT_DATA", 400, details)

class GarmentNotFoundError(GSISException):
    """Raised when garment ID not found"""
    def __init__(self, garment_id: str):
        super().__init__(
            f"Garment {garment_id} not found",
            "GARMENT_NOT_FOUND",
            404
        )

class DTAEException(CirvannaException):
    """Deformation & Tension Approximation Engine exceptions"""
    pass

class NonFittableGarmentError(DTAEException):
    """Raised when garment cannot fit any body"""
    def __init__(
        self,
        message: str = "Garment dimensions outside feasible range",
        details: Optional[Dict] = None
    ):
        super().__init__(message, "NON_FITTABLE", 400, details)

class FCEException(CirvannaException):
    """Fit Confidence Engine exceptions"""
    pass

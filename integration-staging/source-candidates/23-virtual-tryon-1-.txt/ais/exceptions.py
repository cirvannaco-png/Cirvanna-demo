from shared.exceptions import AISException

class ModelLoadError(AISException):
    """Raised when model fails to load"""
    def __init__(self, message: str):
        super().__init__(message, "MODEL_LOAD_ERROR", 503)

class ProcessingError(AISException):
    """Raised when processing fails"""
    def __init__(self, message: str):
        super().__init__(message, "PROCESSING_ERROR", 500)

class InvalidImageError(AISException):
    """Raised when image is invalid"""
    def __init__(self, message: str):
        super().__init__(message, "INVALID_IMAGE", 400)

class CacheError(AISException):
    """Raised when cache operation fails"""
    def __init__(self, message: str):
        super().__init__(message, "CACHE_ERROR", 500)

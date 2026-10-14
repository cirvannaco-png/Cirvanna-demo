from shared.garment import GarmentDescriptor, FitClass, FabricWeight
from shared.exceptions import InvalidGarmentDataError
from typing import List

class GarmentValidator:
    """Validate garment data with auto-correction"""
    
    VALID_SIZES = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL']
    VALID_FIT_CLASSES = [fc.value for fc in FitClass]
    VALID_FABRIC_WEIGHTS = [fw.value for fw in FabricWeight]
    
    @classmethod
    def validate(cls, gdo: GarmentDescriptor) -> List[str]:
        """
        Run all validations with auto-correction
        
        Returns:
            List of warning messages (if any)
        """
        errors = []
        warnings = []
        
        # Size validation
        if gdo.size not in cls.VALID_SIZES and not gdo.size.replace('.','',1).isdigit():
            warnings.append(f"Unusual size: {gdo.size}")
        
        # Fit class validation
        if gdo.fit_class.value not in cls.VALID_FIT_CLASSES:
            errors.append(f"Invalid fit class: {gdo.fit_class.value}")
        
        # Fabric weight validation
        if gdo.fabric_weight.value not

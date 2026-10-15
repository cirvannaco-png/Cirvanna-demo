from typing import List

from shared.exceptions import InvalidGarmentDataError
from shared.garment import FabricWeight, FitClass, GarmentDescriptor


class GarmentValidator:
    """Validate a garment descriptor and return non-fatal warnings."""

    VALID_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL"]
    VALID_FIT_CLASSES = [fit_class.value for fit_class in FitClass]
    VALID_FABRIC_WEIGHTS = [fabric_weight.value for fabric_weight in FabricWeight]

    @classmethod
    def validate(cls, gdo: GarmentDescriptor) -> List[str]:
        """Validate the descriptor, raising for invalid fields and returning warnings."""
        errors: List[str] = []
        warnings: List[str] = []

        if (
            gdo.size not in cls.VALID_SIZES
            and not gdo.size.replace(".", "", 1).isdigit()
        ):
            warnings.append(f"Unusual size: {gdo.size}")

        if gdo.fit_class.value not in cls.VALID_FIT_CLASSES:
            errors.append(f"Invalid fit class: {gdo.fit_class.value}")

        if gdo.fabric_weight.value not in cls.VALID_FABRIC_WEIGHTS:
            errors.append(f"Invalid fabric weight: {gdo.fabric_weight.value}")

        if errors:
            raise InvalidGarmentDataError(
                "Garment validation failed: " + "; ".join(errors),
                details={"errors": errors},
            )

        return warnings

"""
Skin biology: layers, melanin types.
"""
from enum import Enum

class SkinLayer(Enum):
    EPIDERMIS = "epidermis"
    DERMIS = "dermis"
    HYPODERMIS = "hypodermis"

class MelaninType(Enum):
    EUMELANIN = "eumelanin"
    PHEOMELANIN = "pheomelanin"

class SkinBiology:
    @staticmethod
    def get_layer_description(layer: SkinLayer) -> str:
        descriptions = {
            SkinLayer.EPIDERMIS: "Outer layer containing melanocytes, keratinocytes.",
            SkinLayer.DERMIS: "Middle layer with collagen, elastin, blood vessels.",
            SkinLayer.HYPODERMIS: "Subcutaneous fat layer."
        }
        return descriptions.get(layer, "")

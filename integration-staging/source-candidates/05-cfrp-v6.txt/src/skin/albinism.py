"""
Albinism genetic phenotype classification.
"""
from enum import Enum

class AlbinismType(Enum):
    OCA1 = "OCA1"
    OCA2 = "OCA2"
    OCA3 = "OCA3"
    OCA4 = "OCA4"

class AlbinismDetector:
    @staticmethod
    def is_albinism(skin_tone_features: Dict) -> bool:
        melanin_density = skin_tone_features.get('melanin_density', 1.0)
        return melanin_density < 0.1

    @staticmethod
    def classify_type(genetic_data: Dict) -> AlbinismType:
        if genetic_data.get('TYR_mutation'):
            return AlbinismType.OCA1
        elif genetic_data.get('OCA2_mutation'):
            return AlbinismType.OCA2
        elif genetic_data.get('TYRP1_mutation'):
            return AlbinismType.OCA3
        elif genetic_data.get('SLC45A2_mutation'):
            return AlbinismType.OCA4
        return AlbinismType.OCA1

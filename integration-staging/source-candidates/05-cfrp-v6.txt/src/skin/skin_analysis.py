"""
Main skin analysis class integrating all modules.
"""
import numpy as np
from typing import Dict, Any

from src.skin.skin_tone import SkinToneAnalyzer, FitzpatrickType, MonkSkinTone
from src.skin.undertone import UndertoneAnalyzer, Undertone
from src.skin.texture import TextureAnalyzer
from src.skin.conditions import ConditionAnalyzer, SkinCondition
from src.skin.albinism import AlbinismDetector, AlbinismType

class SkinAnalysisResult:
    def __init__(self):
        self.fitzpatrick: FitzpatrickType = None
        self.monk: MonkSkinTone = None
        self.undertone: Undertone = None
        self.pore_density: float = 0.0
        self.wrinkle_depth: float = 0.0
        self.roughness: float = 0.0
        self.conditions: Dict[SkinCondition, float] = {}
        self.is_albinism: bool = False
        self.albinism_type: AlbinismType = None

class SkinAnalyzer:
    def __init__(self):
        self.tone_analyzer = SkinToneAnalyzer()
        self.undertone_analyzer = UndertoneAnalyzer()
        self.texture_analyzer = TextureAnalyzer()
        self.condition_analyzer = ConditionAnalyzer()
        self.albinism_detector = AlbinismDetector()

    async def analyze(self, image: np.ndarray) -> SkinAnalysisResult:
        result = SkinAnalysisResult()

        # Convert RGB to LAB for tone analysis
        # (simplified; real conversion would use cv2.cvtColor)
        lab = image  # placeholder

        result.fitzpatrick = self.tone_analyzer.estimate_fitzpatrick_from_lab(lab)
        result.monk = self.tone_analyzer.estimate_monk_from_rgb(image)
        result.undertone = self.undertone_analyzer.classify_from_rgb(image)

        gray = np.dot(image[...,:3], [0.299, 0.587, 0.114])
        result.pore_density = self.texture_analyzer.pore_density(gray)
        result.wrinkle_depth = self.texture_analyzer.wrinkle_depth(gray)
        result.roughness = self.texture_analyzer.surface_roughness(gray)

        result.conditions = self.condition_analyzer.detect_conditions(image)

        melanin_density = 1.0 - (result.fitzpatrick.value / 6.0)  # rough estimate
        result.is_albinism = self.albinism_detector.is_albinism({'melanin_density': melanin_density})
        if result.is_albinism:
            result.albinism_type = AlbinismType.OCA1  # placeholder

        return result

"""
Enhanced skin analyzer using computer vision models.
Integrates segmentation, tone classification, texture analysis, condition detection, phenotype recognition,
environmental effects, and AI feature variables.
"""
import asyncio
import time
import concurrent.futures
import numpy as np
import cv2
from typing import Dict, List, Optional, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import XyraConfig
from .ingredient_analyzer import IngredientAnalyzer, SkinType
from .segmentation import SkinSegmenter
from .classification import (
    SkinToneClassifier, UndertoneClassifier, AlbinismDetector,
    PigmentationAnalyzer, GeneticPhenotypeDetector, EnvironmentalEffectAnalyzer
)
from .condition_detection import ConditionDetector
from .texture_analysis import TextureAnalyzer
from .ai_features import AIFeatureExtractor

class FastSkinAnalyzer:
    """
    High-performance skin analyzer with predictive caching and multi‑model fusion.
    """
    def __init__(self, config: XyraConfig):
        self.config = config
        self.ingredient_analyzer = IngredientAnalyzer()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_ML)

        # Load models (lazy loading on first use)
        self.segmenter = None
        self.tone_classifier = None
        self.undertone_classifier = None
        self.albinism_detector = None
        self.condition_detector = None
        self.texture_analyzer = None
        self.pigmentation_analyzer = None
        self.genetic_detector = None
        self.environmental_analyzer = None
        self.ai_feature_extractor = None

        # Predictive cache for common skin type + ingredient combinations
        self.predictive_cache = {}
        self._warm_predictive_cache()

    def _load_models(self):
        """Lazy-load all models (called on first image analysis)."""
        if self.segmenter is None:
            self.segmenter = SkinSegmenter(self.config)
            self.tone_classifier = SkinToneClassifier(self.config)
            self.undertone_classifier = UndertoneClassifier(self.config)
            self.albinism_detector = AlbinismDetector(self.config)
            self.condition_detector = ConditionDetector(self.config)
            self.texture_analyzer = TextureAnalyzer(self.config)
            self.pigmentation_analyzer = PigmentationAnalyzer(self.config)
            self.genetic_detector = GeneticPhenotypeDetector(self.config)
            self.environmental_analyzer = EnvironmentalEffectAnalyzer(self.config)
            self.ai_feature_extractor = AIFeatureExtractor(self.config)

    def _warm_predictive_cache(self):
        common_skin_types = [SkinType.DRY, SkinType.OILY, SkinType.COMBINATION]
        common_ingredients = [
            ["hyaluronic_acid", "ceramides"],
            ["salicylic_acid", "niacinamide"],
            ["hyaluronic_acid", "niacinamide"]
        ]
        scores = self.ingredient_analyzer.analyze_batch(common_skin_types, common_ingredients)
        for i, skin_type in enumerate(common_skin_types):
            for j, ingredients in enumerate(common_ingredients):
                key = (skin_type, tuple(sorted(ingredients)))
                self.predictive_cache[key] = scores[i, j]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1))
    async def analyze(self,
                      skin_type: Optional[str] = None,
                      ingredients: Optional[List[str]] = None,
                      image_data: Optional[bytes] = None,
                      metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Perform full skin analysis, including all dimensions.
        """
        start_time = time.perf_counter()
        ingredients = ingredients or []
        metadata = metadata or {}

        # Predictive cache for ingredient compatibility only (if no image and skin_type given)
        if not image_data and skin_type:
            try:
                skin_type_enum = SkinType[skin_type.upper()]
            except KeyError:
                skin_type_enum = SkinType.NORMAL
            cache_key = (skin_type_enum, tuple(sorted(ingredients)))
            if cache_key in self.predictive_cache:
                elapsed = (time.perf_counter() - start_time) * 1000
                return {
                    "compatibility": self.predictive_cache[cache_key],
                    "method": "predictive_cache",
                    "elapsed_ms": elapsed,
                    "confidence": 0.7
                }

        # If no image, fall back to rule‑based analysis
        if image_data is None:
            result = await self._rule_based_analysis(skin_type, ingredients, metadata)
            elapsed = (time.perf_counter() - start_time) * 1000
            result["elapsed_ms"] = elapsed
            result["method"] = "rule_based"
            return result

        # Load models if needed
        self._load_models()

        # Decode image
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image data")

        # Run segmentation first to get mask for tone classifier (for ITA)
        seg_mask = await asyncio.get_event_loop().run_in_executor(self.executor, self.segmenter.segment, img)

        # Run all other analyses in parallel
        loop = asyncio.get_event_loop()
        tasks = {
            "tone": loop.run_in_executor(self.executor, lambda: self.tone_classifier.predict(img, seg_mask)),
            "undertone": loop.run_in_executor(self.executor, self.undertone_classifier.predict, img),
            "albinism": loop.run_in_executor(self.executor, self.albinism_detector.predict, img),
            "conditions": loop.run_in_executor(self.executor, self.condition_detector.predict, img),
            "texture": loop.run_in_executor(self.executor, self.texture_analyzer.analyze, img),
            "pigmentation": loop.run_in_executor(self.executor, self.pigmentation_analyzer.analyze, img),
            "genetic": loop.run_in_executor(self.executor, self.genetic_detector.predict, img),
            "environmental": loop.run_in_executor(self.executor, lambda: self.environmental_analyzer.analyze(img, metadata)),
            "ai_features": loop.run_in_executor(self.executor, self.ai_feature_extractor.extract, img)
        }

        # Wait for all with timeout
        try:
            tone_result = await tasks["tone"]
            undertone_result = await tasks["undertone"]
            albinism_result = await tasks["albinism"]
            conditions_result = await tasks["conditions"]
            texture_result = await tasks["texture"]
            pigmentation_result = await tasks["pigmentation"]
            genetic_result = await tasks["genetic"]
            environmental_result = await tasks["environmental"]
            ai_features = await tasks["ai_features"]
        except Exception as e:
            # Fallback to rule‑based on partial results
            result = await self._rule_based_analysis(skin_type, ingredients, metadata)
            elapsed = (time.perf_counter() - start_time) * 1000
            result["elapsed_ms"] = elapsed
            result["method"] = "timeout_fallback"
            return result

        # Handle exceptions in individual results
        if isinstance(tone_result, Exception):
            tone_result = {"fitzpatrick": 3, "monk": 5, "ita": 0.0, "confidence": 0.5}
        if isinstance(undertone_result, Exception):
            undertone_result = {
                "warm_bias": 0.5, "cool_bias": 0.5, "neutral_balance": 0.5,
                "olive_bias": 0.0, "golden_bias": 0.0, "red_hemoglobin_visibility": 0.5,
                "carotene_presence": 0.0, "ash_undertone": 0.0, "blood_perfusion_tone": 0.5
            }
        if isinstance(albinism_result, Exception):
            albinism_result = {"albinism": False, "confidence": 0.0}
        if isinstance(conditions_result, Exception):
            conditions_result = []
        if isinstance(texture_result, Exception):
            texture_result = {
                "pore_density": 0, "pore_diameter": 0, "pore_distribution": 0,
                "surface_roughness_ra": 0, "surface_roughness_rz": 0,
                "wrinkle_count": 0, "wrinkle_depth": 0, "fine_line_density": 0,
                "micro_line_topology": 0, "elasticity": 0, "firmness": 0,
                "resilience": 0, "microrelief_pattern": 0, "smoothness": 0,
                "sebum_level": 0, "oil_distribution": 0,
                "dry_patch_density": 0, "skin_flake_density": 0
            }
        if isinstance(pigmentation_result, Exception):
            pigmentation_result = {
                "melanin_density": 0.5, "eumelanin_ratio": 0.5, "pheomelanin_ratio": 0.5,
                "melanocyte_activity": 0.5, "pigment_dispersion": 0.5,
                "melanosome_size": 0.5, "melanosome_distribution": 0.5,
                "epidermal_pigmentation": 0.5, "dermal_pigmentation": 0.5,
                "freckle_density": 0, "hyperpigmentation_clusters": 0,
                "hypopigmentation_regions": 0, "vitiligo_markers": 0,
                "sunspot_density": 0, "age_spot_density": 0,
                "pigment_uniformity": 0.5, "pigment_contrast": 0.5,
                "pigment_gradient": 0.5, "pigmentation_disorders": []
            }
        if isinstance(genetic_result, Exception):
            genetic_result = {
                "albinism": False, "vitiligo": False,
                "genetic_pigmentation_diversity": 0.5,
                "confidence": 0.0
            }
        if isinstance(environmental_result, Exception):
            environmental_result = {
                "uv_exposure_index": 0.0,
                "pollution_impact": 0.0,
                "humidity_effect": 0.0,
                "confidence": 0.0
            }
        if isinstance(ai_features, Exception):
            ai_features = {
                "color_histogram": [],
                "texture_map": [],
                "spectral_reflectance": []
            }

        # Determine skin type from tone and conditions
        inferred_skin_type = self._infer_skin_type(tone_result, conditions_result)
        if skin_type is None:
            skin_type = inferred_skin_type

        # Compute ingredient compatibility if ingredients provided
        compatibility = 0.5
        if ingredients and skin_type:
            try:
                skin_type_enum = SkinType[skin_type.upper()]
            except KeyError:
                skin_type_enum = SkinType.NORMAL
            scores = self.ingredient_analyzer.analyze_batch([skin_type_enum], [ingredients])
            compatibility = float(scores[0, 0])

        # Overall confidence (average of component confidences)
        confidences = [
            tone_result.get("confidence", 0.5),
            texture_result.get("confidence", 0.5),
            pigmentation_result.get("confidence", 0.5),
            albinism_result.get("confidence", 0.5),
            genetic_result.get("confidence", 0.5),
            environmental_result.get("confidence", 0.5)
        ]
        overall_confidence = float(np.mean(confidences))

        elapsed = (time.perf_counter() - start_time) * 1000

        return {
            "skin_type": skin_type,
            "fitzpatrick": tone_result.get("fitzpatrick", 3),
            "monk_tone": tone_result.get("monk", 5),
            "ita": tone_result.get("ita", 0.0),
            "undertone": undertone_result,
            "pigmentation": pigmentation_result,
            "texture": texture_result,
            "conditions": conditions_result,
            "genetic": genetic_result,
            "environmental": environmental_result,
            "ai_features": ai_features,
            "compatibility": compatibility,
            "confidence": overall_confidence,
            "method": "full_ml",
            "elapsed_ms": elapsed
        }

    async def _rule_based_analysis(self, skin_type: Optional[str], ingredients: List[str],
                                   metadata: Dict) -> Dict[str, Any]:
        if skin_type is None:
            skin_type = "NORMAL"
        try:
            skin_type_enum = SkinType[skin_type.upper()]
        except KeyError:
            skin_type_enum = SkinType.NORMAL

        ingredient_set = set(ingredients)
        score = 0.5
        if skin_type_enum == SkinType.SENSITIVE and "fragrance" in ingredient_set:
            score = 0.1
        elif skin_type_enum == SkinType.DRY and "hyaluronic_acid" in ingredient_set:
            score = 0.8
        elif skin_type_enum == SkinType.OILY and "salicylic_acid" in ingredient_set:
            score = 0.8

        return {
            "skin_type": skin_type,
            "fitzpatrick": 3,
            "monk_tone": 5,
            "ita": 0.0,
            "undertone": {
                "warm_bias": 0.5, "cool_bias": 0.5, "neutral_balance": 0.5,
                "olive_bias": 0.0, "golden_bias": 0.0, "red_hemoglobin_visibility": 0.5,
                "carotene_presence": 0.0, "ash_undertone": 0.0, "blood_perfusion_tone": 0.5
            },
            "pigmentation": {
                "melanin_density": 0.5, "eumelanin_ratio": 0.5, "pheomelanin_ratio": 0.5,
                "melanocyte_activity": 0.5, "pigment_dispersion": 0.5,
                "melanosome_size": 0.5, "melanosome_distribution": 0.5,
                "epidermal_pigmentation": 0.5, "dermal_pigmentation": 0.5,
                "freckle_density": 0, "hyperpigmentation_clusters": 0,
                "hypopigmentation_regions": 0, "vitiligo_markers": 0,
                "sunspot_density": 0, "age_spot_density": 0,
                "pigment_uniformity": 0.5, "pigment_contrast": 0.5,
                "pigment_gradient": 0.5, "pigmentation_disorders": []
            },
            "texture": {
                "pore_density": 0, "pore_diameter": 0, "pore_distribution": 0,
                "surface_roughness_ra": 0, "surface_roughness_rz": 0,
                "wrinkle_count": 0, "wrinkle_depth": 0, "fine_line_density": 0,
                "micro_line_topology": 0, "elasticity": 0, "firmness": 0,
                "resilience": 0, "microrelief_pattern": 0, "smoothness": 0,
                "sebum_level": 0, "oil_distribution": 0,
                "dry_patch_density": 0, "skin_flake_density": 0,
                "confidence": 0.0
            },
            "conditions": [],
            "genetic": {
                "albinism": False, "vitiligo": False,
                "genetic_pigmentation_diversity": 0.5,
                "confidence": 0.0
            },
            "environmental": {
                "uv_exposure_index": metadata.get("uv_index", 0.0),
                "pollution_impact": metadata.get("pollution", 0.0),
                "humidity_effect": metadata.get("humidity", 0.0),
                "confidence": 0.0
            },
            "ai_features": {
                "color_histogram": [],
                "texture_map": [],
                "spectral_reflectance": []
            },
            "compatibility": score,
            "confidence": 0.5,
            "method": "rule_based"
        }

    def _infer_skin_type(self, tone_result: Dict, conditions: List) -> str:
        fitz = tone_result.get("fitzpatrick", 3)
        if fitz <= 2:
            return "SENSITIVE"
        elif fitz >= 5:
            return "OILY"
        for cond in conditions:
            if cond.get("condition") == "acne" and cond.get("confidence", 0) > 0.6:
                return "OILY"
            if cond.get("condition") == "dryness" and cond.get("confidence", 0) > 0.6:
                return "DRY"
        return "NORMAL"

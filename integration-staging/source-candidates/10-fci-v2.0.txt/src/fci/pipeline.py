import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .models import BodyModel, GarmentModel, BrandData, UserHistory
from .bayesian import BayesianLayer
from .neural import NeuralResidual
from .calibration import FastCalibrator
from .friction import FrictionPolicy, RuleBasedFrictionPolicy, FrictionAction
from .metrics import MetricsCollector, InMemoryMetricsCollector

logger = logging.getLogger("FCI")

class FitConfidenceIndex:
    def __init__(self,
                 structural_weights: Tuple[float, float, float, float] = (0.3, 0.25, 0.25, 0.2),
                 bayesian: Optional[BayesianLayer] = None,
                 neural_residual: Optional[NeuralResidual] = None,
                 calibrator: Optional[FastCalibrator] = None,
                 friction_policy: Optional[FrictionPolicy] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        self.structural_weights = structural_weights
        self.bayesian = bayesian or BayesianLayer()
        self.neural = neural_residual
        self.calibrator = calibrator
        self.friction = friction_policy or RuleBasedFrictionPolicy()
        self.metrics = metrics_collector or InMemoryMetricsCollector()

    def _extract_morphology_features(self, morphology) -> Dict[str, float]:
        """Convert BodyMorphology to a flat dict of numeric features."""
        if morphology is None:
            return {}
        features = {}
        # Include key numeric fields; skip None and non‑numeric (like body_shape)
        for field in ['height_cm', 'weight_kg', 'bmi', 'chest_circumference', 'waist_circumference',
                      'hip_circumference', 'neck_circumference', 'thigh_circumference', 'calf_circumference',
                      'arm_circumference', 'forearm_circumference', 'arm_length', 'forearm_length',
                      'leg_length', 'torso_length', 'shoulder_width', 'shoulder_waist_ratio',
                      'waist_hip_ratio', 'limb_torso_ratio', 'visceral_fat_index', 'subcutaneous_fat_distribution']:
            val = getattr(morphology, field, None)
            if val is not None:
                features[f"morph_{field}"] = val
        # Include body shape as one‑hot? For now just add a categorical index if needed.
        if morphology.body_shape:
            features["morph_body_shape"] = morphology.body_shape.value  # string; neural model may need encoding
        return features

    def _extract_skin_features(self, skin) -> Dict[str, float]:
        """Convert SkinProfile to a flat dict of numeric features."""
        if skin is None:
            return {}
        features = {}
        # Fitzpatrick type as int
        if skin.fitzpatrick_type:
            features["skin_fitzpatrick"] = skin.fitzpatrick_type.value
        # Undertone as categorical – for simplicity, use one‑hot or index
        if skin.undertone:
            features["skin_undertone"] = skin.undertone.value  # string; needs encoding
        # Numeric fields
        for field in ['ita_angle', 'melanin_density', 'eumelanin_ratio', 'melanin_distribution_uniformity',
                      'pore_density', 'wrinkle_depth_avg', 'micro_line_topology', 'surface_roughness',
                      'hydration_level', 'sebum_production', 'elasticity_metrics', 'barrier_function',
                      'uv_exposure_index', 'pollution_impact', 'humidity_effect']:
            val = getattr(skin, field, None)
            if val is not None:
                features[f"skin_{field}"] = val
        # Conditions: count or flags
        if skin.conditions:
            # For simplicity, create a binary flag for each condition (but that could blow up feature space)
            # Here we just count the number of conditions.
            features["skin_condition_count"] = len(skin.conditions)
        return features

    def predict(self,
                body: BodyModel,
                garment: GarmentModel,
                brand: BrandData,
                user: UserHistory,
                category: str,
                brand_name: str,
                user_id: str,
                extra_features: Optional[Dict[str, Any]] = None,
                prediction_id: Optional[str] = None) -> Dict[str, Any]:
        """Run FCI pipeline and return result."""
        try:
            w1, w2, w3, w4 = self.structural_weights
            s_struct = w1 * body.bmc + w2 * garment.gsr + w3 * brand.bfs + w4 * user.phfa
            s_struct = np.clip(s_struct, 0.0, 1.0)

            s_bayes = self.bayesian.predict(category, brand_name, user_id)

            delta = 0.0
            if self.neural is not None:
                features = {
                    "bmc": body.bmc,
                    "gsr": garment.gsr,
                    "bfs": brand.bfs,
                    "phfa": user.phfa,
                    "s_struct": s_struct,
                    "s_bayes": s_bayes,
                    "price_bucket": garment.price_bucket,
                    "rigidity": garment.rigidity_index,
                    "brand_volatility": brand.brand_volatility,
                    "user_tolerance": user.user_tolerance_index,
                }
                # Add optional garment fields
                if garment.fabric_texture is not None:
                    features["fabric_texture"] = garment.fabric_texture
                if garment.breathability is not None:
                    features["breathability"] = garment.breathability
                # Add morphology and skin features if available
                if body.morphology:
                    features.update(self._extract_morphology_features(body.morphology))
                if body.skin:
                    features.update(self._extract_skin_features(body.skin))
                if extra_features:
                    features.update(extra_features)
                delta = self.neural.predict(features)
            s_hybrid = np.clip(s_bayes + delta, 0.0, 1.0)

            if self.calibrator is not None:
                fci_calibrated = self.calibrator.predict_proba(np.array([s_hybrid]))[0]
                ci_lower, ci_upper = self.calibrator.confidence_interval(np.array([s_hybrid]))
                ci_lower, ci_upper = ci_lower[0], ci_upper[0]
            else:
                fci_calibrated = s_hybrid
                ci_lower, ci_upper = s_hybrid - 0.05, s_hybrid + 0.05
                ci_lower, ci_upper = np.clip([ci_lower, ci_upper], 0.0, 1.0)

            fci_final = fci_calibrated
            if body.bmc < 0.6:
                fci_final = min(fci_final, 0.75)
            if garment.gsr < 0.5:
                fci_final = min(fci_final, 0.70)

            state = {
                "fci": fci_final,
                "ci_width": ci_upper - ci_lower,
                "bmc": body.bmc,
                "gsr": garment.gsr,
                "price": garment.price_bucket,
                "brand_volatility": brand.brand_volatility,
                "rigidity": garment.rigidity_index,
                "user_tolerance": user.user_tolerance_index,
            }
            action = self.friction.choose_action(state)

            result = {
                "prediction_id": prediction_id,
                "bmc": body.bmc,
                "gsr": garment.gsr,
                "bfs": brand.bfs,
                "phfa": user.phfa,
                "s_struct": s_struct,
                "s_bayes": s_bayes,
                "delta_residual": delta,
                "s_hybrid": s_hybrid,
                "fci_calibrated": fci_calibrated,
                "fci_final": fci_final,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "ci_width": ci_upper - ci_lower,
                "friction_action": int(action),
                "friction_action_name": action.name,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if prediction_id:
                self.metrics.add_prediction(prediction_id, result)

            logger.info(f"FCI final: {fci_final:.4f}, action: {action.name}")
            return result
        except Exception as e:
            logger.exception("FCI prediction failed")
            return {"prediction_id": prediction_id, "error": str(e), "fci_final": 0.5, "friction_action": 2}

    def record_outcome(self, prediction_id: str, fit_success: bool, return_reason: Optional[str] = None):
        self.metrics.add_outcome(prediction_id, fit_success, return_reason)
        logger.info(f"Outcome recorded: id={prediction_id}, success={fit_success}, reason={return_reason}")

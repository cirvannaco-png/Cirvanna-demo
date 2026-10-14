import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .models import BodyModel, GarmentModel, BrandData, UserHistory
from .bayesian import BayesianLayer
from .neural import NeuralResidual
from .calibration import FastCalibrator
from .friction import FrictionPolicy, RuleBasedFrictionPolicy
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

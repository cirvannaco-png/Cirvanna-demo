import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("FCI")

class NeuralResidual:
    """Wraps any sklearn‑compatible regressor and caps output to ±0.1."""
    def __init__(self, model: Any, feature_names: List[str]):
        self.model = model
        self.feature_names = feature_names

    def predict(self, features: Dict[str, Any]) -> float:
        try:
            X = np.array([[features[name] for name in self.feature_names]])
            residual = self.model.predict(X)[0]
        except Exception as e:
            logger.error(f"Neural residual failed: {e}")
            residual = 0.0
        return max(-0.1, min(0.1, float(residual)))

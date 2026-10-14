from enum import IntEnum
from typing import Dict, Any, Optional, List
import numpy as np
import logging

logger = logging.getLogger("FCI")

class FrictionAction(IntEnum):
    AUTO_CONFIRM = 0
    RECOMMEND_ONLY = 1
    SUGGEST_ALTERNATIVE = 2
    SUGGEST_RECALIBRATION = 3
    REQUIRE_RECAPTURE = 4

class FrictionPolicy:
    """Base class for friction policy."""
    def choose_action(self, state: Dict[str, Any]) -> FrictionAction:
        raise NotImplementedError

    def update(self, state: Dict[str, Any], action: FrictionAction, reward: float):
        """Online learning update (optional)."""
        pass

class RuleBasedFrictionPolicy(FrictionPolicy):
    """Rule‑based policy with guardrails."""
    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        self.thresholds = thresholds or {
            "fci_high": 0.8,
            "fci_medium": 0.65,
            "bmc_low": 0.6,
            "gsr_low": 0.5
        }

    def choose_action(self, state: Dict[str, Any]) -> FrictionAction:
        if state["gsr"] < self.thresholds["gsr_low"]:
            return FrictionAction.SUGGEST_RECALIBRATION
        if state["bmc"] < self.thresholds["bmc_low"]:
            return FrictionAction.SUGGEST_ALTERNATIVE
        fci = state["fci"]
        if fci >= self.thresholds["fci_high"]:
            return FrictionAction.AUTO_CONFIRM
        elif fci >= self.thresholds["fci_medium"]:
            return FrictionAction.RECOMMEND_ONLY
        else:
            return FrictionAction.SUGGEST_ALTERNATIVE

class BanditFrictionPolicy(FrictionPolicy):
    """
    Simple epsilon‑greedy contextual bandit.
    For each state (feature vector), it learns a separate linear model for each action.
    """
    def __init__(self, feature_names: List[str], epsilon: float = 0.1, alpha: float = 1.0):
        self.feature_names = feature_names
        self.epsilon = epsilon
        self.alpha = alpha  # prior strength
        # For each action, store (theta, cov_inv) for online linear regression
        # Using ridge regression incremental update
        self.dim = len(feature_names)
        self.theta = {a: np.zeros(self.dim) for a in FrictionAction}
        self.cov_inv = {a: np.eye(self.dim) / alpha for a in FrictionAction}  # precision matrix
        self._rng = np.random.RandomState(42)

    def _extract_features(self, state: Dict[str, Any]) -> np.ndarray:
        """Convert state dict to feature vector (order must match feature_names)."""
        return np.array([state[name] for name in self.feature_names])

    def choose_action(self, state: Dict[str, Any]) -> FrictionAction:
        # Guardrails override
        if state["gsr"] < 0.5:
            return FrictionAction.SUGGEST_RECALIBRATION
        if state["bmc"] < 0.6:
            return FrictionAction.SUGGEST_ALTERNATIVE

        if self._rng.rand() < self.epsilon:
            # explore
            return self._rng.choice(list(FrictionAction))
        else:
            # exploit: pick action with highest predicted reward
            x = self._extract_features(state)
            best_action = None
            best_value = -np.inf
            for a in FrictionAction:
                # predicted reward = theta[a].dot(x)
                value = self.theta[a].dot(x)
                if value > best_value:
                    best_value = value
                    best_action = a
            return best_action

    def update(self, state: Dict[str, Any], action: FrictionAction, reward: float):
        """Online update using ridge regression (incremental)."""
        x = self._extract_features(state).reshape(-1, 1)
        # Update covariance inverse (Woodbury)
        # cov_inv_new = cov_inv - (cov_inv @ x @ x.T @ cov_inv) / (1 + x.T @ cov_inv @ x)
        # But for simplicity, we can just do batch retraining periodically.
        # For demo, we'll do a simple gradient step:
        # theta = theta + learning_rate * (reward - theta.dot(x)) * x
        # But a more realistic implementation would use a proper online learner.
        # Here we'll just use a placeholder.
        logger.info(f"Bandit update: action={action}, reward={reward} (no‑op in demo)")

    def train_offline(self, historical_data: List[Tuple[Dict[str, Any], FrictionAction, float]]):
        """
        Train the bandit using historical (state, action, reward) tuples.
        This could use any supervised learning method (e.g., train a reward predictor per action).
        Placeholder.
        """
        # In reality, you would train a model to predict reward given (state, action)
        pass

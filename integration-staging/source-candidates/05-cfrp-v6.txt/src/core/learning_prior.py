"""
LearningPrior – Hierarchical learning priors.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional

@dataclass
class LearningPrior:
    global_prior: np.ndarray = field(default_factory=lambda: np.array([0.5]))
    segment_prior: np.ndarray = field(default_factory=lambda: np.array([0.5]))
    user_posterior: np.ndarray = field(default_factory=lambda: np.array([0.5]))

    ALPHA_RANGE = (0.4, 0.8)
    BETA_RANGE = (0.1, 0.4)
    GAMMA_RANGE = (0.05, 0.2)

    @classmethod
    def compute_posterior(cls, user_posterior: np.ndarray,
                          segment_prior: Optional[np.ndarray] = None,
                          global_prior: Optional[np.ndarray] = None,
                          conflict_threshold: float = 0.3) -> Tuple[np.ndarray, Dict[str, float]]:
        if segment_prior is None:
            segment_prior = np.array([0.5])
        if global_prior is None:
            global_prior = np.array([0.5])

        has_conflict = False
        if np.abs(user_posterior[0] - segment_prior[0]) > conflict_threshold:
            has_conflict = True

        if has_conflict or segment_prior is None:
            alpha = 0.7
            beta = 0.2
            gamma = 0.1
        else:
            alpha = 0.6
            beta = 0.3
            gamma = 0.1

        total = alpha + beta + gamma
        alpha, beta, gamma = alpha/total, beta/total, gamma/total

        posterior = (alpha * user_posterior + beta * segment_prior + gamma * global_prior)
        posterior = np.clip(posterior, 0, 1)

        metadata = {
            'alpha': alpha,
            'beta': beta,
            'gamma': gamma,
            'has_conflict': has_conflict,
            'learning_rate_multiplier': 0.5 if has_conflict else 1.0
        }
        return posterior, metadata

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.neighbors import NearestNeighbors
from typing import Tuple

class FastCalibrator:
    """
    Calibrates raw scores using isotonic regression.
    Confidence intervals are approximated using the variance of the
    k‑nearest training scores (local binomial variance).
    """
    def __init__(self, k: int = 50, method: str = "isotonic"):
        self.k = k
        self.method = method
        self.isotonic = None
        self.X_train = None
        self.y_train = None
        self.nn = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        """X: raw scores (n_samples,), y: binary labels."""
        X = X.ravel()
        self.isotonic = IsotonicRegression(out_of_bounds="clip")
        self.isotonic.fit(X, y)
        # Store training data for nearest neighbor search
        self.X_train = X.reshape(-1, 1)
        self.y_train = y
        self.nn = NearestNeighbors(n_neighbors=min(self.k, len(X)))
        self.nn.fit(self.X_train)

    def predict_proba(self, scores: np.ndarray) -> np.ndarray:
        """Return calibrated probabilities."""
        scores = np.atleast_1d(scores)
        return self.isotonic.predict(scores).clip(0, 1)

    def confidence_interval(self, scores: np.ndarray, confidence: float = 0.95) -> Tuple[np.ndarray, np.ndarray]:
        """
        Approximate confidence intervals using local binomial variance.
        For each score, find k nearest training scores, compute the empirical
        variance of the binary labels in that neighborhood, and assume asymptotic
        normality to construct a confidence interval around the calibrated value.
        """
        scores = np.atleast_1d(scores)
        if self.nn is None or len(self.X_train) == 0:
            # fallback
            lower = np.clip(scores - 0.05, 0, 1)
            upper = np.clip(scores + 0.05, 0, 1)
            return lower, upper

        # Get k nearest neighbors for each score
        X_query = scores.reshape(-1, 1)
        distances, indices = self.nn.kneighbors(X_query)

        z = 1.96  # for 95% CI (approx)
        lower = []
        upper = []
        for i, idx in enumerate(indices):
            y_neigh = self.y_train[idx]
            p_hat = np.mean(y_neigh)
            # binomial variance
            var = p_hat * (1 - p_hat) / len(y_neigh)
            std = np.sqrt(var)
            calibrated = self.isotonic.predict([scores[i]])[0]
            # CI around calibrated value using the same std (heuristic)
            ci_lower = calibrated - z * std
            ci_upper = calibrated + z * std
            lower.append(ci_lower)
            upper.append(ci_upper)
        lower = np.clip(lower, 0, 1)
        upper = np.clip(upper, 0, 1)
        return lower, upper

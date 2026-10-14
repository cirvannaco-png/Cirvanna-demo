import threading
import warnings
from typing import Dict, Optional, Tuple

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    warnings.warn("redis-py not installed. Bayesian layer will use in‑memory fallback.")

class BayesianLayer:
    """
    Hierarchical Beta‑Binomial model with persistent storage in Redis.
    Falls back to in‑memory dictionaries if Redis is unavailable or not configured.
    """
    def __init__(self, redis_client: Optional['redis.Redis'] = None, key_prefix: str = "fci:bayes:"):
        self.redis = redis_client
        self.prefix = key_prefix
        self._lock = threading.RLock()
        # In‑memory fallback (used if redis is None)
        self._mem_category: Dict[str, Tuple[float, float]] = {}
        self._mem_brand_category: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self._mem_user_brand_category: Dict[Tuple[str, str, str], Tuple[float, float]] = {}
        # Global prior (fixed)
        self.global_alpha = 1.0
        self.global_beta = 1.0

    def _redis_key(self, level: str, *parts) -> str:
        """Generate Redis key for a given level and identifiers."""
        return self.prefix + level + ":" + ":".join(str(p) for p in parts)

    def _get_counts(self, key: str) -> Tuple[float, float]:
        """Retrieve (alpha, beta) from Redis or in‑memory."""
        if self.redis:
            data = self.redis.hgetall(key)
            if data:
                return float(data.get(b'alpha', 0.0)), float(data.get(b'beta', 0.0))
            return 0.0, 0.0
        else:
            return 0.0, 0.0  # will be handled by caller using in‑memory dicts

    def _set_counts(self, key: str, alpha: float, beta: float):
        """Store (alpha, beta) in Redis or in‑memory."""
        if self.redis:
            self.redis.hset(key, mapping={'alpha': alpha, 'beta': beta})
        # in‑memory is handled separately

    def update(self, category: str, brand: str, user: str, successes: float, trials: float):
        """Update all levels with a new observation."""
        if trials <= 0 or successes < 0 or successes > trials:
            raise ValueError("Invalid successes/trials")
        with self._lock:
            # Update user‑brand‑category
            ubc_key = self._redis_key("ubc", user, brand, category)
            if self.redis:
                a_ubc, b_ubc = self._get_counts(ubc_key)
                self._set_counts(ubc_key, a_ubc + successes, b_ubc + (trials - successes))
            else:
                key = (user, brand, category)
                a_ubc, b_ubc = self._mem_user_brand_category.get(key, (0.0, 0.0))
                self._mem_user_brand_category[key] = (a_ubc + successes, b_ubc + (trials - successes))

            # Update brand‑category
            bc_key = self._redis_key("bc", brand, category)
            if self.redis:
                a_bc, b_bc = self._get_counts(bc_key)
                self._set_counts(bc_key, a_bc + successes, b_bc + (trials - successes))
            else:
                key = (brand, category)
                a_bc, b_bc = self._mem_brand_category.get(key, (0.0, 0.0))
                self._mem_brand_category[key] = (a_bc + successes, b_bc + (trials - successes))

            # Update category
            cat_key = self._redis_key("cat", category)
            if self.redis:
                a_c, b_c = self._get_counts(cat_key)
                self._set_counts(cat_key, a_c + successes, b_c + (trials - successes))
            else:
                a_c, b_c = self._mem_category.get(category, (0.0, 0.0))
                self._mem_category[category] = (a_c + successes, b_c + (trials - successes))

    def predict(self, category: str, brand: str, user: str) -> float:
        """Return posterior mean for the given user, brand, category."""
        with self._lock:
            # Get brand‑category prior
            bc_key = self._redis_key("bc", brand, category)
            if self.redis:
                a_bc, b_bc = self._get_counts(bc_key)
                if a_bc + b_bc == 0:
                    # fallback to global
                    a_bc, b_bc = self.global_alpha, self.global_beta
            else:
                key_bc = (brand, category)
                a_bc, b_bc = self._mem_brand_category.get(key_bc, (self.global_alpha, self.global_beta))

            # Get user‑brand‑category data
            ubc_key = self._redis_key("ubc", user, brand, category)
            if self.redis:
                a_ubc, b_ubc = self._get_counts(ubc_key)
            else:
                key_ubc = (user, brand, category)
                a_ubc, b_ubc = self._mem_user_brand_category.get(key_ubc, (0.0, 0.0))

            # Posterior mean
            trials_ubc = a_ubc + b_ubc
            if trials_ubc > 0:
                posterior_alpha = a_bc + a_ubc
                posterior_beta = b_bc + b_ubc
            else:
                posterior_alpha = a_bc
                posterior_beta = b_bc

            return posterior_alpha / (posterior_alpha + posterior_beta)

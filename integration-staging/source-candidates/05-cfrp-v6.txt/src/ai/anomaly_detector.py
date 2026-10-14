"""
AnomalyDetector – Statistical anomaly detection.
"""
import numpy as np
from collections import deque
from typing import Dict

class AnomalyDetector:
    def __init__(self, window_size: int = 100, sigma_threshold: float = 3.0):
        self.window_size = window_size
        self.sigma_threshold = sigma_threshold
        self.history: Dict[str, deque] = {}

    async def check_anomaly(self, user_id: str, old_conf: float, new_conf: float, metadata=None) -> Dict:
        delta = new_conf - old_conf
        if user_id not in self.history:
            self.history[user_id] = deque(maxlen=self.window_size)
        self.history[user_id].append(delta)
        if len(self.history[user_id]) < 10:
            return {"anomaly": False, "reason": "insufficient_data"}
        mean = np.mean(self.history[user_id])
        std = np.std(self.history[user_id])
        if std == 0:
            return {"anomaly": False, "reason": "zero_std"}
        z_score = (delta - mean) / std
        is_anomaly = abs(z_score) > self.sigma_threshold
        return {"anomaly": is_anomaly, "z_score": float(z_score)}

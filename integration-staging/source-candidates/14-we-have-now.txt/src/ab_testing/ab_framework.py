# src/ab_testing/ab_framework.py
import hashlib
from typing import Optional
from uuid import UUID
from config.config import config

class ABFramework:
    def __init__(self, experiments: dict = None):
        self.experiments = experiments or config.AB_EXPERIMENTS or {}

    def get_experiment(self, user_id: UUID) -> Optional[str]:
        # Assign user to an active experiment based on user_id hash
        # For simplicity, return first experiment if any
        if self.experiments:
            return list(self.experiments.keys())[0]
        return None

    def get_variant(self, user_id: UUID, experiment: str) -> str:
        # Deterministic assignment based on user_id hash and experiment name
        hash_val = int(hashlib.md5(f"{experiment}:{user_id}".encode()).hexdigest(), 16)
        variants = self.experiments[experiment].get('variants', ['control', 'B'])
        idx = hash_val % len(variants)
        return variants[idx]

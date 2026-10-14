"""
Offline evaluation framework for retrieval and outfit quality.
"""
import numpy as np
from typing import List, Dict, Any
from ...config import TariConfig

class OfflineEvaluator:
    def __init__(self, config: TariConfig):
        self.config = config

    def compute_recall_at_k(self, retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
        retrieved_k = retrieved_ids[:k]
        intersection = set(retrieved_k) & set(relevant_ids)
        return len(intersection) / len(relevant_ids) if relevant_ids else 0.0

    def compute_ndcg_at_k(self, retrieved_ids: List[str], relevance_scores: Dict[str, float], k: int) -> float:
        dcg = 0.0
        for i, pid in enumerate(retrieved_ids[:k]):
            rel = relevance_scores.get(pid, 0.0)
            dcg += rel / np.log2(i + 2)
        # Ideal DCG
        sorted_relevances = sorted(relevance_scores.values(), reverse=True)[:k]
        idcg = sum([rel / np.log2(i + 2) for i, rel in enumerate(sorted_relevances)])
        return dcg / idcg if idcg > 0 else 0.0

    def compute_mrr(self, retrieved_ids: List[str], relevant_ids: List[str]) -> float:
        for i, pid in enumerate(retrieved_ids):
            if pid in relevant_ids:
                return 1.0 / (i + 1)
        return 0.0

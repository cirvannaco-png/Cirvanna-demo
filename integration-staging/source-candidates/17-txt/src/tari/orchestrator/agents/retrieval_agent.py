"""
Retrieval Agent – semantic search with hybrid retrieval (BM25 + vector + behavioral boost).
"""
import asyncio
import numpy as np
from typing import List, Dict, Any, Optional
from ...config import TariConfig
from ...cache.predictive_cache import PredictiveCache
from ...privacy.manager import PrivacyManager
from ...connection_pool import SecureConnectionPool
from ...similarity.engine import VectorSimilarityEngine

class RetrievalAgent:
    def __init__(self, config: TariConfig, cache: PredictiveCache,
                 privacy_manager: PrivacyManager, pool: SecureConnectionPool):
        self.config = config
        self.cache = cache
        self.privacy_manager = privacy_manager
        self.pool = pool
        self.vector_engine = VectorSimilarityEngine(config.MAX_EMBEDDING_DIM)
        self._product_index = None
        self._bm25_index = None  # would be built from product descriptions

    async def generate_style_embedding(self, intent: Dict, user_profile: Dict) -> np.ndarray:
        """
        Convert user intent and profile into a unified embedding vector.
        """
        # In production: use CLIP or FashionCLIP to embed the intent text
        # For now, create a dummy embedding
        embedding = np.random.randn(self.config.MAX_EMBEDDING_DIM).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        return embedding

    async def retrieve_products(self, style_embedding: np.ndarray,
                                intent: Dict, user_profile: Dict) -> List[Dict]:
        """
        Hybrid retrieval: vector search + BM25 + behavioral boost + freshness + inventory.
        """
        # Step 1: Vector search (top 200)
        vector_results = await self._vector_search(style_embedding, top_k=self.config.RETRIEVAL_TOP_K)
        # Step 2: BM25 (text match on product descriptions)
        bm25_results = await self._bm25_search(intent, top_k=self.config.RETRIEVAL_TOP_K)
        # Step 3: Merge with reciprocal rank fusion (RRF)
        merged = self._reciprocal_rank_fusion(vector_results, bm25_results, k=60)
        # Step 4: Apply behavioral boost (based on user profile)
        boosted = self._apply_behavioral_boost(merged, user_profile)
        # Step 5: Apply freshness and inventory score
        final = self._apply_inventory_and_freshness(boosted)
        # Step 6: Diversity re-ranking (MMR)
        diverse = self._maximal_marginal_relevance(style_embedding, final, lambda_d=self.config.DIVERSITY_LAMBDA)
        # Step 7: Return top 12
        return diverse[:self.config.FINAL_TOP_K]

    async def _vector_search(self, embedding: np.ndarray, top_k: int) -> List[Dict]:
        # Placeholder – query vector DB
        # In production: Qdrant, Weaviate, Pinecone, or FAISS
        results = []
        # Dummy results
        for i in range(top_k):
            results.append({
                "product_id": f"prod_{i}",
                "score": 1.0 - (i / top_k),
                "embedding": np.random.randn(self.config.MAX_EMBEDDING_DIM).astype(np.float32),
                "metadata": {"category": "top", "color": "black", "price": 50 + i}
            })
        return results

    async def _bm25_search(self, intent: Dict, top_k: int) -> List[Dict]:
        # Placeholder – use Whoosh, Elasticsearch, or a simple TF-IDF
        results = []
        for i in range(top_k):
            results.append({
                "product_id": f"prod_{i}",
                "score": 0.9 - (i / top_k),
                "metadata": {}
            })
        return results

    def _reciprocal_rank_fusion(self, list_a: List[Dict], list_b: List[Dict], k: int = 60) -> List[Dict]:
        scores = {}
        for rank, item in enumerate(list_a):
            rid = item["product_id"]
            scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)
        for rank, item in enumerate(list_b):
            rid = item["product_id"]
            scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)
        sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        merged = []
        for rid, score in sorted_ids:
            # Find the full item from either list
            item = next((x for x in list_a if x["product_id"] == rid), None)
            if not item:
                item = next((x for x in list_b if x["product_id"] == rid), None)
            if item:
                item["fusion_score"] = score
                merged.append(item)
        return merged

    def _apply_behavioral_boost(self, items: List[Dict], user_profile: Dict) -> List[Dict]:
        # Boost products similar to user's liked styles
        liked_styles = user_profile.get("likedStyles", [])
        for item in items:
            item_tags = item.get("metadata", {}).get("styleTags", [])
            boost = 1.0
            for tag in item_tags:
                if tag in liked_styles:
                    boost *= 1.2
            item["score"] = item.get("fusion_score", 0.5) * boost
        items.sort(key=lambda x: x["score"], reverse=True)
        return items

    def _apply_inventory_and_freshness(self, items: List[Dict]) -> List[Dict]:
        # Placeholder – filter out out-of-stock and boost new arrivals
        return items

    def _maximal_marginal_relevance(self, query_embedding: np.ndarray, items: List[Dict],
                                    lambda_d: float = 0.5) -> List[Dict]:
        """
        MMR algorithm for diversity.
        """
        if not items:
            return []
        selected = []
        remaining = items.copy()
        # Precompute item embeddings
        for item in remaining:
            if "embedding" not in item:
                item["embedding"] = np.random.randn(self.config.MAX_EMBEDDING_DIM).astype(np.float32)
                item["embedding"] /= np.linalg.norm(item["embedding"])
        # Select first item
        first = max(remaining, key=lambda x: x["score"])
        selected.append(first)
        remaining.remove(first)
        while remaining and len(selected) < self.config.FINAL_TOP_K:
            mmr_scores = []
            for item in remaining:
                rel = item["score"]
                sim_max = max([self._cosine_sim(item["embedding"], sel["embedding"]) for sel in selected])
                mmr = lambda_d * rel - (1 - lambda_d) * sim_max
                mmr_scores.append(mmr)
            best_idx = np.argmax(mmr_scores)
            selected.append(remaining[best_idx])
            remaining.pop(best_idx)
        return selected

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

    async def health(self) -> Dict:
        return {"agent": "retrieval", "status": "healthy"}

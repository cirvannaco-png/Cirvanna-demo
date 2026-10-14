"""
Privacy-first recommendation engine with integrated dialogue, personalisation, and feedback.
"""
import time
import numpy as np
from datetime import datetime
from typing import Optional, Dict, List, Any

from ..config import XyraConfig
from ..cache.predictive_cache import PredictiveCache
from ..privacy.manager import PrivacyManager
from ..processing.batch_processor import AdaptiveBatchProcessor
from ..optimization.real_time_optimizer import RealTimeOptimizer
from ..skin.analyzer import FastSkinAnalyzer
from ..similarity.engine import VectorSimilarityEngine
from ..dialogue.orchestrator import DialogueOrchestrator
from ..connection_pool import SecureConnectionPool
from ..logging.metrics import METRICS
from ..learning.user_embedding import UserEmbeddingUpdater

class PrivacyFirstRecommendationEngine:
    def __init__(self, config: XyraConfig, cache: PredictiveCache):
        self.config = config
        self.cache = cache
        self.privacy_manager = PrivacyManager(config)
        self.batch_processor = AdaptiveBatchProcessor(config)
        self.performance_monitor = RealTimeOptimizer(config)
        self.skin_analyzer = FastSkinAnalyzer(config)
        self.similarity_engine = VectorSimilarityEngine(config.MAX_EMBEDDING_DIM)
        self.dialogue_orchestrator = DialogueOrchestrator(config, cache)
        self.user_embedding_updater = UserEmbeddingUpdater(config) if config.ENABLE_USER_EMBEDDING else None
        self.product_catalog = self._load_catalog_privately()
        self._build_similarity_index()

    def _load_catalog_privately(self):
        catalog = {
            "prod_001": {
                "id": "prod_001",
                "name": "Hydrating Serum",
                "embedding": self.privacy_manager.add_differential_privacy_noise(
                    np.random.randn(self.config.MAX_EMBEDDING_DIM).astype(np.float32)
                ),
                "ingredients": ["hyaluronic_acid", "ceramides", "vitamin_b5"],
                "category": "serum",
                "price": 29.99,
                "rating": 4.5,
                "popularity": 0.8,
                "safety_score": 0.95
            },
        }
        if self.config.ENCRYPT_SENSITIVE_DATA:
            for product in catalog.values():
                product["encrypted_data"] = self.privacy_manager.encrypt_sensitive_data({
                    "clinical_data": product.get("clinical_data", {}),
                    "supplier_info": product.get("supplier_info", {})
                })
        return catalog

    def _build_similarity_index(self):
        product_ids = []
        embeddings = []
        for pid, product in self.product_catalog.items():
            product_ids.append(pid)
            embeddings.append(product["embedding"])
        embeddings_array = np.array(embeddings, dtype=np.float32)
        self.similarity_engine.build_index(embeddings_array, product_ids)

    async def recommend_with_dialogue(self, user_id, query, context, skin_data=None):
        start_time = time.perf_counter()
        anonymized_id = self.privacy_manager.anonymize_user_id(user_id)
        cache_key = self.cache.generate_key(
            "rec_dialogue", anonymized_id,
            hash(tuple(sorted(context.items()))),
            skin_data.get("skin_type") if skin_data else "none",
            hash(query) if query else "no_query"
        )
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            cached = await self.cache.get_distributed(redis_pool, cache_key)
            if cached:
                return cached

            # Retrieve user embedding
            user_embedding = await self._get_user_embedding_privately(anonymized_id, redis_pool)

            # Collaborative filtering: find similar users (simplified, would use a user-user matrix)
            # For now, use content-based on embedding.

            similar_products = self.similarity_engine.search(
                user_embedding,
                k=50,
                threshold=0.1
            )
            product_batch = []
            for pid, similarity in similar_products:
                product = self.product_catalog.get(pid)
                if product:
                    product_batch.append({
                        "id": pid,
                        "product": product,
                        "similarity": similarity
                    })
            recommendations = await self._process_batch_privately(
                product_batch, context, skin_data
            )
            final_recommendations = self._apply_business_rules(
                recommendations, context
            )
            dialogue = None
            if query:
                dialogue = await self.dialogue_orchestrator.generate_response(
                    user_id=anonymized_id,
                    query=query,
                    context=context,
                    recommendations=final_recommendations,
                    user_embedding=user_embedding
                )
            result = {
                "user_id": anonymized_id,
                "recommendations": final_recommendations[:10],
                "dialogue": dialogue,
                "privacy": {
                    "anonymized": True,
                    "retention_days": self.config.DATA_RETENTION_DAYS,
                    "differential_privacy_applied": self.config.ENABLE_DIFFERENTIAL_PRIVACY
                },
                "performance": {
                    "generated_at": datetime.now().isoformat(),
                    "elapsed_ms": (time.perf_counter() - start_time) * 1000,
                    "cache_status": "miss"
                }
            }
            await self.cache.set_distributed(redis_pool, cache_key, result)
            self.performance_monitor.record_metrics({
                "latency": (time.perf_counter() - start_time) * 1000,
                "cache_hit_rate": 0,
                "recommendations_generated": len(final_recommendations)
            })
            return result

    async def _get_user_embedding_privately(self, user_id, redis_pool):
        cache_key = f"user_embedding:{user_id}"
        cached = await redis_pool.get(cache_key)
        if cached:
            return np.frombuffer(cached, dtype=np.float32)
        query = """
            SELECT embedding, privacy_level FROM user_embeddings
            WHERE user_id = :user_id
            LIMIT 1
        """
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_db() as db:
            result = await db.fetch_one(query, {"user_id": user_id})
            if result and result["embedding"]:
                embedding = np.frombuffer(result["embedding"], dtype=np.float32)
                privacy_level = result.get("privacy_level", "standard")
                if privacy_level == "high" and self.config.ENABLE_DIFFERENTIAL_PRIVACY:
                    embedding = self.privacy_manager.add_differential_privacy_noise(embedding)
            else:
                embedding = np.random.randn(self.config.USER_EMBEDDING_DIM).astype(np.float32)
                embedding = embedding / np.linalg.norm(embedding)
                await db.execute("""
                    INSERT INTO user_embeddings
                    (user_id, embedding, privacy_level, created_at, updated_at)
                    VALUES (:user_id, :embedding, :privacy_level, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                """, {
                    "user_id": user_id,
                    "embedding": embedding.tobytes(),
                    "privacy_level": "standard"
                })
        await redis_pool.setex(cache_key, 3600, embedding.tobytes())
        return embedding

    async def _process_batch_privately(self, products, context, skin_data):
        if not products:
            return []
        async def process_chunk(chunk):
            return await self._process_product_chunk(chunk, context, skin_data)
        return await self.batch_processor.process_batch(products, process_chunk)

    async def _process_product_chunk(self, products, context, skin_data):
        processed = []
        for product_info in products:
            compatibility = await self.skin_analyzer.analyze(
                skin_type=skin_data.get("skin_type") if skin_data else "NORMAL",
                ingredients=product_info["product"].get("ingredients", []),
                image_data=skin_data.get("image") if skin_data else None
            )
            final_score = (
                0.5 * product_info["similarity"] +
                0.3 * compatibility.get("score", 0.5) +
                0.1 * product_info["product"].get("popularity", 0.5) +
                0.1 * product_info["product"].get("safety_score", 0.8)
            )
            processed.append({
                **product_info,
                "score": float(final_score),
                "compatibility": compatibility,
                "safety_score": product_info["product"].get("safety_score", 0.8)
            })
        return processed

    def _apply_business_rules(self, recommendations, context):
        price_sensitive = context.get("price_sensitive", False)
        max_price = context.get("max_price", float('inf'))
        min_safety = context.get("min_safety_score", 0.7)
        filtered = []
        for rec in recommendations:
            product = rec["product"]
            if product["price"] > max_price:
                continue
            if product.get("safety_score", 1.0) < min_safety:
                continue
            adjusted_score = rec["score"]
            if price_sensitive and product["price"] > 30:
                adjusted_score *= 0.8
            safety_boost = (product.get("safety_score", 1.0) - 0.7) * 0.1
            adjusted_score *= (1 + safety_boost)
            filtered.append({
                **rec,
                "final_score": adjusted_score,
                "reasoning": {
                    "price_appropriate": product["price"] <= max_price,
                    "safety_met": product.get("safety_score", 1.0) >= min_safety,
                    "personalization_strength": rec["similarity"]
                }
            })
        filtered.sort(key=lambda x: x["final_score"], reverse=True)
        return filtered

    async def record_feedback(self, user_id: str, interaction_id: str, rating: int, comment: Optional[str] = None):
        """
        Store explicit feedback and update user embedding.
        """
        anonymized_id = self.privacy_manager.anonymize_user_id(user_id)
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_db() as db:
            await db.execute("""
                INSERT INTO user_feedback (user_id, interaction_id, rating, comment, created_at)
                VALUES (:user_id, :interaction_id, :rating, :comment, NOW())
            """, {
                "user_id": anonymized_id,
                "interaction_id": interaction_id,
                "rating": rating,
                "comment": comment
            })
        # Update user embedding asynchronously (could be background task)
        if self.user_embedding_updater:
            await self.user_embedding_updater.update_from_feedback(anonymized_id, interaction_id, rating)

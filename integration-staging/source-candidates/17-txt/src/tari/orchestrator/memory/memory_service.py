"""
Memory Service – layered memory: session, preference, behavioral, semantic.
"""
import time
from typing import Dict, Any, List, Optional
from collections import defaultdict
from ...config import TariConfig
from ...cache.predictive_cache import PredictiveCache
from ...privacy.manager import PrivacyManager
from ...connection_pool import SecureConnectionPool

class MemoryService:
    def __init__(self, config: TariConfig, cache: PredictiveCache,
                 privacy_manager: PrivacyManager, pool: SecureConnectionPool):
        self.config = config
        self.cache = cache
        self.privacy_manager = privacy_manager
        self.pool = pool
        self._session_memories = defaultdict(dict)
        self._preferences = defaultdict(dict)
        self._behavioral = defaultdict(list)
        self._semantic_embeddings = defaultdict(list)

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Retrieve combined user profile from all memory tiers."""
        anonymized = self.privacy_manager.anonymize_user_id(user_id)
        # Fetch from Redis/Postgres or from local caches
        preferences = await self._get_preferences(anonymized)
        behavioral = await self._get_behavioral(anonymized)
        semantic = await self._get_semantic(anonymized)
        session = self._session_memories.get(anonymized, {})
        # Merge
        profile = {
            "likedStyles": preferences.get("liked_styles", []),
            "dislikedStyles": preferences.get("disliked_styles", []),
            "preferredColors": preferences.get("preferred_colors", []),
            "avoidedColors": preferences.get("avoided_colors", []),
            "luxuryPreference": preferences.get("luxury_preference", 0.5),
            "formalityPreference": preferences.get("formality_preference", 0.5),
            "silhouettePreferences": preferences.get("silhouette_preferences", []),
            "recentInteractions": behavioral[-10:],
            "semanticStyle": semantic.get("embedding", []),
            "session": session
        }
        return profile

    async def update_memory(self, user_id: str, interaction: Dict):
        """Update memory tiers based on interaction."""
        anonymized = self.privacy_manager.anonymize_user_id(user_id)
        # Session memory (short-term)
        self._session_memories[anonymized].update(interaction)
        # Preference memory (if explicit like/dislike)
        if "liked_style" in interaction:
            prefs = await self._get_preferences(anonymized)
            prefs["liked_styles"] = prefs.get("liked_styles", []) + [interaction["liked_style"]]
            await self._store_preferences(anonymized, prefs)
        # Behavioral memory (append)
        self._behavioral[anonymized].append({
            "timestamp": time.time(),
            "type": interaction.get("type"),
            "product_id": interaction.get("product_id")
        })
        if len(self._behavioral[anonymized]) > 100:
            self._behavioral[anonymized] = self._behavioral[anonymized][-100:]
        # Semantic memory (update embedding with temporal decay)
        if "style_embedding" in interaction:
            emb = interaction["style_embedding"]
            current = await self._get_semantic(anonymized)
            old_emb = current.get("embedding", [0]*384)
            # Exponential moving average with decay
            alpha = 0.3
            new_emb = [alpha * e + (1-alpha) * o for e, o in zip(emb, old_emb)]
            await self._store_semantic(anonymized, {"embedding": new_emb})

    async def _get_preferences(self, user_id: str) -> Dict:
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            data = await redis_pool.get(f"preferences:{user_id}")
            if data:
                return orjson.loads(data)
        return {}

    async def _store_preferences(self, user_id: str, prefs: Dict):
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            await redis_pool.setex(f"preferences:{user_id}", 86400 * 30, orjson.dumps(prefs))

    async def _get_behavioral(self, user_id: str) -> List:
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            data = await redis_pool.lrange(f"behavioral:{user_id}", 0, -1)
            return [orjson.loads(d) for d in data]

    async def _get_semantic(self, user_id: str) -> Dict:
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            data = await redis_pool.get(f"semantic:{user_id}")
            if data:
                return orjson.loads(data)
        return {"embedding": []}

    async def _store_semantic(self, user_id: str, semantic: Dict):
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            await redis_pool.setex(f"semantic:{user_id}", 86400 * 30, orjson.dumps(semantic))

    async def health(self) -> Dict:
        return {"service": "memory", "status": "healthy"}

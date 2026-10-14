"""
Dialogue history management.
"""
import time
import orjson
from ..cache.predictive_cache import PredictiveCache
from ..connection_pool import SecureConnectionPool

class DialogueMemoryManager:
    def __init__(self, config):
        self.config = config
        self.max_history = config.MAX_DIALOGUE_HISTORY

    async def get_dialogue_history(self, user_id, limit=10):
        cache_key = PredictiveCache.generate_key("dialogue_history", user_id)
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            history = await redis_pool.lrange(cache_key, 0, limit - 1)
        return [orjson.loads(h) for h in history]

    async def store_interaction(self, user_id, query, response, tier, intent):
        interaction = {
            "timestamp": time.time(),
            "query": query,
            "response": response,
            "tier": tier,
            "intent": intent
        }
        cache_key = PredictiveCache.generate_key("dialogue_history", user_id)
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            async with redis_pool.pipeline() as pipe:
                await pipe.lpush(cache_key, orjson.dumps(interaction))
                await pipe.ltrim(cache_key, 0, self.max_history - 1)
                await pipe.expire(cache_key, 86400)  # 24 hours
                await pipe.execute()

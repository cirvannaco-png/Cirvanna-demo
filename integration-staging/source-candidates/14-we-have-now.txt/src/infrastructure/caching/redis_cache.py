# src/infrastructure/caching/redis_cache.py
import json
import redis.asyncio as redis
from typing import Any, Optional
from datetime import timedelta
import pickle
import numpy as np

class RedisCache:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=False)

    async def get(self, key: str) -> Optional[Any]:
        data = await self.redis.get(key)
        if data:
            return pickle.loads(data)
        return None

    async def set(self, key: str, value: Any, ttl: int = None):
        pickled = pickle.dumps(value)
        if ttl:
            await self.redis.setex(key, ttl, pickled)
        else:
            await self.redis.set(key, pickled)

    async def delete(self, key: str):
        await self.redis.delete(key)

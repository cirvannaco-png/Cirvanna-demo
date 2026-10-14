"""Async Redis cache client with typed helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from .config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Thin async wrapper around Redis with JSON serialization.

    Usage:
        await RedisCache.init()
        await RedisCache.set("key", {"a": 1}, ttl=300)
        value = await RedisCache.get_json("key")
        await RedisCache.close()
    """

    _client: redis.Redis | None = None

    @classmethod
    async def init(cls) -> None:
        if cls._client is None:
            cls._client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.redis_max_connections,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            # Ping to verify
            try:
                await cls._client.ping()
                logger.info("Redis connection established")
            except RedisError as exc:
                logger.error(f"Redis ping failed: {exc}")
                cls._client = None
                raise

    @classmethod
    async def close(cls) -> None:
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            logger.info("Redis connection closed")

    @classmethod
    def _require_client(cls) -> redis.Redis:
        if cls._client is None:
            raise RuntimeError("RedisCache not initialized. Call RedisCache.init() first.")
        return cls._client

    # ── Basic operations ────────────────────────────────────────
    @classmethod
    async def get(cls, key: str) -> str | None:
        try:
            return await cls._require_client().get(key)
        except RedisError as exc:
            logger.warning(f"Redis GET failed for key={key}: {exc}")
            return None

    @classmethod
    async def get_json(cls, key: str) -> Any | None:
        raw = await cls.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Malformed JSON in cache key={key}")
            return None

    @classmethod
    async def set(cls, key: str, value: str, ttl: int = 300) -> None:
        try:
            await cls._require_client().set(key, value, ex=ttl)
        except RedisError as exc:
            logger.warning(f"Redis SET failed for key={key}: {exc}")

    @classmethod
    async def set_json(cls, key: str, value: Any, ttl: int = 300) -> None:
        await cls.set(key, json.dumps(value, default=str), ttl)

    @classmethod
    async def delete(cls, *keys: str) -> int:
        try:
            if not keys:
                return 0
            return await cls._require_client().delete(*keys)
        except RedisError as exc:
            logger.warning(f"Redis DEL failed: {exc}")
            return 0

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """Delete all keys matching a pattern (SCAN-based, non-blocking)."""
        client = cls._require_client()
        count = 0
        try:
            async for key in client.scan_iter(match=pattern, count=100):
                count += await client.delete(key)
        except RedisError as exc:
            logger.warning(f"Redis SCAN/DEL failed for pattern={pattern}: {exc}")
        return count

    # ── Atomic counters (rate limiting) ─────────────────────────
    @classmethod
    async def incr(cls, key: str, ttl: int = 60) -> int:
        """Atomic increment; sets expiry on first increment."""
        client = cls._require_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)
        results = await pipe.execute()
        return int(results[0])

    @classmethod
    async def get_int(cls, key: str) -> int:
        raw = await cls.get(key)
        return int(raw) if raw else 0

    # ── Distributed lock (Redlock-lite) ─────────────────────────
    @classmethod
    async def acquire_lock(cls, key: str, ttl: int = 10) -> bool:
        """Best-effort distributed lock using SET NX EX."""
        client = cls._require_client()
        return bool(await client.set(key, "1", nx=True, ex=ttl))

    @classmethod
    async def release_lock(cls, key: str) -> None:
        await cls.delete(key)

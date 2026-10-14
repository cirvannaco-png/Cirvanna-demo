"""Per-endpoint + per-IP rate limiter backed by Redis."""
from __future__ import annotations

import logging

from fastapi import Request

from common.cache import RedisCache
from common.errors import RateLimitError

from .config import DEFAULT_LIMIT, ENDPOINT_LIMITS

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """Respect X-Forwarded-For when behind a proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class EndpointRateLimiter:
    @staticmethod
    async def check(request: Request) -> None:
        path = request.url.path
        limit, window = DEFAULT_LIMIT
        for prefix, cfg in ENDPOINT_LIMITS.items():
            if path.startswith(prefix):
                limit, window = cfg
                break

        ip = _client_ip(request)
        key = f"rl:{path}:{ip}"
        count = await RedisCache.incr(key, ttl=window)
        if count > limit:
            logger.warning(f"Rate limit hit path={path} ip={ip} count={count}")
            raise RateLimitError(
                f"Rate limit exceeded for {path}",
                details={"limit": limit, "window_seconds": window, "count": count},
            )

"""Exponential backoff retry utilities."""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """Retry an async function with exponential backoff + jitter."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return await fn()
        except retry_on as exc:
            if attempt >= max_attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay *= 0.5 + random.random()
            if on_retry:
                on_retry(attempt, exc)
            logger.warning(
                "Retrying after error",
                extra={"extra_fields": {"attempt": attempt, "delay": delay, "error": str(exc)}},
            )
            await asyncio.sleep(delay)


def with_retry(**kwargs):
    """Decorator variant of retry_async."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kw):
            return await retry_async(lambda: fn(*args, **kw), **kwargs)

        return wrapper

    return decorator

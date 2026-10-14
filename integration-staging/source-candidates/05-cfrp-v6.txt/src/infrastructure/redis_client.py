"""
Simulated Redis client for snapshot storage and caching.
"""
import asyncio
import time
from typing import Any, Dict, Optional

class RedisClient:
    _instance = None
    _data: Dict[str, Any] = {}
    _locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        self._data[key] = {
            'value': value,
            'expiry': time.time() + ttl if ttl else None
        }

    async def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None
        entry = self._data[key]
        if entry['expiry'] and time.time() > entry['expiry']:
            del self._data[key]
            return None
        return entry['value']

    async def delete(self, key: str):
        if key in self._data:
            del self._data[key]

    async def acquire_lock(self, lock_name: str, timeout: int = 10) -> bool:
        if lock_name not in self._locks:
            self._locks[lock_name] = asyncio.Lock()
        try:
            await asyncio.wait_for(self._locks[lock_name].acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def release_lock(self, lock_name: str):
        if lock_name in self._locks and self._locks[lock_name].locked():
            self._locks[lock_name].release()

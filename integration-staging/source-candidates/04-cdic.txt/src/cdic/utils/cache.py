"""
Caching utilities
"""

import threading
from typing import Optional, Any
from cachetools import TTLCache, LRUCache


class MultiLevelCache:
    """Multi-level cache with TTL and LRU policies"""
    
    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        self.l1_cache = LRUCache(maxsize=maxsize)
        self.l2_cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.l1_lock = threading.RLock()
        self.l2_lock = threading.RLock()
        self.stats = {"hits": 0, "misses": 0}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        # Try L1 cache
        with self.l1_lock:
            if key in self.l1_cache:
                self.stats["hits"] += 1
                return self.l1_cache[key]
        
        # Try L2 cache
        with self.l2_lock:
            if key in self.l2_cache:
                self.stats["hits"] += 1
                value = self.l2_cache[key]
                # Promote to L1
                with self.l1_lock:
                    self.l1_cache[key] = value
                return value
        
        self.stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any):
        """Set value in both cache levels"""
        with self.l1_lock:
            self.l1_cache[key] = value
        with self.l2_lock:
            self.l2_cache[key] = value
    
    def invalidate(self, key: str):
        """Invalidate cache entry"""
        with self.l1_lock:
            self.l1_cache.pop(key, None)
        with self.l2_lock:
            self.l2_cache.pop(key, None)

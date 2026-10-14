"""
LRUCache – Simple LRU cache.
"""
from collections import OrderedDict
from typing import Any, Optional

class LRUCache:
    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self.cache = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Any, ttl: int = 300):
        if len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = value
        self.cache.move_to_end(key)

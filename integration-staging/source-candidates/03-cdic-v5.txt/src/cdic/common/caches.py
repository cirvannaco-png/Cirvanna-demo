from collections import OrderedDict
from threading import RLock

class LRUCache:
    """Thread-safe LRU cache."""
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                return None
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def __contains__(self, key):
        with self.lock:
            return key in self.cache

    def __len__(self):
        with self.lock:
            return len(self.cache)

    def clear(self):
        with self.lock:
            self.cache.clear()

# Global caches
_prompt_cache = LRUCache(5000)
_option_template_cache = LRUCache(10000)
_context_vector_cache = LRUCache(10000)

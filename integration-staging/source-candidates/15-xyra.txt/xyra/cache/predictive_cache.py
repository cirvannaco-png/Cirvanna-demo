"""
Intelligent caching with prefetching and access pattern learning.
"""
import asyncio
from collections import OrderedDict, deque
import orjson
import mmh3

class PredictiveCache:
    def __init__(self, config):
        self.config = config
        self.local_cache = OrderedDict()
        self.access_patterns = {}
        self.prefetch_queue = asyncio.Queue()
        self.hits = 0
        self.misses = 0
        self.prefetch_hits = 0
        self._prefetch_worker = asyncio.create_task(self._prefetch_worker_task())

    async def _prefetch_worker_task(self):
        while True:
            try:
                key, redis_pool = await self.prefetch_queue.get()
                await self._prefetch_related(key, redis_pool)
                self.prefetch_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def get_local(self, key):
        if key in self.local_cache:
            self.hits += 1
            value = self.local_cache.pop(key)
            self.local_cache[key] = value
            return value
        self.misses += 1
        return None

    def set_local(self, key, value):
        if key in self.local_cache:
            self.local_cache.move_to_end(key)
        else:
            if len(self.local_cache) >= self.config.MAX_CACHE_SIZE:
                self.local_cache.popitem(last=False)
            self.local_cache[key] = value

    async def get_distributed(self, redis_pool, key):
        if key in self.access_patterns:
            self.prefetch_hits += 1
        async with redis_pool.pipeline() as pipe:
            await pipe.get(key)
            await pipe.expire(key, self.config.CACHE_TTL_SECONDS)
            result, _ = await pipe.execute()
        if result:
            try:
                if result.startswith(b'compressed:'):
                    import zlib
                    result = zlib.decompress(result[11:])
                value = orjson.loads(result)
                self.set_local(key, value)
                await self.prefetch_queue.put((key, redis_pool))
                return value
            except Exception:
                pass
        return None

    async def set_distributed(self, redis_pool, key, value, compress=True):
        serialized = orjson.dumps(value)
        if compress and len(serialized) > 1000:
            import zlib
            compressed = zlib.compress(serialized)
            if len(compressed) < len(serialized) * 0.7:
                serialized = b'compressed:' + compressed
        async with redis_pool.pipeline() as pipe:
            await pipe.set(key, serialized, ex=self.config.CACHE_TTL_SECONDS)
            await pipe.execute()
        self.set_local(key, value)

    async def _prefetch_related(self, key, redis_pool):
        if key not in self.access_patterns:
            return
        related = self.access_patterns[key].get('related', [])
        for related_key in related[:5]:
            try:
                await redis_pool.get(related_key)
            except Exception:
                pass

    def record_access(self, key, next_key=None):
        if key not in self.access_patterns:
            self.access_patterns[key] = {'count': 0, 'related': {}}
        self.access_patterns[key]['count'] += 1
        if next_key:
            if next_key not in self.access_patterns[key]['related']:
                self.access_patterns[key]['related'][next_key] = 0
            self.access_patterns[key]['related'][next_key] += 1
            related_items = self.access_patterns[key]['related']
            if len(related_items) > 20:
                sorted_items = sorted(related_items.items(), key=lambda x: x[1], reverse=True)
                self.access_patterns[key]['related'] = dict(sorted_items[:15])

    @staticmethod
    def generate_key(prefix, *args):
        key_string = ":".join(str(arg) for arg in args)
        hash_int = mmh3.hash(key_string, signed=False)
        return f"{prefix}:{hash_int:x}"

    def get_stats(self):
        return {
            "local_cache_size": len(self.local_cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / max(self.hits + self.misses, 1),
            "prefetch_hits": self.prefetch_hits,
            "access_patterns": len(self.access_patterns),
        }

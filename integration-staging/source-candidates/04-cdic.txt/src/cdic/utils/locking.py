"""
Distributed locking utilities
"""

import uuid
import time
import threading
from contextlib import contextmanager
from collections import defaultdict
import redis


class DistributedLock:
    """Redis-based distributed lock with auto-renewal"""
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.local_locks = defaultdict(threading.RLock)
        self.renewal_threads = {}
        self.renewal_lock = threading.RLock()
    
    @contextmanager
    def acquire(self, lock_name: str, timeout: int = 10, block: bool = True):
        """Acquire distributed lock with context manager"""
        lock_key = f"cdic:lock:{lock_name}"
        identifier = str(uuid.uuid4())
        acquired = False
        
        try:
            # Try to acquire lock
            if block:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if self.redis.set(lock_key, identifier, nx=True, ex=timeout):
                        acquired = True
                        self._start_renewal(lock_key, identifier, timeout)
                        break
                    time.sleep(0.01)
            else:
                if self.redis.set(lock_key, identifier, nx=True, ex=timeout):
                    acquired = True
                    self._start_renewal(lock_key, identifier, timeout)
            
            if not acquired:
                raise TimeoutError(f"Could not acquire lock: {lock_name}")
            
            # Acquire local lock for thread safety
            with self.local_locks[lock_name]:
                yield identifier
        
        finally:
            if acquired:
                self._release_lock(lock_key, identifier)
    
    def _start_renewal(self, lock_key: str, identifier: str, timeout: int):
        """Start lock renewal in background thread"""
        with self.renewal_lock:
            if lock_key in self.renewal_threads:
                return
            
            def renew():
                while True:
                    time.sleep(timeout / 2)
                    current_id = self.redis.get(lock_key)
                    if current_id != identifier:
                        break
                    self.redis.expire(lock_key, timeout)
            
            thread = threading.Thread(target=renew, daemon=True)
            self.renewal_threads[lock_key] = thread
            thread.start()
    
    def _release_lock(self, lock_key: str, identifier: str):
        """Release lock"""
        # Use Lua script for atomic release
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(lua, 1, lock_key, identifier)
        
        with self.renewal_lock:
            if lock_key in self.renewal_threads:
                del self.renewal_threads[lock_key]

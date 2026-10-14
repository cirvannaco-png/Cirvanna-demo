"""
Enhanced connection management with security and connection pooling.
"""
import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
import redis.asyncio as redis
from databases import Database
import aiohttp
from .config import XyraConfig

class SecureConnectionPool:
    _instance = None
    _initialized = False

    def __init__(self, config: XyraConfig):
        self.config = config
        self.redis_pool = None
        self.db_pool = None
        self.http_session = None
        self.model_cache = {}
        self._lock = asyncio.Lock()
        self._redis_connections = deque(maxlen=config.DB_POOL_SIZE)
        self._db_connections = deque(maxlen=config.DB_POOL_SIZE)
        self._connection_semaphore = asyncio.Semaphore(config.DB_POOL_SIZE)
        self._rate_limiter = {}

    @classmethod
    def get_instance(cls, config: XyraConfig = None):
        if cls._instance is None:
            with asyncio.Lock():
                if cls._instance is None and config is not None:
                    cls._instance = cls(config)
        return cls._instance

    async def initialize(self):
        if self._initialized:
            return
        async with self._lock:
            try:
                self.redis_pool = await redis.Redis.from_url(
                    "redis://localhost:6379",
                    max_connections=self.config.DB_POOL_SIZE,
                    decode_responses=False,
                    ssl=False,
                    health_check_interval=30,
                )
                self.db_pool = Database(
                    "postgresql://user:pass@localhost/xyra",
                    min_size=5,
                    max_size=self.config.DB_POOL_SIZE,
                    ssl=False,
                )
                await self.db_pool.connect()
                timeout = aiohttp.ClientTimeout(total=2.0)
                connector = aiohttp.TCPConnector(limit=100, ssl=False)
                self.http_session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector,
                    headers={"User-Agent": "Xyra-System/1.0"}
                )
                await self._warm_connections()
                self._initialized = True
            except Exception as e:
                raise

    async def _warm_connections(self):
        tasks = []
        for _ in range(5):
            tasks.append(self._create_redis_connection())
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _create_redis_connection(self):
        conn = await self.redis_pool.connection()
        self._redis_connections.append(conn)
        return conn

    @asynccontextmanager
    async def get_redis(self):
        async with self._connection_semaphore:
            if self._redis_connections:
                conn = self._redis_connections.pop()
            else:
                conn = await self._create_redis_connection()
            try:
                yield conn
            finally:
                self._redis_connections.append(conn)

    @asynccontextmanager
    async def get_db(self):
        yield self.db_pool

    async def check_rate_limit(self, user_id: str, endpoint: str) -> bool:
        key = f"rate_limit:{user_id}:{endpoint}"
        now = time.time()
        window = self.config.RATE_LIMIT_WINDOW
        max_requests = self.config.RATE_LIMIT_REQUESTS
        async with self.get_redis() as redis_conn:
            # Use sorted set to track timestamps
            await redis_conn.zadd(key, {str(now): now})
            await redis_conn.zremrangebyscore(key, 0, now - window)
            count = await redis_conn.zcard(key)
            await redis_conn.expire(key, window)
            return count <= max_requests

    async def close(self):
        async with self._lock:
            if self.redis_pool:
                await self.redis_pool.close()
            if self.db_pool:
                await self.db_pool.disconnect()
            if self.http_session:
                await self.http_session.close()
            self._initialized = False

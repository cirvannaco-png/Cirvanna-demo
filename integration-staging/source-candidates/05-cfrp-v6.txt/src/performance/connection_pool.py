"""
ConnectionPool – Simple connection pool.
"""
import asyncio
from typing import Any

class ConnectionPool:
    def __init__(self, max_connections: int = 100):
        self.max_connections = max_connections
        self.connections = asyncio.Queue(maxsize=max_connections)
        self.in_use = set()

    async def acquire(self) -> Any:
        if not self.connections.empty():
            conn = await self.connections.get()
        elif len(self.in_use) < self.max_connections:
            conn = await self._create_connection()
        else:
            conn = await self.connections.get()
        self.in_use.add(id(conn))
        return conn

    async def release(self, conn: Any):
        if id(conn) in self.in_use:
            self.in_use.remove(id(conn))
            await self.connections.put(conn)

    async def _create_connection(self) -> Any:
        return object()

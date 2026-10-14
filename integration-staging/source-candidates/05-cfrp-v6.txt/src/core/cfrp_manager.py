"""
CFRPManager – Manages CFRP instances with sticky sessions.
"""
import asyncio
import logging
from typing import Dict

from src.core.cfrp_instance import CFRPInstance

class CFRPManager:
    def __init__(self):
        self.instances: Dict[str, CFRPInstance] = {}
        self.lock = asyncio.Lock()
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def get_instance(self, user_id: str) -> CFRPInstance:
        async with self.lock:
            if user_id not in self.instances:
                instance = CFRPInstance(user_id)
                await instance.start()
                self.instances[user_id] = instance
            return self.instances[user_id]

    async def start(self):
        self.running = True
        logging.info("CFRP Manager started")

    async def shutdown(self):
        if not self.running:
            return
        self.running = False
        self.shutdown_event.set()
        async with self.lock:
            shutdown_tasks = [inst.stop() for inst in self.instances.values()]
            if shutdown_tasks:
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            self.instances.clear()
        logging.info("CFRP Manager shutdown complete")

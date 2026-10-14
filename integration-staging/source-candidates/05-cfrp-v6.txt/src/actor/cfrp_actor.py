"""
CFRPActor – Single-threaded message processing lane.
"""
import asyncio
import logging
from typing import Callable, Optional, Dict

class CFRPActor:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.queue = asyncio.Queue(maxsize=1000)
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.signal_states: Dict = {}
        self.reinforcement_log: list = []
        logging.info(f"Actor created for {user_id}")

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if not self.running:
            return
        self.running = False
        await self.queue.put(None)
        if self.task:
            await self.task

    async def _run(self):
        while self.running:
            try:
                msg = await self.queue.get()
                if msg is None:
                    break
                await msg()
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Actor {self.user_id} error: {e}")

    async def send(self, func: Callable):
        future = asyncio.Future()
        async def wrapper():
            try:
                result = await func()
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        await self.queue.put(wrapper)
        return await future

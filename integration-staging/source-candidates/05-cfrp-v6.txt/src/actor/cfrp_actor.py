"""
CFRPActor – Single-writer message processing lane.

The actor serializes one user's state transitions. This is a process-local
guarantee only; it is not distributed ownership or a durable job queue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Any


MessageFunction = Callable[[], Awaitable[Any]]


class CFRPActor:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.queue: asyncio.Queue[tuple[MessageFunction, asyncio.Future] | None] = asyncio.Queue(maxsize=1000)
        self.running = False
        self._closing = False
        self.task: Optional[asyncio.Task] = None
        logging.info("Actor created for user %s", user_id)

    async def start(self) -> None:
        if self.running and self.task and not self.task.done():
            return
        self._closing = False
        self.running = True
        self.task = asyncio.create_task(self._run(), name=f"cfrp-actor-{self.user_id}")

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        if not self.running:
            if self.task and not self.task.done():
                await asyncio.gather(self.task, return_exceptions=True)
            return
        self._closing = True
        try:
            # The worker keeps consuming while the sentinel waits for queue space.
            await asyncio.wait_for(self.queue.put(None), timeout=timeout_seconds)
            if self.task:
                await asyncio.wait_for(self.task, timeout=timeout_seconds)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if self.task and not self.task.done():
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self._fail_pending(RuntimeError("CFRP actor stopped before processing this message"))
        finally:
            self.running = False
            self._closing = False
            self.task = None

    async def _run(self) -> None:
        while True:
            message = await self.queue.get()
            try:
                if message is None:
                    return
                func, future = message
                if future.cancelled():
                    continue
                try:
                    result = await func()
                except asyncio.CancelledError:
                    if not future.done():
                        future.set_exception(RuntimeError("CFRP actor cancelled during message processing"))
                    raise
                except Exception as exc:
                    if not future.done():
                        future.set_exception(exc)
                    logging.exception("Actor %s message failed", self.user_id)
                else:
                    if not future.done():
                        future.set_result(result)
            finally:
                self.queue.task_done()

    async def send(self, func: MessageFunction) -> Any:
        if not self.running or self._closing or not self.task or self.task.done():
            raise RuntimeError("CFRP actor is not accepting messages")
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((func, future))
        return await future

    def _fail_pending(self, error: Exception) -> None:
        while True:
            try:
                message = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if message is not None:
                    _, future = message
                    if not future.done():
                        future.set_exception(error)
            finally:
                self.queue.task_done()

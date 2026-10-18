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
Message = tuple[MessageFunction, asyncio.Future[Any]]


class CFRPActor:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.queue: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=1000)
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
            self._fail_pending(RuntimeError("CFRP actor is stopped"))
            return
        self._closing = True
        try:
            # Do not cancel the consumer merely because the queue is full. The
            # consumer keeps draining until it sees the sentinel.
            await asyncio.wait_for(self.queue.put(None), timeout=timeout_seconds)
            if self.task:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            if self.task and not self.task.done():
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self._fail_pending(RuntimeError("CFRP actor stopped before processing this message"))
        except asyncio.CancelledError:
            if self.task and not self.task.done():
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self._fail_pending(RuntimeError("CFRP actor stop was cancelled"))
            raise
        finally:
            self.running = False
            self._closing = False
            self.task = None

    async def _run(self) -> None:
        while True:
            message: Message | None = None
            dequeued = False
            future: asyncio.Future[Any] | None = None
            try:
                message = await self.queue.get()
                dequeued = True
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
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A malformed task/message must fail only that message, not
                # permanently kill this user's single-writer lane.
                if future is not None and not future.done():
                    future.set_exception(exc)
                logging.exception("Actor %s loop recovered from a message error", self.user_id)
            finally:
                if dequeued:
                    self.queue.task_done()

    async def send(self, func: MessageFunction) -> Any:
        if not callable(func):
            raise TypeError("actor message must be an async callable")
        if not self.running or self._closing or not self.task or self.task.done():
            raise RuntimeError("CFRP actor is not accepting messages")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        try:
            await self.queue.put((func, future))
        except asyncio.CancelledError:
            future.cancel()
            raise
        try:
            return await future
        except asyncio.CancelledError:
            future.cancel()
            raise

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

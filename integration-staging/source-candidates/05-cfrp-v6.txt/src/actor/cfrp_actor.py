"""
CFRPActor – single-writer message processing lane.

This actor serializes state transitions within one process. It is not a
distributed single-writer mechanism or a durable job queue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

MessageFunction = Callable[[], Awaitable[Any]]
WorkItem = Callable[[], Awaitable[None]]
QueueItem = tuple[WorkItem, asyncio.Future[Any]] | None


class CFRPActor:
    def __init__(self, user_id: str):
        if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 128:
            raise ValueError("user_id must contain 1-128 non-whitespace characters")
        self.user_id = user_id.strip()
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=1000)
        self.running = False
        self._closing = False
        self.task: Optional[asyncio.Task[None]] = None

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
            item: QueueItem = None
            dequeued = False
            try:
                item = await self.queue.get()
                dequeued = True
                if item is None:
                    return

                work, response = item
                if response.cancelled():
                    continue

                # A work item handles its own business exception and resolves
                # the response future; the worker loop never receives that
                # business exception as its own failure state.
                try:
                    await work()
                except asyncio.CancelledError:
                    if not response.done():
                        response.set_exception(RuntimeError("CFRP actor cancelled during message processing"))
                    raise
                except Exception as exc:
                    if not response.done():
                        response.set_exception(exc)
                    logging.exception("Actor %s work item wrapper failed", self.user_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Broken queue items or task infrastructure are logged without
                # skipping queue accounting. A broken worker still fails the
                # run; silently continuing after an infrastructure fault is unsafe.
                logging.exception("Actor %s infrastructure failure", self.user_id)
                raise
            finally:
                if dequeued:
                    self.queue.task_done()

    async def send(self, func: MessageFunction) -> Any:
        if not callable(func):
            raise TypeError("actor message must be an async callable")
        if not self.running or self._closing or not self.task or self.task.done():
            raise RuntimeError("CFRP actor is not accepting messages")

        loop = asyncio.get_running_loop()
        response: asyncio.Future[Any] = loop.create_future()

        async def work_item() -> None:
            try:
                result = await func()
            except asyncio.CancelledError:
                if not response.done():
                    response.set_exception(RuntimeError("CFRP message was cancelled"))
                raise
            except Exception as exc:
                if not response.done():
                    response.set_exception(exc)
            else:
                if not response.done():
                    response.set_result(result)

        try:
            await self.queue.put((work_item, response))
        except asyncio.CancelledError:
            response.cancel()
            raise
        # Caller cancellation must not cancel the queued operation's completion
        # future or interfere with the single-writer worker.
        return await asyncio.shield(response)

    def _fail_pending(self, error: Exception) -> None:
        while True:
            try:
                item = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if item is not None:
                    _, response = item
                    if not response.done():
                        response.set_exception(error)
            finally:
                self.queue.task_done()

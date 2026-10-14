"""Async RabbitMQ event bus – publisher and consumer."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage

from .config import settings

logger = logging.getLogger(__name__)

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventPublisher:
    """Publish JSON messages to the Cirvanna topic exchange."""

    _connection: aio_pika.abc.AbstractRobustConnection | None = None
    _channel: aio_pika.abc.AbstractRobustChannel | None = None
    _exchange: aio_pika.abc.AbstractRobustExchange | None = None

    @classmethod
    async def init(cls) -> None:
        if cls._connection is None:
            cls._connection = await aio_pika.connect_robust(
                settings.rabbitmq_url,
                heartbeat=30,
                client_properties={"service": "cirvanna"},
            )
            cls._channel = await cls._connection.channel()
            await cls._channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)
            cls._exchange = await cls._channel.declare_exchange(
                settings.rabbitmq_exchange,
                ExchangeType.TOPIC,
                durable=True,
            )
            logger.info("Event publisher connected")

    @classmethod
    async def close(cls) -> None:
        if cls._connection is not None:
            await cls._connection.close()
            cls._connection = None
            cls._channel = None
            cls._exchange = None
            logger.info("Event publisher closed")

    @classmethod
    async def publish(cls, routing_key: str, data: dict[str, Any]) -> None:
        await cls.init()
        assert cls._exchange is not None
        message = Message(
            body=json.dumps(data, default=str).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={"routing_key": routing_key},
        )
        await cls._exchange.publish(message, routing_key=routing_key)


class EventConsumer:
    """Subscribe to queues bound to the topic exchange."""

    @staticmethod
    async def subscribe(
        queue_name: str,
        routing_keys: list[str],
        handler: Handler,
        *,
        durable: bool = True,
    ) -> aio_pika.abc.AbstractRobustConnection:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url, heartbeat=30)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)

        exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange,
            ExchangeType.TOPIC,
            durable=True,
        )
        queue = await channel.declare_queue(queue_name, durable=durable)
        for rk in routing_keys:
            await queue.bind(exchange, rk)

        async def _on_message(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=True, ignore_processed=True):
                try:
                    payload = json.loads(message.body)
                    await handler(message.routing_key or "", payload)
                except json.JSONDecodeError as exc:
                    logger.error(f"Invalid JSON on {message.routing_key}: {exc}")
                except Exception:
                    logger.exception(f"Handler failed for {message.routing_key}")
                    raise  # requeue

        await queue.consume(_on_message)
        logger.info(f"Subscribed {queue_name} to {routing_keys}")
        return connection

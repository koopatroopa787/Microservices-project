"""Message broker abstraction for RabbitMQ."""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
from uuid import UUID

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange, AbstractQueue
from tenacity import retry, stop_after_attempt, wait_exponential

from .events import BaseEvent, EventType, deserialize_event

logger = logging.getLogger(__name__)


class MessageBroker:
    """RabbitMQ message broker for event publishing and consumption."""

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchange: Optional[AbstractExchange] = None
        self.dead_letter_exchange: Optional[AbstractExchange] = None
        self.event_handlers: Dict[EventType, list[Callable]] = {}

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def connect(self):
        """Establish connection to RabbitMQ."""
        logger.info("Connecting to RabbitMQ...")
        self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self.channel = await self.connection.channel()

        # Set QoS to process one message at a time for better reliability
        await self.channel.set_qos(prefetch_count=1)

        # Declare main exchange for events
        self.exchange = await self.channel.declare_exchange(
            "saga_events",
            ExchangeType.TOPIC,
            durable=True
        )

        # Declare dead letter exchange
        self.dead_letter_exchange = await self.channel.declare_exchange(
            "saga_events_dlx",
            ExchangeType.TOPIC,
            durable=True
        )

        # Declare dead letter queue
        await self.channel.declare_queue(
            "dead_letter_queue",
            durable=True,
            arguments={
                "x-queue-type": "quorum"
            }
        )

        logger.info("Connected to RabbitMQ successfully")

    async def disconnect(self):
        """Close connection to RabbitMQ."""
        if self.connection:
            await self.connection.close()
            logger.info("Disconnected from RabbitMQ")

    async def publish_event(self, event: BaseEvent, routing_key: Optional[str] = None):
        """
        Publish an event to the message broker.

        Args:
            event: The event to publish
            routing_key: Optional routing key (defaults to event_type)
        """
        if not self.exchange:
            raise RuntimeError("Message broker not connected")

        routing_key = routing_key or event.event_type.value

        # Serialize event
        event_data = event.model_dump(mode='json')

        # Convert UUID to string for JSON serialization
        def uuid_converter(obj):
            if isinstance(obj, UUID):
                return str(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        message_body = json.dumps(event_data, default=uuid_converter)

        # Create message with persistence and metadata
        message = Message(
            body=message_body.encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "event_type": event.event_type.value,
                "event_id": str(event.event_id),
                "correlation_id": str(event.correlation_id),
                "version": event.version
            }
        )

        # Publish to exchange
        await self.exchange.publish(
            message,
            routing_key=routing_key
        )

        logger.info(
            f"Published event: {event.event_type.value} "
            f"(id={event.event_id}, correlation={event.correlation_id})"
        )

    async def subscribe_to_event(
        self,
        event_type: EventType,
        queue_name: str,
        handler: Callable[[BaseEvent], Any],
        max_retries: int = 3
    ):
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            queue_name: Name of the queue to consume from
            handler: Async function to handle the event
            max_retries: Maximum number of retries before sending to DLQ
        """
        if not self.channel:
            raise RuntimeError("Message broker not connected")

        # Declare queue with dead letter exchange configuration
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "saga_events_dlx",
                "x-dead-letter-routing-key": f"dlq.{event_type.value}",
                "x-queue-type": "quorum"
            }
        )

        # Bind queue to exchange with routing key pattern
        await queue.bind(self.exchange, routing_key=event_type.value)

        logger.info(f"Subscribed to {event_type.value} on queue {queue_name}")

        # Start consuming
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process(requeue=False):
                try:
                    # Deserialize event
                    event_data = json.loads(message.body.decode())
                    event = deserialize_event(event_data)

                    # Check retry count
                    retry_count = 0
                    if message.headers and "x-retry-count" in message.headers:
                        retry_count = int(message.headers["x-retry-count"])

                    logger.info(
                        f"Processing event: {event.event_type.value} "
                        f"(id={event.event_id}, retry={retry_count})"
                    )

                    # Call handler
                    await handler(event)

                    logger.info(f"Successfully processed event: {event.event_id}")

                except Exception as e:
                    logger.error(f"Error processing event: {str(e)}", exc_info=True)

                    # Get retry count from headers
                    retry_count = 0
                    if message.headers and "x-retry-count" in message.headers:
                        retry_count = int(message.headers["x-retry-count"])

                    retry_count += 1

                    if retry_count <= max_retries:
                        # Retry by republishing to the same queue
                        logger.info(f"Retrying event (attempt {retry_count}/{max_retries})")

                        headers = dict(message.headers) if message.headers else {}
                        headers["x-retry-count"] = retry_count

                        retry_message = Message(
                            body=message.body,
                            delivery_mode=DeliveryMode.PERSISTENT,
                            content_type=message.content_type,
                            headers=headers
                        )

                        # Delay before retry
                        await asyncio.sleep(min(2 ** retry_count, 60))

                        await self.exchange.publish(
                            retry_message,
                            routing_key=event_type.value
                        )
                    else:
                        # Max retries exceeded, send to dead letter queue
                        logger.error(
                            f"Max retries exceeded for event {message.headers.get('event_id')}. "
                            "Sending to dead letter queue."
                        )
                        # Message will be rejected and sent to DLQ automatically
                        raise

        await queue.consume(process_message)

    async def subscribe_to_pattern(
        self,
        pattern: str,
        queue_name: str,
        handler: Callable[[BaseEvent], Any],
        max_retries: int = 3
    ):
        """
        Subscribe to events matching a pattern.

        Args:
            pattern: Routing key pattern (e.g., "order.*", "*.failed")
            queue_name: Name of the queue to consume from
            handler: Async function to handle the event
            max_retries: Maximum number of retries before sending to DLQ
        """
        if not self.channel:
            raise RuntimeError("Message broker not connected")

        # Declare queue with dead letter exchange configuration
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "saga_events_dlx",
                "x-dead-letter-routing-key": f"dlq.{pattern}",
                "x-queue-type": "quorum"
            }
        )

        # Bind queue to exchange with routing key pattern
        await queue.bind(self.exchange, routing_key=pattern)

        logger.info(f"Subscribed to pattern '{pattern}' on queue {queue_name}")

        # Start consuming (similar to subscribe_to_event)
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process(requeue=False):
                try:
                    # Deserialize event
                    event_data = json.loads(message.body.decode())
                    event = deserialize_event(event_data)

                    logger.info(f"Processing event: {event.event_type.value} (id={event.event_id})")

                    # Call handler
                    await handler(event)

                    logger.info(f"Successfully processed event: {event.event_id}")

                except Exception as e:
                    logger.error(f"Error processing event: {str(e)}", exc_info=True)

                    # Get retry count
                    retry_count = 0
                    if message.headers and "x-retry-count" in message.headers:
                        retry_count = int(message.headers["x-retry-count"])

                    retry_count += 1

                    if retry_count <= max_retries:
                        logger.info(f"Retrying event (attempt {retry_count}/{max_retries})")

                        headers = dict(message.headers) if message.headers else {}
                        headers["x-retry-count"] = retry_count

                        retry_message = Message(
                            body=message.body,
                            delivery_mode=DeliveryMode.PERSISTENT,
                            content_type=message.content_type,
                            headers=headers
                        )

                        await asyncio.sleep(min(2 ** retry_count, 60))

                        # Republish with original routing key
                        routing_key = message.routing_key or pattern
                        await self.exchange.publish(retry_message, routing_key=routing_key)
                    else:
                        logger.error(f"Max retries exceeded. Sending to dead letter queue.")
                        raise

        await queue.consume(process_message)

    async def get_dead_letter_messages(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Retrieve messages from the dead letter queue for inspection."""
        if not self.channel:
            raise RuntimeError("Message broker not connected")

        dead_letter_queue = await self.channel.get_queue("dead_letter_queue")

        messages = []
        for _ in range(limit):
            message = await dead_letter_queue.get(timeout=1.0)
            if not message:
                break

            event_data = json.loads(message.body.decode())
            messages.append({
                "event": event_data,
                "headers": dict(message.headers) if message.headers else {},
                "routing_key": message.routing_key
            })
            await message.ack()

        return messages

    async def replay_event(self, event: BaseEvent):
        """
        Replay an event from dead letter queue.

        Args:
            event: Event to replay
        """
        # Remove retry count and republish
        await self.publish_event(event)
        logger.info(f"Replayed event: {event.event_id}")

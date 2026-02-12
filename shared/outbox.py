"""
Outbox pattern implementation for reliable event publishing.

The outbox pattern ensures that events are published exactly once by:
1. Saving events to an outbox table in the same transaction as business logic
2. Publishing events from the outbox in a separate process
3. Marking events as published after successful delivery
"""
import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, String, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from .events import BaseEvent, deserialize_event
from .message_broker import MessageBroker

logger = logging.getLogger(__name__)

Base = declarative_base()


class OutboxStatus(str, Enum):
    """Status of outbox messages."""
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class OutboxMessage(Base):
    """Outbox table for transactional event publishing."""

    __tablename__ = "outbox"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id = Column(PGUUID(as_uuid=True), nullable=False, unique=True)
    event_type = Column(String(100), nullable=False)
    aggregate_id = Column(PGUUID(as_uuid=True), nullable=False)
    event_data = Column(Text, nullable=False)  # JSON serialized event
    status = Column(String(20), default=OutboxStatus.PENDING.value, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)
    retry_count = Column(String(20), default="0")
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_outbox_status_created", "status", "created_at"),
        Index("ix_outbox_aggregate_id", "aggregate_id"),
    )


class OutboxPublisher:
    """Publishes events from the outbox to the message broker."""

    def __init__(
        self,
        session_factory,
        message_broker: MessageBroker,
        poll_interval: int = 1,
        batch_size: int = 100,
        max_retries: int = 3
    ):
        """
        Initialize outbox publisher.

        Args:
            session_factory: Async session factory for database access
            message_broker: Message broker for publishing events
            poll_interval: Seconds to wait between polls
            batch_size: Number of messages to process per batch
            max_retries: Maximum retry attempts for failed publishes
        """
        self.session_factory = session_factory
        self.message_broker = message_broker
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the outbox publisher."""
        if self._running:
            logger.warning("Outbox publisher already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_and_publish())
        logger.info("Outbox publisher started")

    async def stop(self):
        """Stop the outbox publisher."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Outbox publisher stopped")

    async def _poll_and_publish(self):
        """Poll the outbox and publish pending messages."""
        while self._running:
            try:
                await self._publish_pending_messages()
            except Exception as e:
                logger.error(f"Error in outbox publisher: {str(e)}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _publish_pending_messages(self):
        """Fetch and publish pending messages from the outbox."""
        async with self.session_factory() as session:
            # Fetch pending messages
            query = (
                select(OutboxMessage)
                .where(OutboxMessage.status == OutboxStatus.PENDING.value)
                .order_by(OutboxMessage.created_at)
                .limit(self.batch_size)
            )

            result = await session.execute(query)
            messages = result.scalars().all()

            if not messages:
                return

            logger.info(f"Processing {len(messages)} pending outbox messages")

            for message in messages:
                try:
                    # Deserialize event
                    event_data = json.loads(message.event_data)
                    event = deserialize_event(event_data)

                    # Publish to message broker
                    await self.message_broker.publish_event(event)

                    # Mark as published
                    message.status = OutboxStatus.PUBLISHED.value
                    message.published_at = datetime.utcnow()

                    logger.info(f"Published event {message.event_id} from outbox")

                except Exception as e:
                    logger.error(
                        f"Failed to publish event {message.event_id}: {str(e)}",
                        exc_info=True
                    )

                    # Increment retry count
                    retry_count = int(message.retry_count)
                    retry_count += 1
                    message.retry_count = str(retry_count)
                    message.error_message = str(e)

                    # Mark as failed if max retries exceeded
                    if retry_count >= self.max_retries:
                        message.status = OutboxStatus.FAILED.value
                        logger.error(
                            f"Event {message.event_id} exceeded max retries. "
                            "Marked as failed."
                        )

            await session.commit()

    async def retry_failed_messages(self, limit: int = 100):
        """
        Retry failed messages.

        Args:
            limit: Maximum number of messages to retry
        """
        async with self.session_factory() as session:
            query = (
                select(OutboxMessage)
                .where(OutboxMessage.status == OutboxStatus.FAILED.value)
                .order_by(OutboxMessage.created_at)
                .limit(limit)
            )

            result = await session.execute(query)
            messages = result.scalars().all()

            for message in messages:
                # Reset status and retry count
                message.status = OutboxStatus.PENDING.value
                message.retry_count = "0"
                message.error_message = None

            await session.commit()

            logger.info(f"Reset {len(messages)} failed messages for retry")


async def save_event_to_outbox(session: AsyncSession, event: BaseEvent):
    """
    Save an event to the outbox table.

    This should be called in the same transaction as the business logic
    to ensure atomicity.

    Args:
        session: Database session
        event: Event to save
    """
    # Convert UUID to string for JSON serialization
    def uuid_converter(obj):
        if isinstance(obj, UUID):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    event_data = event.model_dump(mode='json')
    event_json = json.dumps(event_data, default=uuid_converter)

    outbox_message = OutboxMessage(
        event_id=event.event_id,
        event_type=event.event_type.value,
        aggregate_id=event.aggregate_id,
        event_data=event_json,
        status=OutboxStatus.PENDING.value,
        created_at=datetime.utcnow()
    )

    session.add(outbox_message)

    logger.debug(f"Saved event {event.event_id} to outbox")

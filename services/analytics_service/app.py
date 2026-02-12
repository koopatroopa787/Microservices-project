"""Analytics Service FastAPI application."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from redis import asyncio as aioredis

from shared.config import Settings
from shared.events import (
    BaseEvent,
    EventType,
    OrderConfirmedEvent,
    OrderFailedEvent,
    OrderPlacedEvent,
    PaymentFailedEvent,
    PaymentProcessedEvent,
)
from shared.message_broker import MessageBroker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="analytics-service",
    service_port=8006,
)

# Message broker and Redis
message_broker = MessageBroker(settings.rabbitmq_url)
redis_client: Optional[aioredis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    global redis_client

    # Startup
    logger.info("Starting Analytics Service...")

    # Connect to Redis
    redis_client = await aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )

    await message_broker.connect()
    await subscribe_to_events()

    logger.info("Analytics Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Analytics Service...")
    await message_broker.disconnect()
    if redis_client:
        await redis_client.close()


app = FastAPI(title="Analytics Service", lifespan=lifespan)


# Response models
class MetricsResponse(BaseModel):
    """Real-time metrics response."""
    total_orders: int
    confirmed_orders: int
    failed_orders: int
    total_revenue: float
    payment_success_rate: float
    average_order_value: float


class EventStatsResponse(BaseModel):
    """Event statistics response."""
    event_type: str
    count: int


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "analytics-service"}


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get real-time business metrics."""
    if not redis_client:
        return MetricsResponse(
            total_orders=0,
            confirmed_orders=0,
            failed_orders=0,
            total_revenue=0.0,
            payment_success_rate=0.0,
            average_order_value=0.0,
        )

    # Fetch metrics from Redis
    total_orders = int(await redis_client.get("metrics:total_orders") or 0)
    confirmed_orders = int(await redis_client.get("metrics:confirmed_orders") or 0)
    failed_orders = int(await redis_client.get("metrics:failed_orders") or 0)
    total_revenue = float(await redis_client.get("metrics:total_revenue") or 0.0)

    payment_attempts = int(await redis_client.get("metrics:payment_attempts") or 0)
    payment_successes = int(await redis_client.get("metrics:payment_successes") or 0)

    payment_success_rate = (
        (payment_successes / payment_attempts * 100) if payment_attempts > 0 else 0.0
    )

    average_order_value = (
        (total_revenue / confirmed_orders) if confirmed_orders > 0 else 0.0
    )

    return MetricsResponse(
        total_orders=total_orders,
        confirmed_orders=confirmed_orders,
        failed_orders=failed_orders,
        total_revenue=total_revenue,
        payment_success_rate=round(payment_success_rate, 2),
        average_order_value=round(average_order_value, 2),
    )


@app.get("/events/stats")
async def get_event_stats():
    """Get event type statistics."""
    if not redis_client:
        return []

    stats = []
    for event_type in EventType:
        count = int(await redis_client.get(f"events:count:{event_type.value}") or 0)
        if count > 0:
            stats.append(EventStatsResponse(event_type=event_type.value, count=count))

    return stats


@app.get("/orders/recent")
async def get_recent_orders():
    """Get recent order events."""
    if not redis_client:
        return []

    # Fetch recent orders from sorted set
    recent = await redis_client.zrevrange("orders:recent", 0, 9, withscores=True)

    orders = []
    for order_data, timestamp in recent:
        order_info = json.loads(order_data)
        order_info["timestamp"] = datetime.fromtimestamp(timestamp).isoformat()
        orders.append(order_info)

    return orders


# Analytics Logic
async def track_event(event: BaseEvent):
    """Track event in Redis."""
    if not redis_client:
        return

    # Increment event counter
    await redis_client.incr(f"events:count:{event.event_type.value}")

    # Store event in time-series (last 1000 events)
    event_data = {
        "event_id": str(event.event_id),
        "event_type": event.event_type.value,
        "aggregate_id": str(event.aggregate_id),
        "correlation_id": str(event.correlation_id),
        "timestamp": event.timestamp.isoformat(),
    }

    await redis_client.zadd(
        "events:timeline",
        {json.dumps(event_data): event.timestamp.timestamp()}
    )

    # Keep only last 1000 events
    await redis_client.zremrangebyrank("events:timeline", 0, -1001)


async def update_order_metrics(event: OrderPlacedEvent):
    """Update order metrics."""
    if not redis_client:
        return

    await redis_client.incr("metrics:total_orders")

    # Add to recent orders
    order_data = {
        "order_id": str(event.aggregate_id),
        "customer_id": str(event.customer_id),
        "total_amount": event.total_amount,
        "items_count": len(event.items),
    }

    await redis_client.zadd(
        "orders:recent",
        {json.dumps(order_data): event.timestamp.timestamp()}
    )

    # Keep only last 100 orders
    await redis_client.zremrangebyrank("orders:recent", 0, -101)


async def update_confirmed_metrics(event: OrderConfirmedEvent):
    """Update confirmed order metrics."""
    if not redis_client:
        return

    await redis_client.incr("metrics:confirmed_orders")


async def update_failed_metrics(event: OrderFailedEvent):
    """Update failed order metrics."""
    if not redis_client:
        return

    await redis_client.incr("metrics:failed_orders")


async def update_payment_metrics(event: PaymentProcessedEvent):
    """Update payment metrics."""
    if not redis_client:
        return

    await redis_client.incr("metrics:payment_attempts")
    await redis_client.incr("metrics:payment_successes")

    # Update revenue
    current_revenue = float(await redis_client.get("metrics:total_revenue") or 0.0)
    await redis_client.set("metrics:total_revenue", current_revenue + event.amount)


async def update_payment_failed_metrics(event: PaymentFailedEvent):
    """Update payment failure metrics."""
    if not redis_client:
        return

    await redis_client.incr("metrics:payment_attempts")


# Event Handlers
async def subscribe_to_events():
    """Subscribe to all events for analytics."""

    async def handle_order_placed(event: OrderPlacedEvent):
        """Handle order placed event."""
        await track_event(event)
        await update_order_metrics(event)
        logger.info(f"Analytics: Order placed {event.aggregate_id}")

    async def handle_order_confirmed(event: OrderConfirmedEvent):
        """Handle order confirmed event."""
        await track_event(event)
        await update_confirmed_metrics(event)
        logger.info(f"Analytics: Order confirmed {event.order_id}")

    async def handle_order_failed(event: OrderFailedEvent):
        """Handle order failed event."""
        await track_event(event)
        await update_failed_metrics(event)
        logger.info(f"Analytics: Order failed {event.order_id}")

    async def handle_payment_processed(event: PaymentProcessedEvent):
        """Handle payment processed event."""
        await track_event(event)
        await update_payment_metrics(event)
        logger.info(f"Analytics: Payment processed ${event.amount}")

    async def handle_payment_failed(event: PaymentFailedEvent):
        """Handle payment failed event."""
        await track_event(event)
        await update_payment_failed_metrics(event)
        logger.info(f"Analytics: Payment failed for order {event.order_id}")

    async def handle_all_events(event: BaseEvent):
        """Track all events."""
        await track_event(event)

    # Subscribe to specific events for detailed analytics
    await message_broker.subscribe_to_event(
        EventType.ORDER_PLACED,
        "analytics_service_order_placed",
        handle_order_placed,
    )

    await message_broker.subscribe_to_event(
        EventType.ORDER_CONFIRMED,
        "analytics_service_order_confirmed",
        handle_order_confirmed,
    )

    await message_broker.subscribe_to_event(
        EventType.ORDER_FAILED,
        "analytics_service_order_failed",
        handle_order_failed,
    )

    await message_broker.subscribe_to_event(
        EventType.PAYMENT_PROCESSED,
        "analytics_service_payment_processed",
        handle_payment_processed,
    )

    await message_broker.subscribe_to_event(
        EventType.PAYMENT_FAILED,
        "analytics_service_payment_failed",
        handle_payment_failed,
    )

    logger.info("Subscribed to analytics events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

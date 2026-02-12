"""Notification Service FastAPI application."""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from shared.config import Settings
from shared.events import (
    BaseEvent,
    EventType,
    OrderConfirmedEvent,
    OrderFailedEvent,
    PaymentProcessedEvent,
    ShippingScheduledEvent,
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
    service_name="notification-service",
    service_port=8005,
)

# Message broker
message_broker = MessageBroker(settings.rabbitmq_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""

    # Startup
    logger.info("Starting Notification Service...")

    await message_broker.connect()
    await subscribe_to_events()

    logger.info("Notification Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Notification Service...")
    await message_broker.disconnect()


app = FastAPI(title="Notification Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "notification-service"}


# Notification Logic
async def send_email(recipient: str, subject: str, body: str):
    """
    Send email notification.

    In a real system, this would integrate with SendGrid, SES, or similar.
    """
    logger.info(f"[EMAIL] To: {recipient}")
    logger.info(f"[EMAIL] Subject: {subject}")
    logger.info(f"[EMAIL] Body: {body}")
    logger.info("-" * 60)


async def send_sms(recipient: str, message: str):
    """
    Send SMS notification.

    In a real system, this would integrate with Twilio, SNS, or similar.
    """
    logger.info(f"[SMS] To: {recipient}")
    logger.info(f"[SMS] Message: {message}")
    logger.info("-" * 60)


# Event Handlers
async def subscribe_to_events():
    """Subscribe to all order-related events for notifications."""

    async def handle_payment_processed(event: PaymentProcessedEvent):
        """Notify customer of successful payment."""
        await send_email(
            recipient=f"customer_{event.metadata.get('customer_id', 'unknown')}@example.com",
            subject="Payment Confirmed",
            body=f"Your payment of ${event.amount} has been processed successfully. "
                 f"Order ID: {event.order_id}"
        )

        await send_sms(
            recipient="+1234567890",
            message=f"Payment of ${event.amount} confirmed for order {str(event.order_id)[:8]}"
        )

    async def handle_order_confirmed(event: OrderConfirmedEvent):
        """Notify customer of order confirmation."""
        await send_email(
            recipient=f"customer_{event.metadata.get('customer_id', 'unknown')}@example.com",
            subject="Order Confirmed",
            body=f"Your order {event.order_id} has been confirmed and is being prepared for shipment."
        )

    async def handle_shipping_scheduled(event: ShippingScheduledEvent):
        """Notify customer of shipping."""
        estimated_delivery = event.estimated_delivery.strftime("%Y-%m-%d") if event.estimated_delivery else "TBD"

        await send_email(
            recipient=f"customer_{event.metadata.get('customer_id', 'unknown')}@example.com",
            subject="Order Shipped",
            body=f"Your order {event.order_id} has been shipped! "
                 f"Estimated delivery: {estimated_delivery}"
        )

        await send_sms(
            recipient="+1234567890",
            message=f"Your order {str(event.order_id)[:8]} has been shipped! Delivery: {estimated_delivery}"
        )

    async def handle_order_failed(event: OrderFailedEvent):
        """Notify customer of order failure."""
        await send_email(
            recipient=f"customer_{event.metadata.get('customer_id', 'unknown')}@example.com",
            subject="Order Failed",
            body=f"We're sorry, but your order {event.order_id} could not be processed. "
                 f"Reason: {event.reason}. Please contact support or try again."
        )

    async def log_all_events(event: BaseEvent):
        """Log all events for audit purposes."""
        logger.info(
            f"Event received: {event.event_type.value} "
            f"(id={event.event_id}, correlation={event.correlation_id})"
        )

    # Subscribe to specific events for targeted notifications
    await message_broker.subscribe_to_event(
        EventType.PAYMENT_PROCESSED,
        "notification_service_payment",
        handle_payment_processed,
    )

    await message_broker.subscribe_to_event(
        EventType.ORDER_CONFIRMED,
        "notification_service_order_confirmed",
        handle_order_confirmed,
    )

    await message_broker.subscribe_to_event(
        EventType.SHIPPING_SCHEDULED,
        "notification_service_shipping",
        handle_shipping_scheduled,
    )

    await message_broker.subscribe_to_event(
        EventType.ORDER_FAILED,
        "notification_service_order_failed",
        handle_order_failed,
    )

    # Subscribe to all events for logging
    await message_broker.subscribe_to_pattern(
        "*.*",
        "notification_service_all_events",
        log_all_events,
    )

    logger.info("Subscribed to notification events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

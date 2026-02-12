"""Shipping Service FastAPI application."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import Settings
from shared.database import Database
from shared.events import (
    EventType,
    OrderConfirmedEvent,
    ShippingScheduledEvent,
)
from shared.message_broker import MessageBroker
from shared.outbox import OutboxPublisher, save_event_to_outbox

from .models import Shipment, ShipmentStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="shipping-service",
    service_port=8004,
    postgres_db="shipping_db",
)

# Database and message broker
database = Database(settings.database_url)
message_broker = MessageBroker(settings.rabbitmq_url)
outbox_publisher: Optional[OutboxPublisher] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    global outbox_publisher

    # Startup
    logger.info("Starting Shipping Service...")

    from shared.outbox import Base as OutboxBase
    from .models import Base

    Base.metadata.tables.update(OutboxBase.metadata.tables)
    await database.create_tables()
    await message_broker.connect()

    outbox_publisher = OutboxPublisher(
        session_factory=database.session_factory,
        message_broker=message_broker,
    )
    await outbox_publisher.start()
    await subscribe_to_events()

    logger.info("Shipping Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Shipping Service...")
    if outbox_publisher:
        await outbox_publisher.stop()
    await message_broker.disconnect()
    await database.close()


app = FastAPI(title="Shipping Service", lifespan=lifespan)


async def get_session() -> AsyncSession:
    """Get database session."""
    async with database.session_factory() as session:
        yield session


# Request/Response models
class ShipmentResponse(BaseModel):
    """Shipment response."""
    id: UUID
    order_id: UUID
    status: str
    tracking_number: Optional[str]
    estimated_delivery: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


# API Endpoints
@app.get("/shipments/{order_id}", response_model=ShipmentResponse)
async def get_shipment(order_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get shipment by order ID."""
    result = await session.execute(
        select(Shipment).where(Shipment.order_id == order_id)
    )
    shipment = result.scalar_one_or_none()

    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    return ShipmentResponse(
        id=shipment.id,
        order_id=shipment.order_id,
        status=shipment.status,
        tracking_number=shipment.tracking_number,
        estimated_delivery=shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
        created_at=shipment.created_at.isoformat(),
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "shipping-service"}


# Event Handlers
async def subscribe_to_events():
    """Subscribe to relevant events."""

    async def handle_order_confirmed(event: OrderConfirmedEvent):
        """Handle order confirmed event and schedule shipping."""
        async with database.session_factory() as session:
            try:
                # Check if shipment already exists (idempotency)
                result = await session.execute(
                    select(Shipment).where(Shipment.order_id == event.order_id)
                )
                existing_shipment = result.scalar_one_or_none()

                if existing_shipment:
                    logger.info(f"Shipment for order {event.order_id} already exists")
                    return

                # Get order details from event metadata
                # In a real system, we might fetch this from Order Service API
                shipping_address = event.metadata.get("shipping_address", {})

                # Calculate estimated delivery (3-5 business days)
                estimated_delivery = datetime.utcnow() + timedelta(days=4)

                # Create shipment
                shipment = Shipment(
                    id=uuid4(),
                    order_id=event.order_id,
                    correlation_id=event.correlation_id,
                    status=ShipmentStatus.SCHEDULED.value,
                    shipping_address=shipping_address,
                    estimated_delivery=estimated_delivery,
                    tracking_number=f"TRK{uuid4().hex[:12].upper()}",
                )

                session.add(shipment)

                # Emit SHIPPING_SCHEDULED event
                scheduled_event = ShippingScheduledEvent(
                    aggregate_id=event.order_id,
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                    order_id=event.order_id,
                    shipping_id=shipment.id,
                    estimated_delivery=estimated_delivery,
                    shipping_address=shipping_address,
                )

                await save_event_to_outbox(session, scheduled_event)

                await session.commit()

                logger.info(
                    f"Scheduled shipping for order {event.order_id} "
                    f"(tracking: {shipment.tracking_number})"
                )

            except Exception as e:
                logger.error(f"Error scheduling shipping: {str(e)}", exc_info=True)
                await session.rollback()
                raise

    # Subscribe to events
    await message_broker.subscribe_to_event(
        EventType.ORDER_CONFIRMED,
        "shipping_service_order_confirmed",
        handle_order_confirmed,
    )

    logger.info("Subscribed to shipping events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

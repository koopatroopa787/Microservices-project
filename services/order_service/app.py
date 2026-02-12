"""Order Service FastAPI application."""
import logging
from contextlib import asynccontextmanager
from typing import List
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import Settings
from shared.database import Database
from shared.events import (
    EventType,
    InventoryReserveFailedEvent,
    InventoryReservedEvent,
    PaymentFailedEvent,
    PaymentProcessedEvent,
)
from shared.message_broker import MessageBroker
from shared.outbox import OutboxMessage, OutboxPublisher

from .models import Order, SagaLog
from .saga_orchestrator import SagaOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="order-service",
    service_port=8001,
    postgres_db="order_db",
)

# Database and message broker
database = Database(settings.database_url)
message_broker = MessageBroker(settings.rabbitmq_url)
outbox_publisher: OutboxPublisher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    global outbox_publisher

    # Startup
    logger.info("Starting Order Service...")

    # Import models to register them with Base
    from shared.outbox import Base as OutboxBase
    from .models import Base

    # Merge the bases
    Base.metadata.tables.update(OutboxBase.metadata.tables)

    # Create tables
    await database.create_tables()

    # Connect to message broker
    await message_broker.connect()

    # Start outbox publisher
    outbox_publisher = OutboxPublisher(
        session_factory=database.session_factory,
        message_broker=message_broker,
        poll_interval=1,
        batch_size=100,
    )
    await outbox_publisher.start()

    # Subscribe to events
    await subscribe_to_events()

    logger.info("Order Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Order Service...")
    if outbox_publisher:
        await outbox_publisher.stop()
    await message_broker.disconnect()
    await database.close()


app = FastAPI(title="Order Service", lifespan=lifespan)


# Dependency to get database session
async def get_session() -> AsyncSession:
    """Get database session."""
    async with database.session_factory() as session:
        yield session


# Request/Response models
class OrderItem(BaseModel):
    """Order item."""
    product_id: UUID
    quantity: int
    price: float


class CreateOrderRequest(BaseModel):
    """Request to create a new order."""
    customer_id: UUID
    items: List[OrderItem]
    shipping_address: dict
    payment_method: dict


class OrderResponse(BaseModel):
    """Order response."""
    id: UUID
    customer_id: UUID
    status: str
    total_amount: float
    items: List[dict]
    shipping_address: dict
    correlation_id: UUID
    created_at: str

    class Config:
        from_attributes = True


class SagaLogResponse(BaseModel):
    """Saga log response."""
    id: UUID
    order_id: UUID
    step: str
    event_type: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


# API Endpoints
@app.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    request: CreateOrderRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new order and start the saga.

    This endpoint initiates the order processing saga:
    1. Creates the order
    2. Emits ORDER_PLACED event
    3. Requests inventory reservation
    """
    orchestrator = SagaOrchestrator(session)

    # Calculate total amount
    total_amount = sum(item.price * item.quantity for item in request.items)

    # Start saga
    order = await orchestrator.start_order_saga(
        customer_id=request.customer_id,
        items=[item.model_dump() for item in request.items],
        total_amount=total_amount,
        shipping_address=request.shipping_address,
        payment_method=request.payment_method,
    )

    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_amount=order.total_amount,
        items=order.items,
        shipping_address=order.shipping_address,
        correlation_id=order.correlation_id,
        created_at=order.created_at.isoformat(),
    )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get order by ID."""
    result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_amount=order.total_amount,
        items=order.items,
        shipping_address=order.shipping_address,
        correlation_id=order.correlation_id,
        created_at=order.created_at.isoformat(),
    )


@app.get("/orders/{order_id}/saga-logs", response_model=List[SagaLogResponse])
async def get_saga_logs(order_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get saga execution logs for an order."""
    result = await session.execute(
        select(SagaLog)
        .where(SagaLog.order_id == order_id)
        .order_by(SagaLog.created_at)
    )
    logs = result.scalars().all()

    return [
        SagaLogResponse(
            id=log.id,
            order_id=log.order_id,
            step=log.step,
            event_type=log.event_type,
            status=log.status,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "order-service"}


# Event Handlers
async def subscribe_to_events():
    """Subscribe to relevant events."""

    async def handle_inventory_reserved(event: InventoryReservedEvent):
        """Handle inventory reserved event."""
        async with database.session_factory() as session:
            orchestrator = SagaOrchestrator(session)
            await orchestrator.handle_inventory_reserved(event)

    async def handle_inventory_reserve_failed(event: InventoryReserveFailedEvent):
        """Handle inventory reservation failure."""
        async with database.session_factory() as session:
            orchestrator = SagaOrchestrator(session)
            await orchestrator.handle_inventory_reserve_failed(event)

    async def handle_payment_processed(event: PaymentProcessedEvent):
        """Handle payment processed event."""
        async with database.session_factory() as session:
            orchestrator = SagaOrchestrator(session)
            await orchestrator.handle_payment_processed(event)

    async def handle_payment_failed(event: PaymentFailedEvent):
        """Handle payment failure."""
        async with database.session_factory() as session:
            orchestrator = SagaOrchestrator(session)
            await orchestrator.handle_payment_failed(event)

    # Subscribe to events
    await message_broker.subscribe_to_event(
        EventType.INVENTORY_RESERVED,
        "order_service_inventory_reserved",
        handle_inventory_reserved,
    )

    await message_broker.subscribe_to_event(
        EventType.INVENTORY_RESERVE_FAILED,
        "order_service_inventory_failed",
        handle_inventory_reserve_failed,
    )

    await message_broker.subscribe_to_event(
        EventType.PAYMENT_PROCESSED,
        "order_service_payment_processed",
        handle_payment_processed,
    )

    await message_broker.subscribe_to_event(
        EventType.PAYMENT_FAILED,
        "order_service_payment_failed",
        handle_payment_failed,
    )

    logger.info("Subscribed to saga events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

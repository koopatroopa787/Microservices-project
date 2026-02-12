"""Inventory Service FastAPI application."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import Settings
from shared.database import Database
from shared.events import (
    EventType,
    InventoryReleasedEvent,
    InventoryReserveFailedEvent,
    InventoryReserveRequestedEvent,
    InventoryReservedEvent,
)
from shared.message_broker import MessageBroker
from shared.outbox import OutboxPublisher, save_event_to_outbox

from .models import Product, Reservation, ReservationStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="inventory-service",
    service_port=8002,
    postgres_db="inventory_db",
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
    logger.info("Starting Inventory Service...")

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

    # Seed initial data
    await seed_initial_data()

    logger.info("Inventory Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Inventory Service...")
    if outbox_publisher:
        await outbox_publisher.stop()
    await message_broker.disconnect()
    await database.close()


app = FastAPI(title="Inventory Service", lifespan=lifespan)


async def get_session() -> AsyncSession:
    """Get database session."""
    async with database.session_factory() as session:
        yield session


# Request/Response models
class ProductRequest(BaseModel):
    """Request to create/update a product."""
    name: str
    description: Optional[str] = None
    price: float
    quantity: int


class ProductResponse(BaseModel):
    """Product response."""
    id: UUID
    name: str
    description: Optional[str]
    price: float
    available_quantity: int
    reserved_quantity: int

    class Config:
        from_attributes = True


class ReservationResponse(BaseModel):
    """Reservation response."""
    id: UUID
    order_id: UUID
    status: str
    items: List[dict]
    created_at: str

    class Config:
        from_attributes = True


# API Endpoints
@app.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    request: ProductRequest,
    session: AsyncSession = Depends(get_session)
):
    """Create a new product."""
    product = Product(
        id=uuid4(),
        name=request.name,
        description=request.description,
        price=request.price,
        available_quantity=request.quantity,
    )

    session.add(product)
    await session.commit()
    await session.refresh(product)

    logger.info(f"Created product {product.id}: {product.name}")

    return product


@app.get("/products", response_model=List[ProductResponse])
async def list_products(session: AsyncSession = Depends(get_session)):
    """List all products."""
    result = await session.execute(select(Product))
    products = result.scalars().all()
    return products


@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get product by ID."""
    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@app.get("/reservations/{order_id}", response_model=ReservationResponse)
async def get_reservation(order_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get reservation by order ID."""
    result = await session.execute(
        select(Reservation).where(Reservation.order_id == order_id)
    )
    reservation = result.scalar_one_or_none()

    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    return ReservationResponse(
        id=reservation.id,
        order_id=reservation.order_id,
        status=reservation.status,
        items=reservation.items,
        created_at=reservation.created_at.isoformat(),
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "inventory-service"}


# Event Handlers
async def subscribe_to_events():
    """Subscribe to relevant events."""

    async def handle_reserve_requested(event: InventoryReserveRequestedEvent):
        """Handle inventory reservation request."""
        async with database.session_factory() as session:
            try:
                # Check if reservation already exists (idempotency)
                result = await session.execute(
                    select(Reservation).where(Reservation.order_id == event.order_id)
                )
                existing_reservation = result.scalar_one_or_none()

                if existing_reservation:
                    logger.info(f"Reservation for order {event.order_id} already exists")

                    # Re-emit success event (idempotent)
                    success_event = InventoryReservedEvent(
                        aggregate_id=event.aggregate_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                        order_id=event.order_id,
                        reservation_id=existing_reservation.id,
                        items=existing_reservation.items,
                    )
                    await save_event_to_outbox(session, success_event)
                    await session.commit()
                    return

                # Check availability
                unavailable_items = []
                for item in event.items:
                    product_id = UUID(item["product_id"]) if isinstance(item["product_id"], str) else item["product_id"]
                    quantity = item["quantity"]

                    result = await session.execute(
                        select(Product).where(Product.id == product_id)
                    )
                    product = result.scalar_one_or_none()

                    if not product or product.available_quantity < quantity:
                        unavailable_items.append({
                            "product_id": str(product_id),
                            "requested": quantity,
                            "available": product.available_quantity if product else 0,
                        })

                if unavailable_items:
                    # Emit failure event
                    failure_event = InventoryReserveFailedEvent(
                        aggregate_id=event.aggregate_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                        order_id=event.order_id,
                        reason="Insufficient inventory",
                        unavailable_items=unavailable_items,
                    )
                    await save_event_to_outbox(session, failure_event)
                    await session.commit()

                    logger.warning(
                        f"Insufficient inventory for order {event.order_id}: {unavailable_items}"
                    )
                    return

                # Reserve inventory
                for item in event.items:
                    product_id = UUID(item["product_id"]) if isinstance(item["product_id"], str) else item["product_id"]
                    quantity = item["quantity"]

                    await session.execute(
                        update(Product)
                        .where(Product.id == product_id)
                        .values(
                            available_quantity=Product.available_quantity - quantity,
                            reserved_quantity=Product.reserved_quantity + quantity,
                        )
                    )

                # Create reservation
                reservation = Reservation(
                    id=uuid4(),
                    order_id=event.order_id,
                    correlation_id=event.correlation_id,
                    status=ReservationStatus.ACTIVE.value,
                    items=event.items,
                )
                session.add(reservation)

                # Emit success event
                success_event = InventoryReservedEvent(
                    aggregate_id=event.aggregate_id,
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                    order_id=event.order_id,
                    reservation_id=reservation.id,
                    items=event.items,
                )
                await save_event_to_outbox(session, success_event)

                await session.commit()

                logger.info(f"Reserved inventory for order {event.order_id}")

            except Exception as e:
                logger.error(f"Error processing reservation request: {str(e)}", exc_info=True)
                await session.rollback()
                raise

    async def handle_release_inventory(event: InventoryReleasedEvent):
        """Handle inventory release (compensating action)."""
        async with database.session_factory() as session:
            try:
                # Get reservation
                result = await session.execute(
                    select(Reservation).where(
                        Reservation.id == event.reservation_id,
                        Reservation.order_id == event.order_id
                    )
                )
                reservation = result.scalar_one_or_none()

                if not reservation:
                    logger.warning(f"Reservation {event.reservation_id} not found")
                    return

                if reservation.status == ReservationStatus.RELEASED.value:
                    logger.info(f"Reservation {event.reservation_id} already released")
                    return

                # Release inventory
                for item in reservation.items:
                    product_id = UUID(item["product_id"]) if isinstance(item["product_id"], str) else item["product_id"]
                    quantity = item["quantity"]

                    await session.execute(
                        update(Product)
                        .where(Product.id == product_id)
                        .values(
                            available_quantity=Product.available_quantity + quantity,
                            reserved_quantity=Product.reserved_quantity - quantity,
                        )
                    )

                # Update reservation status
                reservation.status = ReservationStatus.RELEASED.value
                reservation.released_at = datetime.utcnow()

                await session.commit()

                logger.info(f"Released reservation {event.reservation_id} for order {event.order_id}")

            except Exception as e:
                logger.error(f"Error releasing inventory: {str(e)}", exc_info=True)
                await session.rollback()
                raise

    # Subscribe to events
    await message_broker.subscribe_to_event(
        EventType.INVENTORY_RESERVE_REQUESTED,
        "inventory_service_reserve",
        handle_reserve_requested,
    )

    await message_broker.subscribe_to_event(
        EventType.INVENTORY_RELEASED,
        "inventory_service_release",
        handle_release_inventory,
    )

    logger.info("Subscribed to inventory events")


async def seed_initial_data():
    """Seed initial product data for testing."""
    async with database.session_factory() as session:
        # Check if products already exist
        result = await session.execute(select(Product))
        if result.scalars().first():
            logger.info("Products already exist, skipping seed")
            return

        # Create sample products
        products = [
            Product(
                id=uuid4(),
                name="Laptop",
                description="High-performance laptop",
                price=1200.00,
                available_quantity=50,
            ),
            Product(
                id=uuid4(),
                name="Mouse",
                description="Wireless mouse",
                price=25.00,
                available_quantity=200,
            ),
            Product(
                id=uuid4(),
                name="Keyboard",
                description="Mechanical keyboard",
                price=80.00,
                available_quantity=100,
            ),
            Product(
                id=uuid4(),
                name="Monitor",
                description="27-inch 4K monitor",
                price=350.00,
                available_quantity=30,
            ),
        ]

        for product in products:
            session.add(product)

        await session.commit()

        logger.info("Seeded initial product data")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

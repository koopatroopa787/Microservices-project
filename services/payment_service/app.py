"""Payment Service FastAPI application."""
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime
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
    PaymentFailedEvent,
    PaymentProcessedEvent,
    PaymentRefundedEvent,
    PaymentRequestedEvent,
)
from shared.message_broker import MessageBroker
from shared.outbox import OutboxPublisher, save_event_to_outbox

from .models import Refund, Transaction, TransactionStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="payment-service",
    service_port=8003,
    postgres_db="payment_db",
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
    logger.info("Starting Payment Service...")

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

    logger.info("Payment Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Payment Service...")
    if outbox_publisher:
        await outbox_publisher.stop()
    await message_broker.disconnect()
    await database.close()


app = FastAPI(title="Payment Service", lifespan=lifespan)


async def get_session() -> AsyncSession:
    """Get database session."""
    async with database.session_factory() as session:
        yield session


# Request/Response models
class TransactionResponse(BaseModel):
    """Transaction response."""
    id: UUID
    order_id: UUID
    customer_id: UUID
    amount: float
    currency: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


# API Endpoints
@app.get("/transactions/{order_id}", response_model=TransactionResponse)
async def get_transaction(order_id: UUID, session: AsyncSession = Depends(get_session)):
    """Get transaction by order ID."""
    result = await session.execute(
        select(Transaction).where(Transaction.order_id == order_id)
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return TransactionResponse(
        id=transaction.id,
        order_id=transaction.order_id,
        customer_id=transaction.customer_id,
        amount=transaction.amount,
        currency=transaction.currency,
        status=transaction.status,
        created_at=transaction.created_at.isoformat(),
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "payment-service"}


# Payment Processing Logic
async def process_payment(
    session: AsyncSession,
    order_id: UUID,
    customer_id: UUID,
    amount: float,
    currency: str,
    payment_method: dict,
) -> tuple[bool, Optional[str]]:
    """
    Simulate payment processing.

    In a real system, this would integrate with a payment gateway like Stripe, PayPal, etc.

    Returns:
        Tuple of (success, error_message)
    """
    # Simulate payment processing delay
    import asyncio
    await asyncio.sleep(0.5)

    # Simulate random payment failures (20% failure rate for demo)
    if random.random() < 0.2:
        error_messages = [
            "Insufficient funds",
            "Card declined",
            "Payment gateway timeout",
            "Invalid payment method",
        ]
        return False, random.choice(error_messages)

    # Simulate successful payment
    return True, None


# Event Handlers
async def subscribe_to_events():
    """Subscribe to relevant events."""

    async def handle_payment_requested(event: PaymentRequestedEvent):
        """Handle payment request event (with idempotency)."""
        async with database.session_factory() as session:
            try:
                # Check for existing transaction (idempotency)
                idempotency_key = f"payment_{event.order_id}"

                result = await session.execute(
                    select(Transaction).where(
                        Transaction.idempotency_key == idempotency_key
                    )
                )
                existing_transaction = result.scalar_one_or_none()

                if existing_transaction:
                    logger.info(
                        f"Transaction for order {event.order_id} already exists "
                        f"(status={existing_transaction.status})"
                    )

                    # Re-emit the appropriate event based on existing status
                    if existing_transaction.status == TransactionStatus.COMPLETED.value:
                        success_event = PaymentProcessedEvent(
                            aggregate_id=event.aggregate_id,
                            correlation_id=event.correlation_id,
                            causation_id=event.event_id,
                            order_id=event.order_id,
                            transaction_id=existing_transaction.id,
                            amount=existing_transaction.amount,
                            currency=existing_transaction.currency,
                        )
                        await save_event_to_outbox(session, success_event)

                    elif existing_transaction.status == TransactionStatus.FAILED.value:
                        failure_event = PaymentFailedEvent(
                            aggregate_id=event.aggregate_id,
                            correlation_id=event.correlation_id,
                            causation_id=event.event_id,
                            order_id=event.order_id,
                            reason=existing_transaction.error_message or "Unknown error",
                            error_code="PAYMENT_FAILED",
                        )
                        await save_event_to_outbox(session, failure_event)

                    await session.commit()
                    return

                # Create new transaction
                transaction = Transaction(
                    id=uuid4(),
                    order_id=event.order_id,
                    customer_id=event.customer_id,
                    correlation_id=event.correlation_id,
                    idempotency_key=idempotency_key,
                    amount=event.amount,
                    currency=event.currency,
                    status=TransactionStatus.PROCESSING.value,
                    payment_method=event.payment_method,
                )

                session.add(transaction)
                await session.commit()

                logger.info(f"Processing payment for order {event.order_id}")

                # Process payment
                success, error_message = await process_payment(
                    session=session,
                    order_id=event.order_id,
                    customer_id=event.customer_id,
                    amount=event.amount,
                    currency=event.currency,
                    payment_method=event.payment_method,
                )

                if success:
                    # Update transaction
                    transaction.status = TransactionStatus.COMPLETED.value
                    transaction.processed_at = datetime.utcnow()
                    transaction.payment_gateway_response = {
                        "status": "success",
                        "gateway_transaction_id": str(uuid4()),
                    }

                    # Emit success event
                    success_event = PaymentProcessedEvent(
                        aggregate_id=event.aggregate_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                        order_id=event.order_id,
                        transaction_id=transaction.id,
                        amount=event.amount,
                        currency=event.currency,
                    )
                    await save_event_to_outbox(session, success_event)

                    logger.info(f"Payment processed successfully for order {event.order_id}")

                else:
                    # Update transaction
                    transaction.status = TransactionStatus.FAILED.value
                    transaction.processed_at = datetime.utcnow()
                    transaction.error_message = error_message
                    transaction.payment_gateway_response = {
                        "status": "failed",
                        "error": error_message,
                    }

                    # Emit failure event
                    failure_event = PaymentFailedEvent(
                        aggregate_id=event.aggregate_id,
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                        order_id=event.order_id,
                        reason=error_message or "Payment processing failed",
                        error_code="PAYMENT_FAILED",
                    )
                    await save_event_to_outbox(session, failure_event)

                    logger.warning(
                        f"Payment failed for order {event.order_id}: {error_message}"
                    )

                await session.commit()

            except Exception as e:
                logger.error(f"Error processing payment: {str(e)}", exc_info=True)
                await session.rollback()
                raise

    async def handle_payment_refund(event: PaymentRefundedEvent):
        """Handle payment refund request (compensating action)."""
        async with database.session_factory() as session:
            try:
                # Get original transaction
                result = await session.execute(
                    select(Transaction).where(Transaction.id == event.transaction_id)
                )
                transaction = result.scalar_one_or_none()

                if not transaction:
                    logger.warning(f"Transaction {event.transaction_id} not found")
                    return

                if transaction.status != TransactionStatus.COMPLETED.value:
                    logger.warning(
                        f"Cannot refund transaction {event.transaction_id} "
                        f"with status {transaction.status}"
                    )
                    return

                # Check if already refunded
                result = await session.execute(
                    select(Refund).where(
                        Refund.transaction_id == event.transaction_id,
                        Refund.status == "completed"
                    )
                )
                existing_refund = result.scalar_one_or_none()

                if existing_refund:
                    logger.info(f"Transaction {event.transaction_id} already refunded")
                    return

                # Create refund
                refund = Refund(
                    id=event.refund_id,
                    transaction_id=event.transaction_id,
                    order_id=event.order_id,
                    correlation_id=event.correlation_id,
                    amount=event.amount,
                    reason="Order cancellation",
                    status="completed",
                    processed_at=datetime.utcnow(),
                    refund_gateway_response={
                        "status": "success",
                        "gateway_refund_id": str(uuid4()),
                    },
                )

                session.add(refund)

                # Update transaction status
                transaction.status = TransactionStatus.REFUNDED.value

                await session.commit()

                logger.info(f"Refunded transaction {event.transaction_id}")

            except Exception as e:
                logger.error(f"Error processing refund: {str(e)}", exc_info=True)
                await session.rollback()
                raise

    # Subscribe to events
    await message_broker.subscribe_to_event(
        EventType.PAYMENT_REQUESTED,
        "payment_service_payment_requested",
        handle_payment_requested,
    )

    await message_broker.subscribe_to_event(
        EventType.PAYMENT_REFUNDED,
        "payment_service_refund",
        handle_payment_refund,
    )

    logger.info("Subscribed to payment events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

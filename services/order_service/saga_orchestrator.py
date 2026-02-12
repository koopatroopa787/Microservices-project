"""Saga orchestrator for order processing."""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.events import (
    BaseEvent,
    EventType,
    InventoryReleasedEvent,
    InventoryReserveFailedEvent,
    InventoryReserveRequestedEvent,
    InventoryReservedEvent,
    OrderCancelledEvent,
    OrderConfirmedEvent,
    OrderFailedEvent,
    OrderPlacedEvent,
    PaymentFailedEvent,
    PaymentProcessedEvent,
    PaymentRefundedEvent,
    PaymentRequestedEvent,
    ShippingScheduledEvent,
)
from shared.outbox import save_event_to_outbox

from .models import Order, OrderStatus, SagaLog, SagaStep

logger = logging.getLogger(__name__)


class SagaOrchestrator:
    """Orchestrates the order processing saga."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_order_saga(
        self,
        customer_id: UUID,
        items: list[dict],
        total_amount: float,
        shipping_address: dict,
        payment_method: dict
    ) -> Order:
        """
        Start a new order saga.

        Args:
            customer_id: Customer placing the order
            items: List of items to order
            total_amount: Total order amount
            shipping_address: Shipping address
            payment_method: Payment method details

        Returns:
            Created order
        """
        # Create order
        correlation_id = uuid4()
        order = Order(
            id=uuid4(),
            customer_id=customer_id,
            status=OrderStatus.PENDING.value,
            current_saga_step=SagaStep.ORDER_PLACED.value,
            items=items,
            total_amount=total_amount,
            shipping_address=shipping_address,
            correlation_id=correlation_id,
        )

        self.session.add(order)

        # Create ORDER_PLACED event
        event = OrderPlacedEvent(
            aggregate_id=order.id,
            correlation_id=correlation_id,
            customer_id=customer_id,
            items=items,
            total_amount=total_amount,
            shipping_address=shipping_address,
        )

        # Save event to outbox (will be published transactionally)
        await save_event_to_outbox(self.session, event)

        # Log saga step
        await self._log_saga_step(
            order_id=order.id,
            correlation_id=correlation_id,
            step=SagaStep.ORDER_PLACED.value,
            event_type=EventType.ORDER_PLACED.value,
            event_id=event.event_id,
            status="completed",
        )

        # Immediately request inventory reservation
        inventory_event = InventoryReserveRequestedEvent(
            aggregate_id=order.id,
            correlation_id=correlation_id,
            causation_id=event.event_id,
            order_id=order.id,
            items=[{"product_id": item["product_id"], "quantity": item["quantity"]}
                   for item in items],
        )

        await save_event_to_outbox(self.session, inventory_event)

        order.current_saga_step = SagaStep.INVENTORY_RESERVATION.value

        await self._log_saga_step(
            order_id=order.id,
            correlation_id=correlation_id,
            step=SagaStep.INVENTORY_RESERVATION.value,
            event_type=EventType.INVENTORY_RESERVE_REQUESTED.value,
            event_id=inventory_event.event_id,
            status="started",
        )

        await self.session.commit()

        logger.info(f"Started order saga for order {order.id}")

        return order

    async def handle_inventory_reserved(self, event: InventoryReservedEvent):
        """
        Handle successful inventory reservation.

        Next step: Request payment processing.
        """
        order = await self._get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        # Update order status
        order.status = OrderStatus.INVENTORY_RESERVED.value
        order.reservation_id = event.reservation_id
        order.current_saga_step = SagaStep.PAYMENT_PROCESSING.value

        # Log step completion
        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.INVENTORY_RESERVATION.value,
            event_type=event.event_type.value,
            event_id=event.event_id,
            status="completed",
        )

        # Request payment
        payment_event = PaymentRequestedEvent(
            aggregate_id=order.id,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            order_id=order.id,
            customer_id=order.customer_id,
            amount=order.total_amount,
            payment_method={"type": "credit_card"},  # Simplified for demo
        )

        await save_event_to_outbox(self.session, payment_event)

        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.PAYMENT_PROCESSING.value,
            event_type=EventType.PAYMENT_REQUESTED.value,
            event_id=payment_event.event_id,
            status="started",
        )

        await self.session.commit()

        logger.info(f"Inventory reserved for order {order.id}, requesting payment")

    async def handle_inventory_reserve_failed(self, event: InventoryReserveFailedEvent):
        """
        Handle inventory reservation failure.

        Compensating action: Cancel order.
        """
        order = await self._get_order(event.order_id)
        if not order:
            return

        # Update order status
        order.status = OrderStatus.FAILED.value
        order.error_message = event.reason

        # Log failure
        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.INVENTORY_RESERVATION.value,
            event_type=event.event_type.value,
            event_id=event.event_id,
            status="failed",
            error_message=event.reason,
        )

        # Emit ORDER_FAILED event
        failed_event = OrderFailedEvent(
            aggregate_id=order.id,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            order_id=order.id,
            reason=event.reason,
            failed_step="inventory_reservation",
        )

        await save_event_to_outbox(self.session, failed_event)

        await self.session.commit()

        logger.error(f"Order {order.id} failed: {event.reason}")

    async def handle_payment_processed(self, event: PaymentProcessedEvent):
        """
        Handle successful payment processing.

        Next step: Confirm order and schedule shipping.
        """
        order = await self._get_order(event.order_id)
        if not order:
            return

        # Update order status
        order.status = OrderStatus.CONFIRMED.value
        order.transaction_id = event.transaction_id
        order.current_saga_step = SagaStep.ORDER_CONFIRMATION.value

        # Log step completion
        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.PAYMENT_PROCESSING.value,
            event_type=event.event_type.value,
            event_id=event.event_id,
            status="completed",
        )

        # Emit ORDER_CONFIRMED event
        confirmed_event = OrderConfirmedEvent(
            aggregate_id=order.id,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            order_id=order.id,
        )

        await save_event_to_outbox(self.session, confirmed_event)

        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.ORDER_CONFIRMATION.value,
            event_type=EventType.ORDER_CONFIRMED.value,
            event_id=confirmed_event.event_id,
            status="completed",
        )

        await self.session.commit()

        logger.info(f"Order {order.id} confirmed successfully")

    async def handle_payment_failed(self, event: PaymentFailedEvent):
        """
        Handle payment processing failure.

        Compensating action: Release inventory reservation.
        """
        order = await self._get_order(event.order_id)
        if not order:
            return

        # Update order status
        order.status = OrderStatus.FAILED.value
        order.error_message = event.reason

        # Log failure
        await self._log_saga_step(
            order_id=order.id,
            correlation_id=event.correlation_id,
            step=SagaStep.PAYMENT_PROCESSING.value,
            event_type=event.event_type.value,
            event_id=event.event_id,
            status="failed",
            error_message=event.reason,
        )

        # Compensating action: Release inventory
        if order.reservation_id:
            release_event = InventoryReleasedEvent(
                aggregate_id=order.id,
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
                order_id=order.id,
                reservation_id=order.reservation_id,
            )

            await save_event_to_outbox(self.session, release_event)

            await self._log_saga_step(
                order_id=order.id,
                correlation_id=event.correlation_id,
                step="compensation",
                event_type=EventType.INVENTORY_RELEASED.value,
                event_id=release_event.event_id,
                status="compensated",
            )

        # Emit ORDER_FAILED event
        failed_event = OrderFailedEvent(
            aggregate_id=order.id,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            order_id=order.id,
            reason=event.reason,
            failed_step="payment_processing",
        )

        await save_event_to_outbox(self.session, failed_event)

        await self.session.commit()

        logger.error(f"Order {order.id} failed at payment: {event.reason}")

    async def _get_order(self, order_id: UUID) -> Optional[Order]:
        """Fetch order by ID."""
        result = await self.session.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def _log_saga_step(
        self,
        order_id: UUID,
        correlation_id: UUID,
        step: str,
        event_type: str,
        event_id: UUID,
        status: str,
        error_message: Optional[str] = None,
    ):
        """Log a saga execution step."""
        log = SagaLog(
            order_id=order_id,
            correlation_id=correlation_id,
            step=step,
            event_type=event_type,
            event_id=event_id,
            status=status,
            error_message=error_message,
        )

        self.session.add(log)

"""Database models for Order Service."""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.database import Base


class OrderStatus(str, Enum):
    """Order status in the saga."""
    PENDING = "pending"
    INVENTORY_RESERVED = "inventory_reserved"
    PAYMENT_PROCESSING = "payment_processing"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SagaStep(str, Enum):
    """Steps in the order saga."""
    ORDER_PLACED = "order_placed"
    INVENTORY_RESERVATION = "inventory_reservation"
    PAYMENT_PROCESSING = "payment_processing"
    SHIPPING_SCHEDULING = "shipping_scheduling"
    ORDER_CONFIRMATION = "order_confirmation"


class Order(Base):
    """Order aggregate root."""

    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(String(50), default=OrderStatus.PENDING.value, nullable=False, index=True)
    current_saga_step = Column(String(50), default=SagaStep.ORDER_PLACED.value)

    # Order details
    items = Column(JSONB, nullable=False)  # [{"product_id": UUID, "quantity": int, "price": float}]
    total_amount = Column(Float, nullable=False)
    shipping_address = Column(JSONB, nullable=False)

    # Saga tracking
    correlation_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    reservation_id = Column(UUID(as_uuid=True), nullable=True)
    transaction_id = Column(UUID(as_uuid=True), nullable=True)
    shipping_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_correlation_id", "correlation_id"),
    )


class SagaLog(Base):
    """Audit log for saga execution steps."""

    __tablename__ = "saga_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    step = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(20), nullable=False)  # started, completed, failed, compensated

    event_data = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_saga_logs_order_created", "order_id", "created_at"),
    )

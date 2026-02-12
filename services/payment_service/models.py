"""Database models for Payment Service."""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.database import Base


class TransactionStatus(str, Enum):
    """Transaction status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Transaction(Base):
    """Payment transaction."""

    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Idempotency key (order_id serves as idempotency key)
    idempotency_key = Column(String(255), unique=True, nullable=False)

    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(String(20), default=TransactionStatus.PENDING.value, nullable=False, index=True)

    payment_method = Column(JSONB, nullable=False)
    payment_gateway_response = Column(JSONB, nullable=True)

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_transactions_status_created", "status", "created_at"),
    )


class Refund(Base):
    """Payment refund (compensating action)."""

    __tablename__ = "refunds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    transaction_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False)

    amount = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)

    refund_gateway_response = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_refunds_transaction_id", "transaction_id"),
    )

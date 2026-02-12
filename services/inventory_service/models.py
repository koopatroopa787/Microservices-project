"""Database models for Inventory Service."""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.database import Base


class ReservationStatus(str, Enum):
    """Reservation status."""
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class Product(Base):
    """Product inventory."""

    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    available_quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_products_name", "name"),
    )


class Reservation(Base):
    """Inventory reservation for orders."""

    __tablename__ = "reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    status = Column(String(20), default=ReservationStatus.ACTIVE.value, nullable=False)
    items = Column(JSONB, nullable=False)  # [{"product_id": UUID, "quantity": int}]

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    released_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_reservations_status_created", "status", "created_at"),
    )

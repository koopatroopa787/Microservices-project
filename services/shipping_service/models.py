"""Database models for Shipping Service."""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from shared.database import Base


class ShipmentStatus(str, Enum):
    """Shipment status."""
    SCHEDULED = "scheduled"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


class Shipment(Base):
    """Shipment tracking."""

    __tablename__ = "shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    status = Column(String(20), default=ShipmentStatus.SCHEDULED.value, nullable=False, index=True)
    tracking_number = Column(String(100), nullable=True, unique=True)

    shipping_address = Column(JSONB, nullable=False)
    estimated_delivery = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    dispatched_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_shipments_status_created", "status", "created_at"),
    )

"""Event definitions and base classes for the saga pattern."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types in the order processing saga."""

    # Order events
    ORDER_PLACED = "order.placed"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_FAILED = "order.failed"

    # Inventory events
    INVENTORY_RESERVE_REQUESTED = "inventory.reserve.requested"
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_RESERVE_FAILED = "inventory.reserve.failed"
    INVENTORY_RELEASED = "inventory.released"

    # Payment events
    PAYMENT_REQUESTED = "payment.requested"
    PAYMENT_PROCESSED = "payment.processed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"

    # Shipping events
    SHIPPING_SCHEDULED = "shipping.scheduled"
    SHIPPING_DISPATCHED = "shipping.dispatched"
    SHIPPING_DELIVERED = "shipping.delivered"
    SHIPPING_FAILED = "shipping.failed"

    # Notification events
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_FAILED = "notification.failed"


class EventStatus(str, Enum):
    """Status of event processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class BaseEvent(BaseModel):
    """Base event model with common fields."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    aggregate_id: UUID  # ID of the main entity (order_id in most cases)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1)
    correlation_id: UUID  # For tracing across services
    causation_id: Optional[UUID] = None  # ID of event that caused this one
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Order Events
class OrderPlacedEvent(BaseEvent):
    """Event emitted when a new order is placed."""
    event_type: EventType = EventType.ORDER_PLACED
    customer_id: UUID
    items: list[Dict[str, Any]]  # [{"product_id": UUID, "quantity": int, "price": float}]
    total_amount: float
    shipping_address: Dict[str, str]


class OrderConfirmedEvent(BaseEvent):
    """Event emitted when order is confirmed."""
    event_type: EventType = EventType.ORDER_CONFIRMED
    order_id: UUID


class OrderCancelledEvent(BaseEvent):
    """Event emitted when order is cancelled."""
    event_type: EventType = EventType.ORDER_CANCELLED
    order_id: UUID
    reason: str


class OrderFailedEvent(BaseEvent):
    """Event emitted when order processing fails."""
    event_type: EventType = EventType.ORDER_FAILED
    order_id: UUID
    reason: str
    failed_step: str


# Inventory Events
class InventoryReserveRequestedEvent(BaseEvent):
    """Event requesting inventory reservation."""
    event_type: EventType = EventType.INVENTORY_RESERVE_REQUESTED
    order_id: UUID
    items: list[Dict[str, Any]]  # [{"product_id": UUID, "quantity": int}]


class InventoryReservedEvent(BaseEvent):
    """Event emitted when inventory is reserved."""
    event_type: EventType = EventType.INVENTORY_RESERVED
    order_id: UUID
    reservation_id: UUID
    items: list[Dict[str, Any]]


class InventoryReserveFailedEvent(BaseEvent):
    """Event emitted when inventory reservation fails."""
    event_type: EventType = EventType.INVENTORY_RESERVE_FAILED
    order_id: UUID
    reason: str
    unavailable_items: list[Dict[str, Any]]


class InventoryReleasedEvent(BaseEvent):
    """Event emitted when inventory is released (compensating action)."""
    event_type: EventType = EventType.INVENTORY_RELEASED
    order_id: UUID
    reservation_id: UUID


# Payment Events
class PaymentRequestedEvent(BaseEvent):
    """Event requesting payment processing."""
    event_type: EventType = EventType.PAYMENT_REQUESTED
    order_id: UUID
    customer_id: UUID
    amount: float
    currency: str = "USD"
    payment_method: Dict[str, Any]


class PaymentProcessedEvent(BaseEvent):
    """Event emitted when payment is processed."""
    event_type: EventType = EventType.PAYMENT_PROCESSED
    order_id: UUID
    transaction_id: UUID
    amount: float
    currency: str = "USD"


class PaymentFailedEvent(BaseEvent):
    """Event emitted when payment processing fails."""
    event_type: EventType = EventType.PAYMENT_FAILED
    order_id: UUID
    reason: str
    error_code: Optional[str] = None


class PaymentRefundedEvent(BaseEvent):
    """Event emitted when payment is refunded (compensating action)."""
    event_type: EventType = EventType.PAYMENT_REFUNDED
    order_id: UUID
    transaction_id: UUID
    refund_id: UUID
    amount: float


# Shipping Events
class ShippingScheduledEvent(BaseEvent):
    """Event emitted when shipping is scheduled."""
    event_type: EventType = EventType.SHIPPING_SCHEDULED
    order_id: UUID
    shipping_id: UUID
    estimated_delivery: datetime
    shipping_address: Dict[str, str]


class ShippingDispatchedEvent(BaseEvent):
    """Event emitted when shipment is dispatched."""
    event_type: EventType = EventType.SHIPPING_DISPATCHED
    order_id: UUID
    shipping_id: UUID
    tracking_number: str


class ShippingDeliveredEvent(BaseEvent):
    """Event emitted when shipment is delivered."""
    event_type: EventType = EventType.SHIPPING_DELIVERED
    order_id: UUID
    shipping_id: UUID
    delivered_at: datetime


# Notification Events
class NotificationSentEvent(BaseEvent):
    """Event emitted when notification is sent."""
    event_type: EventType = EventType.NOTIFICATION_SENT
    notification_type: str  # email, sms, push
    recipient: str
    subject: str


class NotificationFailedEvent(BaseEvent):
    """Event emitted when notification fails."""
    event_type: EventType = EventType.NOTIFICATION_FAILED
    notification_type: str
    recipient: str
    reason: str


# Event Registry for deserialization
EVENT_REGISTRY: Dict[EventType, type[BaseEvent]] = {
    EventType.ORDER_PLACED: OrderPlacedEvent,
    EventType.ORDER_CONFIRMED: OrderConfirmedEvent,
    EventType.ORDER_CANCELLED: OrderCancelledEvent,
    EventType.ORDER_FAILED: OrderFailedEvent,

    EventType.INVENTORY_RESERVE_REQUESTED: InventoryReserveRequestedEvent,
    EventType.INVENTORY_RESERVED: InventoryReservedEvent,
    EventType.INVENTORY_RESERVE_FAILED: InventoryReserveFailedEvent,
    EventType.INVENTORY_RELEASED: InventoryReleasedEvent,

    EventType.PAYMENT_REQUESTED: PaymentRequestedEvent,
    EventType.PAYMENT_PROCESSED: PaymentProcessedEvent,
    EventType.PAYMENT_FAILED: PaymentFailedEvent,
    EventType.PAYMENT_REFUNDED: PaymentRefundedEvent,

    EventType.SHIPPING_SCHEDULED: ShippingScheduledEvent,
    EventType.SHIPPING_DISPATCHED: ShippingDispatchedEvent,
    EventType.SHIPPING_DELIVERED: ShippingDeliveredEvent,
}


def deserialize_event(event_data: Dict[str, Any]) -> BaseEvent:
    """Deserialize event from dictionary."""
    event_type = EventType(event_data["event_type"])
    event_class = EVENT_REGISTRY.get(event_type, BaseEvent)
    return event_class(**event_data)

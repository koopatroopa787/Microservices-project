# Architecture Deep Dive

## System Architecture

This document provides a detailed explanation of the architectural patterns and design decisions in the Event-Driven Order Processing System.

## Table of Contents

1. [Saga Pattern](#saga-pattern)
2. [Event Sourcing](#event-sourcing)
3. [Outbox Pattern](#outbox-pattern)
4. [Idempotency](#idempotency)
5. [Event Versioning](#event-versioning)
6. [Dead Letter Queues](#dead-letter-queues)
7. [Service Communication](#service-communication)
8. [Data Consistency](#data-consistency)

---

## Saga Pattern

### What is a Saga?

A saga is a sequence of local transactions where each transaction updates data within a single service. If a step fails, the saga executes compensating transactions to undo the changes made by preceding transactions.

### Types of Sagas

1. **Choreography-based** (used in this system)
   - Services produce and listen to events
   - No central coordinator
   - Each service knows what to do when an event occurs

2. **Orchestration-based**
   - Central orchestrator tells services what to do
   - Orchestrator manages the saga flow
   - We use Order Service as a lightweight orchestrator

### Our Saga Implementation

```
Order Saga Flow:

SUCCESS PATH:
1. Order Service creates order → ORDER_PLACED
2. Inventory Service reserves stock → INVENTORY_RESERVED
3. Payment Service processes payment → PAYMENT_PROCESSED
4. Order Service confirms order → ORDER_CONFIRMED
5. Shipping Service schedules delivery → SHIPPING_SCHEDULED

FAILURE PATH (Payment Fails):
1. Order Service creates order → ORDER_PLACED
2. Inventory Service reserves stock → INVENTORY_RESERVED
3. Payment Service fails payment → PAYMENT_FAILED
4. Order Service triggers compensation → INVENTORY_RELEASED
5. Inventory Service releases stock
6. Order Service marks order as failed → ORDER_FAILED
```

### Compensating Transactions

When a step fails, we execute compensating transactions to rollback:

| Failed Step | Compensating Action | Event |
|------------|---------------------|-------|
| Inventory Reservation | N/A (first step) | ORDER_FAILED |
| Payment Processing | Release Inventory | INVENTORY_RELEASED |
| Shipping (future) | Refund Payment + Release Inventory | PAYMENT_REFUNDED, INVENTORY_RELEASED |

### Saga Log

The `saga_logs` table tracks every step:
- Step name
- Event type
- Status (started, completed, failed, compensated)
- Timestamp
- Error messages

This provides:
- Full audit trail
- Debugging capability
- Monitoring and alerting

---

## Event Sourcing

### Principles

Instead of storing current state, we store all state changes as events:

1. **Events are immutable** - Once created, never modified
2. **Events are facts** - They represent things that happened
3. **Current state is derived** - By replaying events

### Benefits

1. **Complete Audit Trail**
   - Every change is recorded
   - Can answer "why did this happen?"

2. **Temporal Queries**
   - Can query state at any point in time
   - "What was the inventory on Monday?"

3. **Event Replay**
   - Rebuild state from events
   - Recover from corruption
   - Create new projections

4. **Debugging**
   - Exact sequence of events
   - Easy to reproduce issues

### Implementation

```python
class BaseEvent:
    event_id: UUID          # Unique identifier
    event_type: EventType   # Type of event
    aggregate_id: UUID      # Entity this affects
    timestamp: datetime     # When it happened
    correlation_id: UUID    # Links related events
    causation_id: UUID      # Event that caused this
    version: int            # Schema version
```

### Event Store

We use two approaches:
1. **Outbox Table** - Transactional event log
2. **Message Broker** - Event stream for consumers

---

## Outbox Pattern

### The Dual-Write Problem

Traditional approach (WRONG):
```python
# 1. Update database
db.save(order)

# 2. Publish event
message_broker.publish(OrderPlaced)

# Problem: What if step 2 fails?
# Order saved but event not published!
```

### Solution: Outbox Pattern

```python
# 1. Update database AND save event in same transaction
with transaction:
    db.save(order)
    db.save_to_outbox(OrderPlaced)

# 2. Separate process publishes from outbox
outbox_publisher.poll_and_publish()
```

### Benefits

1. **Atomicity** - Event saved in same transaction as data
2. **Reliability** - Event guaranteed to be published
3. **Exactly-Once** - No duplicate events
4. **Ordering** - Events published in order

### Implementation

```python
# In service
async def create_order(...):
    async with session.begin():
        # Save business data
        order = Order(...)
        session.add(order)

        # Save event to outbox
        event = OrderPlacedEvent(...)
        await save_event_to_outbox(session, event)

    # Event will be published by OutboxPublisher

# OutboxPublisher (separate process)
async def poll_and_publish():
    while True:
        pending_events = fetch_pending_events()
        for event in pending_events:
            await message_broker.publish(event)
            mark_as_published(event)
```

### Outbox Table Schema

```sql
CREATE TABLE outbox (
    id UUID PRIMARY KEY,
    event_id UUID UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_data TEXT NOT NULL,  -- JSON
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);
```

---

## Idempotency

### Why Idempotency Matters

In distributed systems:
- Networks are unreliable
- Services restart
- Messages can be duplicated
- Retries happen

**Idempotency ensures**: Processing the same request multiple times has the same effect as processing it once.

### Implementation Strategies

#### 1. Idempotency Keys

```python
async def handle_payment_requested(event: PaymentRequestedEvent):
    # Use order_id as idempotency key
    idempotency_key = f"payment_{event.order_id}"

    # Check if already processed
    existing = await db.get_by_idempotency_key(idempotency_key)

    if existing:
        # Already processed - return cached result
        await publish_cached_result(existing)
        return

    # Process payment
    transaction = await process_payment(...)

    # Save with idempotency key
    transaction.idempotency_key = idempotency_key
    await db.save(transaction)
```

#### 2. Natural Idempotency

Some operations are naturally idempotent:
- Setting a value: `user.status = "active"`
- Checking existence: `if product.exists()`

#### 3. Unique Constraints

Database enforces idempotency:
```python
# order_id is unique - duplicate insert fails gracefully
try:
    await db.save(reservation)
except UniqueConstraintError:
    # Already exists - idempotent
    existing = await db.get(order_id)
    return existing
```

### Testing Idempotency

```bash
# Send same request twice
curl -X POST http://localhost:8001/orders ... (save order_id)
curl -X POST http://localhost:8001/orders ... (same order_id)

# Should get same result, no duplicate processing
```

---

## Event Versioning

### The Challenge

Events are immutable, but requirements change:
- Add new fields
- Rename fields
- Change field types
- Remove fields

### Solution: Schema Evolution

#### Version Field

```python
class BaseEvent:
    version: int = 1  # Schema version
```

#### Versioned Event Classes

```python
# Version 1
class OrderPlacedEventV1(BaseEvent):
    version: int = 1
    customer_id: UUID
    items: list[dict]
    total_amount: float

# Version 2 (added shipping info)
class OrderPlacedEventV2(BaseEvent):
    version: int = 2
    customer_id: UUID
    items: list[dict]
    total_amount: float
    shipping_address: dict  # NEW
    shipping_method: str    # NEW
```

#### Deserialization

```python
def deserialize_event(data: dict) -> BaseEvent:
    event_type = data["event_type"]
    version = data.get("version", 1)

    if event_type == "order.placed":
        if version == 1:
            return OrderPlacedEventV1(**data)
        elif version == 2:
            return OrderPlacedEventV2(**data)

    # Default
    return BaseEvent(**data)
```

#### Upcasting

Convert old events to new format:

```python
def upcast_order_placed_v1_to_v2(v1: OrderPlacedEventV1) -> OrderPlacedEventV2:
    return OrderPlacedEventV2(
        **v1.dict(),
        version=2,
        shipping_address={"street": "N/A"},  # Default
        shipping_method="standard"            # Default
    )
```

### Best Practices

1. **Additive Changes** - Prefer adding fields over modifying
2. **Optional Fields** - New fields should be optional
3. **Default Values** - Provide sensible defaults
4. **Version Tracking** - Always include version field
5. **Schema Registry** - Central registry for event schemas

---

## Dead Letter Queues

### Purpose

Handle messages that can't be processed:
- Parsing errors
- Business logic failures
- Service unavailable
- Corrupted data

### Flow

```
1. Message arrives
2. Try to process
3. If fails, retry with exponential backoff
4. After max retries, send to DLQ
5. Manual investigation
6. Fix issue
7. Replay from DLQ
```

### Implementation

```python
async def process_message(message):
    retry_count = message.headers.get("x-retry-count", 0)
    max_retries = 3

    try:
        await handle_event(message)
    except Exception as e:
        retry_count += 1

        if retry_count <= max_retries:
            # Retry with delay
            await asyncio.sleep(2 ** retry_count)
            await republish_with_retry_count(message, retry_count)
        else:
            # Send to DLQ
            await dead_letter_queue.publish(message)
```

### RabbitMQ DLQ Configuration

```python
# Declare queue with DLX
queue = await channel.declare_queue(
    "order_queue",
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.order"
    }
)
```

### Monitoring DLQs

```python
# Check DLQ depth
dlq_messages = await get_dead_letter_messages()

# Alert if threshold exceeded
if len(dlq_messages) > 100:
    send_alert("DLQ threshold exceeded!")
```

### Replay from DLQ

```python
# Inspect message
messages = await get_dead_letter_messages(limit=1)
print(messages[0])

# Fix the issue (deploy fix, fix data, etc.)

# Replay message
await replay_event(messages[0])
```

---

## Service Communication

### Asynchronous Events (Primary)

**Used for**: Saga coordination, notifications, analytics

```python
# Publisher
await message_broker.publish_event(OrderPlacedEvent(...))

# Consumer
await message_broker.subscribe_to_event(
    EventType.ORDER_PLACED,
    queue_name="inventory_service",
    handler=handle_order_placed
)
```

**Benefits**:
- Loose coupling
- Services can be offline
- Natural backpressure
- Easy to add consumers

### Synchronous API (Secondary)

**Used for**: Queries, external integrations

```python
# REST API
@app.get("/orders/{order_id}")
async def get_order(order_id: UUID):
    return await db.get_order(order_id)
```

**When to use**:
- Need immediate response
- Query operations
- External API calls

### Comparison

| Aspect | Async Events | Sync API |
|--------|-------------|----------|
| Coupling | Loose | Tight |
| Resilience | High | Low |
| Latency | Variable | Predictable |
| Use Case | Commands | Queries |

---

## Data Consistency

### Eventual Consistency

We use eventual consistency:
- Changes propagate via events
- Services eventually reach consistent state
- Temporary inconsistencies are acceptable

### Example

```
T0: Order created (status=pending)
T1: Inventory reserved (order.status still pending)
T2: Payment processed (order.status still pending)
T3: Order confirmed event processed (order.status=confirmed)
```

Between T0 and T3, reading order status may show "pending" even though payment is processed. This is acceptable because:
1. The saga is still in progress
2. Final state will be consistent
3. User expectations are set (processing time)

### Handling Inconsistencies

#### 1. Saga Timeout

```python
# If saga doesn't complete in time, trigger compensation
if order.created_at < now() - timedelta(minutes=5):
    if order.status == "pending":
        trigger_saga_timeout_compensation(order)
```

#### 2. Reconciliation

```python
# Periodic job to fix inconsistencies
async def reconcile_orders():
    orphaned_reservations = find_reservations_without_orders()
    for reservation in orphaned_reservations:
        await release_reservation(reservation)
```

#### 3. Monitoring

```python
# Alert on long-running sagas
sagas = get_sagas_older_than(minutes=10)
if sagas:
    alert(f"{len(sagas)} sagas running > 10 minutes")
```

### Strong Consistency (Where Needed)

Some operations require strong consistency:

#### Inventory Reservation

```sql
-- Use row-level locking
BEGIN;
SELECT * FROM products WHERE id = $1 FOR UPDATE;
-- Check availability
-- Reserve inventory
COMMIT;
```

#### Payment Idempotency

```sql
-- Unique constraint ensures no duplicate payments
CREATE UNIQUE INDEX idx_transaction_idempotency
ON transactions(idempotency_key);
```

---

## Scalability

### Horizontal Scaling

All services are stateless and can scale horizontally:

```bash
docker-compose up --scale order-service=3
docker-compose up --scale inventory-service=3
```

### Database Scaling

Each service has its own database:
- Independent scaling
- Read replicas for queries
- Sharding for writes

### Message Broker Scaling

RabbitMQ:
- Clustering for HA
- Partitioned queues for scaling
- Message persistence for durability

### Caching

Redis for:
- Analytics (hot data)
- Session data
- Rate limiting

---

## Observability

### Distributed Tracing

Correlation ID links events across services:

```
correlation_id: abc-123
├─ ORDER_PLACED (order-service)
├─ INVENTORY_RESERVE_REQUESTED (order-service)
├─ INVENTORY_RESERVED (inventory-service)
├─ PAYMENT_REQUESTED (order-service)
├─ PAYMENT_PROCESSED (payment-service)
└─ ORDER_CONFIRMED (order-service)
```

### Logging

Structured logging:
```python
logger.info(
    "Order placed",
    extra={
        "order_id": order.id,
        "correlation_id": order.correlation_id,
        "customer_id": order.customer_id,
        "total_amount": order.total_amount
    }
)
```

### Metrics

Track:
- Order success/failure rate
- Payment success rate
- Saga completion time
- Event processing latency
- Queue depths

---

## Security Considerations

### Event Validation

```python
async def handle_event(event: BaseEvent):
    # Validate event schema
    validate_schema(event)

    # Verify correlation_id
    if not is_valid_correlation_id(event.correlation_id):
        raise InvalidEventError()

    # Check causation chain
    if event.causation_id:
        verify_causation_chain(event)
```

### Idempotency Keys

Prevent replay attacks:
```python
# Check if event already processed
if await is_duplicate_event(event.event_id):
    logger.warning(f"Duplicate event: {event.event_id}")
    return
```

### Data Encryption

- Encrypt sensitive data in events
- Use TLS for message broker
- Encrypt database at rest

---

## Testing Strategy

### Unit Tests

Test individual components:
```python
async def test_inventory_reservation():
    service = InventoryService()
    result = await service.reserve_inventory(order_id, items)
    assert result.success
```

### Integration Tests

Test service interactions:
```python
async def test_order_saga():
    # Place order
    order = await order_service.create_order(...)

    # Wait for saga to complete
    await asyncio.sleep(5)

    # Verify all steps completed
    assert order.status == "confirmed"
    assert inventory_reserved(order.id)
    assert payment_processed(order.id)
```

### Chaos Testing

Simulate failures:
- Kill random services
- Introduce network latency
- Corrupt messages
- Fill disk space

Verify:
- Saga compensations work
- System recovers
- No data loss

---

## Summary

This architecture demonstrates:

✅ **Saga Pattern** - Distributed transactions with compensation
✅ **Event Sourcing** - Complete audit trail
✅ **Outbox Pattern** - Reliable event publishing
✅ **Idempotency** - Safe retries
✅ **Event Versioning** - Schema evolution
✅ **Dead Letter Queues** - Error handling
✅ **Eventual Consistency** - Scalable consistency model
✅ **Observability** - Tracing and monitoring

All essential patterns for building robust, scalable, event-driven systems!

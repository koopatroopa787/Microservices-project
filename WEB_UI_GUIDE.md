# Web UI Dashboard Guide

## Overview

The Web UI provides a beautiful, interactive dashboard for testing and monitoring your event-driven order processing system. It features real-time updates, saga flow visualization, and comprehensive analytics.

## Accessing the Dashboard

```bash
# Start all services
docker-compose up -d

# Open the Web UI
open http://localhost:8000

# Or use make command
make ui
```

## Features

### 1. Service Health Monitoring 💚

At the top of the dashboard, you'll see real-time health status for all services:
- **Order Service** - Saga orchestrator
- **Inventory Service** - Stock management
- **Payment Service** - Payment processing
- **Shipping Service** - Delivery scheduling
- **Notification Service** - Event consumer
- **Analytics Service** - Real-time metrics

Each service shows:
- ✅ Green indicator = Healthy
- ❌ Red indicator = Unhealthy
- ⚫ Gray indicator = Unreachable

**Auto-refresh**: Service health updates every 5 seconds automatically.

### 2. Order Creation Interface 🛒

The left sidebar provides an intuitive form to create orders:

#### Steps to Create an Order:

1. **Select a Product**
   - Dropdown shows all available products
   - Displays product name, price, and available quantity

2. **Enter Quantity**
   - Number input for order quantity
   - Validation ensures quantity is positive

3. **Shipping Address**
   - Pre-filled with sample address
   - Customize street, city, state, and ZIP

4. **Submit Order**
   - Click "Place Order" button
   - Watch the saga execute in real-time!

#### Order Creation Flow:

```
Click "Place Order"
    ↓
Order Created (green notification)
    ↓
Order ID displayed
    ↓
Auto-track saga after 2 seconds
    ↓
View saga flow visualization
```

### 3. Real-time Metrics 📊

Below the order form, view live business metrics:

- **Total Orders** - All orders created
- **Confirmed Orders** - Successfully completed
- **Failed Orders** - Failed due to inventory or payment issues
- **Total Revenue** - Sum of all confirmed orders
- **Payment Success Rate** - Percentage of successful payments
- **Average Order Value** - Mean order amount

**Auto-refresh**: Metrics update every 5 seconds.

### 4. Saga Flow Tracker 🔍

The main panel provides powerful saga tracking:

#### How to Track an Order:

1. Enter Order ID in the search box
2. Click "Track" or press Enter
3. View complete saga execution

#### What You'll See:

**Order Status Card**
- Current order status (Pending, Confirmed, Failed)
- Color-coded indicator:
  - 🟢 Green = Confirmed
  - 🔴 Red = Failed
  - 🟡 Yellow = In Progress
- Order details (amount, items count)

**Saga Execution Steps**
Visual timeline showing each step:

```
✅ Order Placed (completed)
    ↓
✅ Inventory Reservation (completed)
    ↓
✅ Payment Processing (completed)
    ↓
✅ Order Confirmation (completed)
```

Each step shows:
- **Icon**: ✓ (completed), ✗ (failed), ⟳ (in progress), ↶ (compensated)
- **Step name**: Human-readable description
- **Event type**: Technical event name
- **Status**: completed, failed, started, compensated
- **Timestamp**: When the step occurred

**Service Details Cards**
Three cards showing detailed information:

1. **Inventory Card** (Blue)
   - Reservation status
   - Number of items reserved

2. **Payment Card** (Green)
   - Transaction status
   - Payment amount

3. **Shipping Card** (Purple)
   - Shipment status
   - Tracking number

### 5. Event Statistics 📈

Bottom panel shows event counts by type:
- `order.placed`
- `inventory.reserved`
- `payment.processed`
- etc.

Grid layout with count for each event type.

### 6. Recent Orders Feed 🕒

- View the latest orders captured by analytics in a compact feed
- Click any recent order to instantly start tracking its saga
- Includes timestamp, order amount, and item count

### 7. AI Insights Panel 🧠

When tracking an order, the dashboard now provides AI-assisted diagnostics:
- **Fraud risk score and level**
- **Payment success probability**
- **Saga anomaly score and anomaly detection status**

Use **Refresh AI** to re-run analysis on demand.

### 8. Refresh + Theme Controls ⚙️

- Toggle **auto-refresh** on/off
- Select refresh interval (5s / 10s / 15s)
- Switch between **light** and **dark** mode

## Common Workflows

### Workflow 1: Create and Track an Order

1. Select a product from dropdown
2. Enter quantity (e.g., 2)
3. Review shipping address
4. Click "Place Order"
5. **Wait for green success message**
6. Order automatically tracked after 2 seconds
7. Watch saga steps complete in real-time
8. View final status and service details

**Expected Result**: Order status changes from `pending` → `inventory_reserved` → `confirmed`

### Workflow 2: Monitor Payment Failures

Since payment service has a ~20% failure rate:

1. Create multiple orders (use "Place Order" several times)
2. Some will succeed, some will fail
3. For failed orders:
   - Status shows `failed`
   - Saga logs show "Payment Failed"
   - Saga logs show "Compensation" step
   - Inventory automatically released
4. Check metrics to see failure rate

**Expected Result**: Failed orders show compensating transaction (inventory release)

### Workflow 3: Test Insufficient Inventory

1. Note product's available quantity
2. Try to order more than available
3. Watch saga fail at inventory step
4. No payment attempted (saga stopped early)

**Expected Result**: Order status = `failed`, reason = "Insufficient inventory"

### Workflow 4: Monitor System Health

1. Keep dashboard open
2. Stop a service: `docker stop saga_pattern-payment-service-1`
3. Watch service health indicator turn red
4. Try creating an order
5. Saga will hang at payment step
6. Restart service: `docker start saga_pattern-payment-service-1`
7. Watch health indicator turn green
8. Saga continues and completes

**Expected Result**: System handles service failures gracefully

## UI Components

### Auto-Refresh Behavior

The UI automatically refreshes:
- **Service health**: Every 5 seconds
- **Metrics**: Every 5 seconds
- **Event stats**: Every 5 seconds
- **Tracked order**: Every 5 seconds (if an order is being tracked)

### Animations

- **Pulse animation**: Success/error notifications
- **Slide-in animation**: Alert messages
- **Spin animation**: Loading states
- **Color transitions**: Smooth status changes

### Responsive Design

The UI is fully responsive:
- **Desktop**: 3-column layout
- **Tablet**: 2-column layout
- **Mobile**: Single column, stacked layout

## Keyboard Shortcuts

- **Enter** in Order ID field: Track order
- **Enter** in search box: Track order
- **F5**: Refresh page
- **Ctrl/Cmd + R**: Refresh page

## Color Coding

### Status Colors

- **Green**: Success, healthy, completed
- **Red**: Error, unhealthy, failed
- **Yellow**: Warning, in progress, pending
- **Blue**: Compensated, informational
- **Purple**: Highlighted, special actions
- **Gray**: Neutral, unreachable, disabled

### Service Colors

- Order Service: Purple
- Inventory Service: Blue
- Payment Service: Green
- Shipping Service: Purple
- Notification Service: Orange
- Analytics Service: Green

## Tips & Tricks

### Tip 1: Keep Dashboard Open
Leave the dashboard open in a browser tab to monitor system in real-time as you run tests from the command line.

### Tip 2: Multiple Orders
Create several orders in quick succession to see how the system handles concurrent sagas.

### Tip 3: Track Failed Orders
Failed orders are just as interesting as successful ones! Track them to see compensating transactions in action.

### Tip 4: Watch Metrics Change
Create 5-10 orders and watch the metrics update in real-time. Great for demos!

### Tip 5: Use Browser DevTools
Open browser console to see API calls and responses for debugging.

## Troubleshooting

### Dashboard Not Loading

```bash
# Check if web-ui service is running
docker ps | grep web-ui

# Check logs
docker logs saga_pattern-web-ui-1

# Restart service
docker restart saga_pattern-web-ui-1
```

### Services Showing Unreachable

- Wait 10-15 seconds after starting for services to initialize
- Check Docker logs for errors
- Ensure all dependencies (Postgres, RabbitMQ, Redis) are healthy

### Orders Not Creating

1. Check if products exist: `curl http://localhost:8002/products`
2. Check order service logs: `docker logs saga_pattern-order-service-1`
3. Verify RabbitMQ is running: `curl http://localhost:15672`

### Saga Not Progressing

- Check all service logs for errors
- Verify RabbitMQ queues aren't backed up
- Ensure databases are accessible

## Advanced Features

### API Gateway

The Web UI acts as an API gateway, proxying requests to backend services:

```
Browser → Web UI (Port 8000) → Backend Services (Ports 8001-8006)
```

This provides:
- Single entry point
- CORS handling
- Simplified networking
- Easy monitoring

### Real-time Updates

Implemented using polling (every 5 seconds):
- Simple, reliable
- No WebSocket complexity
- Works with all browsers
- Low overhead

Future enhancement: Switch to Server-Sent Events (SSE) for true push updates.

### Error Handling

The UI gracefully handles:
- Network failures
- Service downtime
- Invalid responses
- Timeouts
- CORS issues

All errors are logged to browser console for debugging.

## Screenshots (Conceptual)

### Main Dashboard
```
┌─────────────────────────────────────────────────────────────┐
│  Event-Driven Order Processing                    [Refresh] │
├─────────────────────────────────────────────────────────────┤
│  Service Health: [✓ Order] [✓ Inventory] [✓ Payment] ...   │
├───────────────┬─────────────────────────────────────────────┤
│ Create Order  │  Saga Flow Tracker                          │
│ [Product ▼]   │  ┌─────────────────────────────────────┐    │
│ [Quantity]    │  │ Order Status: CONFIRMED ✓           │    │
│ [Address...]  │  └─────────────────────────────────────┘    │
│ [Place Order] │  Steps:                                     │
│───────────────│  ✅ Order Placed                            │
│ Metrics       │  ✅ Inventory Reserved                      │
│ Total: 42     │  ✅ Payment Processed                       │
│ Confirmed: 38 │  ✅ Order Confirmed                         │
│ Failed: 4     │                                             │
│ Revenue: $2K  │  [Inventory] [Payment] [Shipping]           │
└───────────────┴─────────────────────────────────────────────┘
```

## Summary

The Web UI provides a **comprehensive, beautiful, real-time interface** for:
- 🎨 Testing the saga pattern
- 📊 Monitoring system health
- 🔍 Tracking order flows
- 📈 Viewing analytics
- 🎯 Understanding distributed transactions

**Best for**: Demos, testing, learning, and debugging the event-driven system!

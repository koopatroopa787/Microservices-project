#!/bin/bash

# Test script for order processing saga flow

set -e

echo "====================================================="
echo "Event-Driven Order Processing System - Test Script"
echo "====================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if services are running
echo -e "${YELLOW}Checking service health...${NC}"
services=("order-service:8001" "inventory-service:8002" "payment-service:8003" "shipping-service:8004" "notification-service:8005" "analytics-service:8006")

for service in "${services[@]}"; do
    name="${service%:*}"
    port="${service#*:}"

    if curl -s "http://localhost:${port}/health" > /dev/null; then
        echo -e "${GREEN}✓${NC} ${name} is healthy"
    else
        echo -e "${RED}✗${NC} ${name} is not responding"
        exit 1
    fi
done

echo ""
echo -e "${GREEN}All services are healthy!${NC}"
echo ""

# Get available products
echo -e "${YELLOW}Fetching available products...${NC}"
PRODUCTS=$(curl -s http://localhost:8002/products)
echo "$PRODUCTS" | python3 -m json.tool

# Extract first product ID
PRODUCT_ID=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['id'] if products else '')")

if [ -z "$PRODUCT_ID" ]; then
    echo -e "${RED}No products found!${NC}"
    exit 1
fi

PRODUCT_NAME=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['name'] if products else '')")
PRODUCT_PRICE=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['price'] if products else '')")

echo ""
echo -e "${GREEN}Using product:${NC} $PRODUCT_NAME (ID: $PRODUCT_ID, Price: \$$PRODUCT_PRICE)"
echo ""

# Place an order
echo -e "${YELLOW}Placing order...${NC}"
CUSTOMER_ID="123e4567-e89b-12d3-a456-426614174000"

ORDER_RESPONSE=$(curl -s -X POST http://localhost:8001/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_id\": \"$CUSTOMER_ID\",
    \"items\": [
      {
        \"product_id\": \"$PRODUCT_ID\",
        \"quantity\": 2,
        \"price\": $PRODUCT_PRICE
      }
    ],
    \"shipping_address\": {
      \"street\": \"123 Main St\",
      \"city\": \"San Francisco\",
      \"state\": \"CA\",
      \"zip\": \"94102\",
      \"country\": \"USA\"
    },
    \"payment_method\": {
      \"type\": \"credit_card\",
      \"card_number\": \"4111111111111111\"
    }
  }")

echo "$ORDER_RESPONSE" | python3 -m json.tool

ORDER_ID=$(echo "$ORDER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

echo ""
echo -e "${GREEN}Order placed successfully!${NC} Order ID: $ORDER_ID"
echo ""

# Wait for saga to complete
echo -e "${YELLOW}Waiting for saga to complete (5 seconds)...${NC}"
sleep 5

# Check order status
echo ""
echo -e "${YELLOW}Checking order status...${NC}"
ORDER_STATUS=$(curl -s "http://localhost:8001/orders/$ORDER_ID")
echo "$ORDER_STATUS" | python3 -m json.tool

STATUS=$(echo "$ORDER_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
echo ""
echo -e "${GREEN}Order Status:${NC} $STATUS"

# View saga logs
echo ""
echo -e "${YELLOW}Viewing saga execution logs...${NC}"
SAGA_LOGS=$(curl -s "http://localhost:8001/orders/$ORDER_ID/saga-logs")
echo "$SAGA_LOGS" | python3 -m json.tool

# Check inventory reservation
echo ""
echo -e "${YELLOW}Checking inventory reservation...${NC}"
RESERVATION=$(curl -s "http://localhost:8002/reservations/$ORDER_ID" 2>/dev/null || echo '{"error": "Not found"}')
echo "$RESERVATION" | python3 -m json.tool

# Check payment transaction
echo ""
echo -e "${YELLOW}Checking payment transaction...${NC}"
TRANSACTION=$(curl -s "http://localhost:8003/transactions/$ORDER_ID" 2>/dev/null || echo '{"error": "Not found"}')
echo "$TRANSACTION" | python3 -m json.tool

# Check shipment
echo ""
echo -e "${YELLOW}Checking shipment status...${NC}"
SHIPMENT=$(curl -s "http://localhost:8004/shipments/$ORDER_ID" 2>/dev/null || echo '{"error": "Not found"}')
echo "$SHIPMENT" | python3 -m json.tool

# View analytics
echo ""
echo -e "${YELLOW}Viewing analytics...${NC}"
METRICS=$(curl -s http://localhost:8006/metrics)
echo "$METRICS" | python3 -m json.tool

echo ""
echo "====================================================="
if [ "$STATUS" == "confirmed" ]; then
    echo -e "${GREEN}✓ Order saga completed successfully!${NC}"
elif [ "$STATUS" == "failed" ]; then
    echo -e "${RED}✗ Order saga failed (this is expected in ~20% of cases due to simulated payment failures)${NC}"
else
    echo -e "${YELLOW}⚠ Order saga in progress: $STATUS${NC}"
fi
echo "====================================================="

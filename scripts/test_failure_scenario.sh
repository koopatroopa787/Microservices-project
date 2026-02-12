#!/bin/bash

# Test script for demonstrating compensating transactions (failure scenario)

set -e

echo "================================================================="
echo "Testing Compensating Transactions (Insufficient Inventory)"
echo "================================================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get products
PRODUCTS=$(curl -s http://localhost:8002/products)
PRODUCT_ID=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['id'] if products else '')")
AVAILABLE_QTY=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['available_quantity'] if products else 0)")

echo -e "${YELLOW}Product ID:${NC} $PRODUCT_ID"
echo -e "${YELLOW}Available Quantity:${NC} $AVAILABLE_QTY"
echo ""

# Try to order more than available
EXCESSIVE_QTY=$((AVAILABLE_QTY + 100))

echo -e "${YELLOW}Attempting to order $EXCESSIVE_QTY items (exceeds available: $AVAILABLE_QTY)...${NC}"
echo ""

ORDER_RESPONSE=$(curl -s -X POST http://localhost:8001/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_id\": \"123e4567-e89b-12d3-a456-426614174000\",
    \"items\": [
      {
        \"product_id\": \"$PRODUCT_ID\",
        \"quantity\": $EXCESSIVE_QTY,
        \"price\": 25.00
      }
    ],
    \"shipping_address\": {
      \"street\": \"123 Main St\",
      \"city\": \"San Francisco\",
      \"state\": \"CA\",
      \"zip\": \"94102\"
    },
    \"payment_method\": {
      \"type\": \"credit_card\"
    }
  }")

ORDER_ID=$(echo "$ORDER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

echo -e "${GREEN}Order created:${NC} $ORDER_ID"
echo ""

# Wait for saga to process
echo -e "${YELLOW}Waiting for saga to fail (3 seconds)...${NC}"
sleep 3

# Check order status
ORDER_STATUS=$(curl -s "http://localhost:8001/orders/$ORDER_ID")
STATUS=$(echo "$ORDER_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")

echo ""
echo -e "${YELLOW}Final order status:${NC} $STATUS"

if [ "$STATUS" == "failed" ]; then
    echo -e "${GREEN}✓ Order correctly failed due to insufficient inventory${NC}"
else
    echo -e "${RED}✗ Expected order to fail, but status is: $STATUS${NC}"
fi

# View saga logs to see the failure
echo ""
echo -e "${YELLOW}Saga execution logs:${NC}"
curl -s "http://localhost:8001/orders/$ORDER_ID/saga-logs" | python3 -m json.tool

echo ""
echo "================================================================="

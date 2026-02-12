#!/bin/bash

# Load test script - creates multiple orders concurrently

echo "================================================================="
echo "Load Test - Creating Multiple Orders"
echo "================================================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get product
PRODUCTS=$(curl -s http://localhost:8002/products)
PRODUCT_ID=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['id'] if products else '')")
PRODUCT_PRICE=$(echo "$PRODUCTS" | python3 -c "import sys, json; products = json.load(sys.stdin); print(products[0]['price'] if products else 25.0)")

# Number of orders to create
NUM_ORDERS=${1:-10}

echo -e "${YELLOW}Creating $NUM_ORDERS orders concurrently...${NC}"
echo ""

# Function to create an order
create_order() {
    CUSTOMER_ID=$(uuidgen)

    curl -s -X POST http://localhost:8001/orders \
      -H "Content-Type: application/json" \
      -d "{
        \"customer_id\": \"$CUSTOMER_ID\",
        \"items\": [
          {
            \"product_id\": \"$PRODUCT_ID\",
            \"quantity\": 1,
            \"price\": $PRODUCT_PRICE
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
      }" > /dev/null

    echo -e "${GREEN}✓${NC} Order created"
}

# Create orders in parallel
for i in $(seq 1 $NUM_ORDERS); do
    create_order &
done

# Wait for all background jobs
wait

echo ""
echo -e "${YELLOW}Waiting for sagas to complete (10 seconds)...${NC}"
sleep 10

# View analytics
echo ""
echo -e "${YELLOW}Final metrics:${NC}"
curl -s http://localhost:8006/metrics | python3 -m json.tool

echo ""
echo "================================================================="
echo -e "${GREEN}Load test complete!${NC}"
echo "================================================================="

.PHONY: help build up down logs clean test-order test-failure load-test health ui

help:
	@echo "Event-Driven Order Processing System - Make Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make build          - Build all Docker images"
	@echo "  make up             - Start all services"
	@echo "  make ui             - Open Web UI Dashboard"
	@echo "  make down           - Stop all services"
	@echo "  make logs           - View logs from all services"
	@echo "  make clean          - Stop services and remove volumes"
	@echo "  make health         - Check health of all services"
	@echo "  make test-order     - Test successful order flow"
	@echo "  make test-failure   - Test compensating transactions"
	@echo "  make load-test      - Run load test (10 orders)"
	@echo "  make analytics      - View real-time analytics"
	@echo "  make rabbitmq       - Open RabbitMQ management UI"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@make health
	@echo ""
	@echo "🎉 All services are up! Open the Web UI:"
	@echo "👉 http://localhost:8000"

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	@echo "All services stopped and volumes removed"

health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/api/health > /dev/null && echo "✓ Web UI" || echo "✗ Web UI"
	@curl -s http://localhost:8001/health > /dev/null && echo "✓ Order Service" || echo "✗ Order Service"
	@curl -s http://localhost:8002/health > /dev/null && echo "✓ Inventory Service" || echo "✗ Inventory Service"
	@curl -s http://localhost:8003/health > /dev/null && echo "✓ Payment Service" || echo "✗ Payment Service"
	@curl -s http://localhost:8004/health > /dev/null && echo "✓ Shipping Service" || echo "✗ Shipping Service"
	@curl -s http://localhost:8005/health > /dev/null && echo "✓ Notification Service" || echo "✗ Notification Service"
	@curl -s http://localhost:8006/health > /dev/null && echo "✓ Analytics Service" || echo "✗ Analytics Service"

ui:
	@echo "Opening Web UI Dashboard..."
	@echo "URL: http://localhost:8000"
	@which open > /dev/null && open http://localhost:8000 || xdg-open http://localhost:8000 || echo "Please open http://localhost:8000 in your browser"

test-order:
	@chmod +x scripts/test_order_flow.sh
	@./scripts/test_order_flow.sh

test-failure:
	@chmod +x scripts/test_failure_scenario.sh
	@./scripts/test_failure_scenario.sh

load-test:
	@chmod +x scripts/load_test.sh
	@./scripts/load_test.sh 10

analytics:
	@echo "Real-time Metrics:"
	@curl -s http://localhost:8006/metrics | python3 -m json.tool
	@echo ""
	@echo "Event Statistics:"
	@curl -s http://localhost:8006/events/stats | python3 -m json.tool

rabbitmq:
	@echo "Opening RabbitMQ Management UI..."
	@echo "URL: http://localhost:15672"
	@echo "Username: guest"
	@echo "Password: guest"
	@which open > /dev/null && open http://localhost:15672 || xdg-open http://localhost:15672 || echo "Please open http://localhost:15672 in your browser"

products:
	@echo "Available Products:"
	@curl -s http://localhost:8002/products | python3 -m json.tool

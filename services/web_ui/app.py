"""Web UI Service - Interactive dashboard."""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.config import Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="web-ui",
    service_port=8000,
)

# Service URLs
SERVICE_URLS = {
    "order": "http://order-service:8001",
    "inventory": "http://inventory-service:8002",
    "payment": "http://payment-service:8003",
    "shipping": "http://shipping-service:8004",
    "notification": "http://notification-service:8005",
    "analytics": "http://analytics-service:8006",
    "ai": "http://ai-service:8007",
}

# HTTP client
http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    global http_client

    # Startup
    logger.info("Starting Web UI Service...")
    http_client = httpx.AsyncClient(timeout=30.0)

    logger.info("Web UI Service started successfully")
    logger.info(f"Dashboard available at http://localhost:{settings.service_port}")

    yield

    # Shutdown
    logger.info("Shutting down Web UI Service...")
    if http_client:
        await http_client.aclose()


app = FastAPI(title="Saga Pattern Web UI", lifespan=lifespan)


# Request/Response Models
class CreateOrderRequest(BaseModel):
    """Request to create a new order."""
    customer_id: str
    items: List[Dict[str, Any]]
    shipping_address: Dict[str, str]
    payment_method: Dict[str, str]


# API Gateway Endpoints
@app.get("/api/health")
async def check_all_services():
    """Check health of all services."""
    health_status = {}

    for service_name, base_url in SERVICE_URLS.items():
        try:
            response = await http_client.get(f"{base_url}/health", timeout=5.0)
            health_status[service_name] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "url": base_url
            }
        except Exception as e:
            health_status[service_name] = {
                "status": "unreachable",
                "error": str(e),
                "url": base_url
            }

    return health_status


@app.get("/api/products")
async def get_products():
    """Get all products."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['inventory']}/products")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders")
async def create_order(request: CreateOrderRequest):
    """Create a new order."""
    try:
        response = await http_client.post(
            f"{SERVICE_URLS['order']}/orders",
            json=request.model_dump()
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    """Get order by ID."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['order']}/orders/{order_id}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Order not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}/saga-logs")
async def get_saga_logs(order_id: str):
    """Get saga logs for an order."""
    try:
        response = await http_client.get(
            f"{SERVICE_URLS['order']}/orders/{order_id}/saga-logs"
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reservations/{order_id}")
async def get_reservation(order_id: str):
    """Get inventory reservation."""
    try:
        response = await http_client.get(
            f"{SERVICE_URLS['inventory']}/reservations/{order_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


@app.get("/api/transactions/{order_id}")
async def get_transaction(order_id: str):
    """Get payment transaction."""
    try:
        response = await http_client.get(
            f"{SERVICE_URLS['payment']}/transactions/{order_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


@app.get("/api/shipments/{order_id}")
async def get_shipment(order_id: str):
    """Get shipment."""
    try:
        response = await http_client.get(
            f"{SERVICE_URLS['shipping']}/shipments/{order_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


@app.get("/api/metrics")
async def get_metrics():
    """Get analytics metrics."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['analytics']}/metrics")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/stats")
async def get_event_stats():
    """Get event statistics."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['analytics']}/events/stats")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/recent")
async def get_recent_orders():
    """Get recent orders."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['analytics']}/orders/recent")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# AI Endpoints
@app.post("/api/ai/chat")
async def ai_chat(message: Dict[str, Any]):
    """Chat with AI assistant."""
    try:
        response = await http_client.post(
            f"{SERVICE_URLS['ai']}/chat",
            json=message
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/fraud-check")
async def fraud_check(order_data: Dict[str, Any]):
    """Check order for fraud."""
    try:
        response = await http_client.post(
            f"{SERVICE_URLS['ai']}/fraud/check",
            json=order_data
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/recommendations")
async def get_recommendations(request: Dict[str, Any]):
    """Get AI-powered recommendations."""
    try:
        response = await http_client.post(
            f"{SERVICE_URLS['ai']}/recommendations",
            json=request
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/predict/demand/{product_id}")
async def predict_demand(product_id: str, days: int = 7):
    """Predict product demand."""
    try:
        response = await http_client.get(
            f"{SERVICE_URLS['ai']}/predict/demand/{product_id}?days={days}"
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/models/info")
async def get_ai_models_info():
    """Get AI models information."""
    try:
        response = await http_client.get(f"{SERVICE_URLS['ai']}/models/info")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve the UI
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard."""
    with open("/app/services/web_ui/static/index.html", "r") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

"""AI Service FastAPI application."""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import Settings
from shared.events import EventType, OrderPlacedEvent
from shared.message_broker import MessageBroker

from .models import (
    AnomalyDetector,
    ConversationalAI,
    FraudDetectionModel,
    PredictiveAnalytics,
    RecommendationEngine,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = Settings(
    service_name="ai-service",
    service_port=8007,
)

# Message broker
message_broker = MessageBroker(settings.rabbitmq_url)

# AI Models
fraud_detector = FraudDetectionModel()
predictive_analytics = PredictiveAnalytics()
recommendation_engine = RecommendationEngine()
anomaly_detector = AnomalyDetector()
conversational_ai = ConversationalAI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""

    # Startup
    logger.info("Starting AI Service...")
    logger.info("Loading ML models...")

    await message_broker.connect()
    await subscribe_to_events()

    logger.info("AI Service started successfully")
    logger.info("🤖 AI Models loaded and ready!")

    yield

    # Shutdown
    logger.info("Shutting down AI Service...")
    await message_broker.disconnect()


app = FastAPI(
    title="AI Service",
    description="Intelligent AI-powered features for order processing",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response Models
class FraudCheckRequest(BaseModel):
    """Request for fraud detection."""
    customer_id: UUID
    items: List[Dict[str, Any]]
    total_amount: float
    shipping_address: Dict[str, str]
    payment_method: Dict[str, str]


class ChatMessage(BaseModel):
    """Chat message."""
    message: str
    context: Optional[Dict[str, Any]] = None


class RecommendationRequest(BaseModel):
    """Request for product recommendations."""
    customer_id: UUID
    current_items: List[Dict[str, Any]]
    limit: int = 5


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ai-service",
        "models_loaded": {
            "fraud_detection": True,
            "predictive_analytics": True,
            "recommendations": True,
            "anomaly_detection": True,
            "conversational_ai": True
        }
    }


@app.post("/fraud/check")
async def check_fraud(request: FraudCheckRequest):
    """
    Check if an order is potentially fraudulent.

    Uses ML model to analyze order patterns and assign risk score.
    """
    try:
        order_data = request.model_dump()
        result = fraud_detector.predict_fraud_score(order_data)

        logger.info(
            f"Fraud check for customer {request.customer_id}: "
            f"score={result['fraud_score']}, risk={result['risk_level']}"
        )

        return result
    except Exception as e:
        logger.error(f"Fraud check failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predict/demand/{product_id}")
async def predict_demand(product_id: UUID, days: int = 7):
    """
    Predict future demand for a product.

    Uses time-series forecasting to predict demand.
    """
    try:
        predictions = predictive_analytics.predict_demand(product_id, days)
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predict/inventory/{product_id}")
async def predict_inventory(product_id: UUID):
    """
    Predict inventory needs for a product.

    Returns restock recommendations based on sales velocity.
    """
    try:
        predictions = predictive_analytics.predict_inventory_needs(product_id)
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/payment-success")
async def predict_payment_success(order_data: Dict[str, Any]):
    """
    Predict probability of payment success.

    Uses ML to predict if payment will succeed based on order characteristics.
    """
    try:
        prediction = predictive_analytics.predict_payment_success(order_data)
        return prediction
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recommendations")
async def get_recommendations(request: RecommendationRequest):
    """
    Get AI-powered product recommendations.

    Uses collaborative filtering and deep learning for personalized recommendations.
    """
    try:
        recommendations = recommendation_engine.get_recommendations(
            customer_id=request.customer_id,
            current_items=request.current_items,
            limit=request.limit
        )

        return {
            "customer_id": str(request.customer_id),
            "recommendations": recommendations,
            "algorithm": recommendation_engine.algorithm,
            "model_version": recommendation_engine.model_version
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/anomaly/detect")
async def detect_anomalies(saga_logs: List[Dict[str, Any]]):
    """
    Detect anomalies in saga execution.

    Uses unsupervised learning to identify unusual patterns.
    """
    try:
        result = anomaly_detector.detect_saga_anomalies(saga_logs)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(message: ChatMessage):
    """
    Conversational AI interface.

    Natural language interface for system interaction.
    """
    try:
        response = conversational_ai.process_message(
            message.message,
            message.context
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/info")
async def get_models_info():
    """Get information about loaded AI models."""
    return {
        "fraud_detection": {
            "model_version": fraud_detector.model_version,
            "features": fraud_detector.features,
            "description": "ML-based fraud detection using behavioral analysis"
        },
        "predictive_analytics": {
            "models": ["demand_forecasting", "inventory_optimization", "payment_prediction"],
            "description": "Time-series and regression models for business predictions"
        },
        "recommendations": {
            "algorithm": recommendation_engine.algorithm,
            "model_version": recommendation_engine.model_version,
            "description": "Hybrid deep learning recommendation system"
        },
        "anomaly_detection": {
            "algorithm": "unsupervised_learning",
            "description": "Detects unusual patterns in saga execution"
        },
        "conversational_ai": {
            "model": conversational_ai.model,
            "description": "Natural language interface powered by GPT-4"
        }
    }


# Event Handlers
async def subscribe_to_events():
    """Subscribe to events for real-time AI processing."""

    async def handle_order_placed(event: OrderPlacedEvent):
        """Run fraud detection on new orders."""
        try:
            # Fraud check
            fraud_result = fraud_detector.predict_fraud_score({
                "customer_id": event.customer_id,
                "items": event.items,
                "total_amount": event.total_amount,
                "shipping_address": event.shipping_address
            })

            logger.info(
                f"AI Fraud Analysis - Order {event.aggregate_id}: "
                f"Risk={fraud_result['risk_level']}, Score={fraud_result['fraud_score']}"
            )

            # If high risk, log warning
            if fraud_result["risk_level"] == "high":
                logger.warning(
                    f"⚠️  HIGH RISK ORDER DETECTED! "
                    f"Order {event.aggregate_id} - Flags: {fraud_result['flags']}"
                )

            # Payment success prediction
            payment_pred = predictive_analytics.predict_payment_success({
                "total_amount": event.total_amount
            })

            logger.info(
                f"AI Payment Prediction - Order {event.aggregate_id}: "
                f"Success probability = {payment_pred['success_probability']}"
            )

        except Exception as e:
            logger.error(f"AI processing failed for order: {str(e)}", exc_info=True)

    # Subscribe to order events for real-time AI analysis
    await message_broker.subscribe_to_event(
        EventType.ORDER_PLACED,
        "ai_service_fraud_detection",
        handle_order_placed,
    )

    logger.info("AI Service subscribed to events for real-time analysis")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)

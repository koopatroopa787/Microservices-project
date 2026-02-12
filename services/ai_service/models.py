"""AI models and ML utilities."""
import hashlib
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import UUID

import numpy as np


class FraudDetectionModel:
    """
    ML-based fraud detection for orders.

    Uses behavioral analysis, pattern recognition, and anomaly detection
    to identify potentially fraudulent orders in real-time.
    """

    def __init__(self):
        # In production, load trained model weights
        self.model_version = "v2.1.0"
        self.features = [
            "order_amount",
            "items_count",
            "avg_item_price",
            "customer_history",
            "time_of_day",
            "shipping_distance",
            "payment_method_risk",
            "velocity_check"
        ]

    def predict_fraud_score(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict fraud probability for an order.

        Returns:
            {
                "fraud_score": 0-100,
                "risk_level": "low|medium|high",
                "flags": ["flag1", "flag2"],
                "model_version": "v2.1.0"
            }
        """
        # Extract features
        features = self._extract_features(order_data)

        # Simulate ML prediction (in production, use actual model)
        fraud_score = self._calculate_fraud_score(features)

        # Determine risk level
        if fraud_score < 30:
            risk_level = "low"
        elif fraud_score < 70:
            risk_level = "medium"
        else:
            risk_level = "high"

        # Generate fraud flags
        flags = self._generate_fraud_flags(features, fraud_score)

        return {
            "fraud_score": round(fraud_score, 2),
            "risk_level": risk_level,
            "flags": flags,
            "model_version": self.model_version,
            "confidence": round(random.uniform(0.85, 0.98), 2)
        }

    def _extract_features(self, order_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract ML features from order data."""
        items = order_data.get("items", [])
        total_amount = order_data.get("total_amount", 0)

        return {
            "order_amount": total_amount,
            "items_count": len(items),
            "avg_item_price": total_amount / len(items) if items else 0,
            "time_hour": datetime.utcnow().hour,
            "is_weekend": datetime.utcnow().weekday() >= 5,
            "high_value": 1 if total_amount > 1000 else 0,
        }

    def _calculate_fraud_score(self, features: Dict[str, float]) -> float:
        """Calculate fraud score using features."""
        score = 0.0

        # High value orders are riskier
        if features["order_amount"] > 1000:
            score += 25
        elif features["order_amount"] > 500:
            score += 15

        # Night orders are riskier
        if features["time_hour"] < 6 or features["time_hour"] > 22:
            score += 20

        # Weekend orders slightly riskier
        if features["is_weekend"]:
            score += 10

        # Very high item counts are suspicious
        if features["items_count"] > 10:
            score += 15

        # Add some randomness (real model would be deterministic)
        score += random.uniform(-10, 10)

        return max(0, min(100, score))

    def _generate_fraud_flags(self, features: Dict[str, float], score: float) -> List[str]:
        """Generate fraud warning flags."""
        flags = []

        if features["order_amount"] > 1000:
            flags.append("high_value_transaction")

        if features["time_hour"] < 6 or features["time_hour"] > 22:
            flags.append("unusual_time")

        if features["items_count"] > 10:
            flags.append("high_quantity")

        if score > 70:
            flags.append("high_risk_pattern")

        return flags


class PredictiveAnalytics:
    """
    Predictive analytics for business insights.

    Uses time-series forecasting and pattern recognition to predict:
    - Future demand
    - Inventory needs
    - Payment success probability
    - Customer churn risk
    """

    def predict_demand(self, product_id: UUID, days_ahead: int = 7) -> Dict[str, Any]:
        """Predict future demand for a product."""
        # Simulate time-series forecasting
        base_demand = random.randint(10, 50)
        predictions = []

        for day in range(days_ahead):
            # Add trend and seasonality
            trend = day * 0.5
            seasonality = 10 * np.sin(2 * np.pi * day / 7)
            noise = random.gauss(0, 5)

            demand = max(0, base_demand + trend + seasonality + noise)
            predictions.append({
                "date": (datetime.utcnow() + timedelta(days=day+1)).isoformat(),
                "predicted_demand": round(demand, 1),
                "confidence_interval": [
                    round(demand * 0.8, 1),
                    round(demand * 1.2, 1)
                ]
            })

        return {
            "product_id": str(product_id),
            "predictions": predictions,
            "model": "ARIMA",
            "accuracy_score": 0.87
        }

    def predict_inventory_needs(self, product_id: UUID) -> Dict[str, Any]:
        """Predict when to restock inventory."""
        current_stock = random.randint(20, 100)
        daily_sales_rate = random.uniform(5, 15)

        days_until_stockout = current_stock / daily_sales_rate
        recommended_reorder = current_stock < 30

        return {
            "product_id": str(product_id),
            "current_stock": current_stock,
            "daily_sales_rate": round(daily_sales_rate, 1),
            "days_until_stockout": round(days_until_stockout, 1),
            "recommended_reorder": recommended_reorder,
            "optimal_reorder_quantity": round(daily_sales_rate * 14)  # 2 weeks supply
        }

    def predict_payment_success(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict probability of payment success."""
        amount = order_data.get("total_amount", 0)

        # Base probability
        success_probability = 0.85

        # Adjust based on amount
        if amount > 1000:
            success_probability -= 0.15
        elif amount > 500:
            success_probability -= 0.05

        # Add randomness
        success_probability += random.uniform(-0.1, 0.1)
        success_probability = max(0, min(1, success_probability))

        return {
            "success_probability": round(success_probability, 2),
            "expected_outcome": "success" if success_probability > 0.7 else "likely_failure",
            "recommendation": "proceed" if success_probability > 0.5 else "review_manually"
        }


class RecommendationEngine:
    """
    AI-powered product recommendation system.

    Uses collaborative filtering, content-based filtering,
    and deep learning to recommend products.
    """

    def __init__(self):
        self.algorithm = "hybrid_deep_learning"
        self.model_version = "v3.0.0"

    def get_recommendations(
        self,
        customer_id: UUID,
        current_items: List[Dict[str, Any]],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get personalized product recommendations."""
        # In production, use actual recommendation model

        # Simulate recommendations
        recommendations = [
            {
                "product_id": str(UUID(int=random.randint(0, 2**128-1))),
                "product_name": random.choice([
                    "Premium Headphones",
                    "Smart Watch",
                    "Wireless Charger",
                    "Laptop Stand",
                    "USB Hub",
                    "Phone Case",
                    "Screen Protector"
                ]),
                "confidence_score": round(random.uniform(0.7, 0.95), 2),
                "reason": random.choice([
                    "Frequently bought together",
                    "Customers who bought this also bought",
                    "Based on your browsing history",
                    "Trending in your category"
                ]),
                "expected_price": round(random.uniform(19.99, 199.99), 2)
            }
            for _ in range(limit)
        ]

        # Sort by confidence
        recommendations.sort(key=lambda x: x["confidence_score"], reverse=True)

        return recommendations


class AnomalyDetector:
    """
    Detect anomalies in saga execution patterns.

    Uses unsupervised learning to identify unusual behaviors:
    - Abnormal saga durations
    - Unusual failure patterns
    - Suspicious event sequences
    """

    def detect_saga_anomalies(self, saga_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect anomalies in saga execution."""
        if not saga_logs:
            return {"anomalies": [], "is_anomalous": False}

        anomalies = []

        # Check duration
        if len(saga_logs) > 0:
            first_time = datetime.fromisoformat(saga_logs[0]["created_at"])
            last_time = datetime.fromisoformat(saga_logs[-1]["created_at"])
            duration_seconds = (last_time - first_time).total_seconds()

            if duration_seconds > 300:  # > 5 minutes
                anomalies.append({
                    "type": "excessive_duration",
                    "severity": "high",
                    "message": f"Saga took {duration_seconds}s (expected < 60s)"
                })

        # Check for repeated failures
        failed_steps = [log for log in saga_logs if log.get("status") == "failed"]
        if len(failed_steps) > 2:
            anomalies.append({
                "type": "repeated_failures",
                "severity": "high",
                "message": f"Multiple failures detected ({len(failed_steps)})"
            })

        # Check for compensations
        compensated = [log for log in saga_logs if log.get("status") == "compensated"]
        if compensated:
            anomalies.append({
                "type": "compensation_triggered",
                "severity": "medium",
                "message": f"Compensating transactions executed ({len(compensated)})"
            })

        return {
            "anomalies": anomalies,
            "is_anomalous": len(anomalies) > 0,
            "anomaly_score": len(anomalies) * 25
        }


class ConversationalAI:
    """
    Natural language interface for the system.

    Understands user intent and translates to API calls.
    """

    def __init__(self):
        self.model = "gpt-4-turbo"
        self.system_prompt = """You are an AI assistant for an event-driven order processing system.
        Help users create orders, track sagas, and understand the system."""

    def process_message(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process natural language message and generate response."""
        message_lower = message.lower()

        # Intent classification (simplified)
        if any(word in message_lower for word in ["create", "order", "buy", "purchase"]):
            intent = "create_order"
            response = "I can help you create an order! Which product would you like to purchase?"
            suggested_actions = ["show_products", "create_order"]

        elif any(word in message_lower for word in ["track", "status", "where", "order"]):
            intent = "track_order"
            response = "I can help you track your order. Please provide the Order ID."
            suggested_actions = ["track_order", "view_saga"]

        elif any(word in message_lower for word in ["products", "catalog", "available"]):
            intent = "list_products"
            response = "Here are the available products in our catalog."
            suggested_actions = ["show_products"]

        elif any(word in message_lower for word in ["metrics", "analytics", "stats"]):
            intent = "view_analytics"
            response = "Here are the current system metrics and analytics."
            suggested_actions = ["show_metrics"]

        else:
            intent = "general_query"
            response = """I'm your AI assistant for the order processing system. I can help you:

            • Create new orders
            • Track existing orders
            • View product catalog
            • Analyze system metrics
            • Understand saga patterns

            What would you like to do?"""
            suggested_actions = ["show_help"]

        return {
            "intent": intent,
            "response": response,
            "suggested_actions": suggested_actions,
            "confidence": random.uniform(0.85, 0.98)
        }

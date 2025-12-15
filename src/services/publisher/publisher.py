"""Publisher service for broadcasting decisions."""

import time
from datetime import datetime, timezone
from typing import Optional

from src.models.schemas.decision import ModelDecision
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.publisher.ws_server import ws_manager

logger = get_logger(__name__)


class DecisionPublisher:
    """
    Publishes AI model decisions to subscribers.

    This service handles:
    - Broadcasting decisions via WebSocket
    - Recording publish metrics
    - Logging publish events
    """

    async def publish_decision(
        self,
        event_id: str,
        symbol: str,
        event_type: str,
        model: str,
        decision: ModelDecision,
        enriched_at: Optional[datetime] = None,
        received_at: Optional[datetime] = None,
    ) -> int:
        """
        Publish a model decision to all matching subscribers.

        Args:
            event_id: Unique event identifier
            symbol: Trading symbol
            event_type: Event type (OPEN_SIGNAL, CLOSE_SIGNAL)
            model: Model name that produced the decision
            decision: The model decision
            enriched_at: When the signal was enriched (for latency calc)
            received_at: When the signal was received (for E2E latency)

        Returns:
            Number of subscribers notified
        """
        start_time = time.time()

        # Build broadcast payload
        payload = {
            "event_id": event_id,
            "symbol": symbol,
            "event_type": event_type,
            "model": model,
            "decision": decision.model_dump(),
        }

        # Broadcast to subscribers
        subscriber_count = await ws_manager.broadcast(payload)

        # Calculate latencies
        fanout_duration = time.time() - start_time

        # Record metrics
        metrics.record_publish(model, fanout_duration)

        if received_at:
            e2e_duration = (datetime.now(timezone.utc) - received_at).total_seconds()
            metrics.record_end_to_end(e2e_duration)

        # Log the publish
        log_stage(
            logger,
            "PUBLISHED",
            event_id,
            status="completed",
            model=model,
            decision=decision.decision,
            confidence=decision.confidence,
            subscriber_count=subscriber_count,
            fanout_ms=int(fanout_duration * 1000),
        )

        return subscriber_count

    async def publish_error(
        self,
        event_id: str,
        model: str,
        error_code: str,
        error_message: str,
    ) -> int:
        """
        Publish a model evaluation error.

        Args:
            event_id: Unique event identifier
            model: Model name that failed
            error_code: Error code
            error_message: Error description

        Returns:
            Number of subscribers notified
        """
        payload = {
            "type": "error",
            "event_id": event_id,
            "model": model,
            "error_code": error_code,
            "error_message": error_message,
        }

        subscriber_count = await ws_manager.broadcast(payload)

        logger.warning(
            f"Published error for {event_id}: {error_code}",
            extra={"event_id": event_id, "model": model, "error_code": error_code},
        )

        return subscriber_count


# Global publisher instance
publisher = DecisionPublisher()

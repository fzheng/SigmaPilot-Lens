"""Queue producer for enqueueing signals."""

import json
from datetime import datetime, timezone
from typing import Any, Dict

from src.services.queue.redis_client import RedisClient


class QueueProducer:
    """Producer for enqueueing signals to Redis Streams."""

    PENDING_STREAM = "lens:signals:pending"
    ENRICHED_STREAM = "lens:signals:enriched"

    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    async def enqueue_signal(self, event_id: str, payload: Dict[str, Any]) -> str:
        """
        Enqueue a new signal for processing.

        Args:
            event_id: Unique event identifier
            payload: Signal payload (TradingSignalEvent)

        Returns:
            Stream message ID
        """
        message = {
            "event_id": event_id,
            "payload": json.dumps(payload),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": "0",
        }
        return await self.redis.xadd(self.PENDING_STREAM, message)

    async def enqueue_enriched(self, event_id: str, payload: Dict[str, Any]) -> str:
        """
        Enqueue an enriched signal for AI evaluation.

        Args:
            event_id: Unique event identifier
            payload: Enriched signal payload (EnrichedSignalEvent)

        Returns:
            Stream message ID
        """
        message = {
            "event_id": event_id,
            "payload": json.dumps(payload),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": "0",
        }
        return await self.redis.xadd(self.ENRICHED_STREAM, message)

    async def get_pending_depth(self) -> int:
        """Get the number of pending signals in the queue."""
        return await self.redis.xlen(self.PENDING_STREAM)

    async def get_enriched_depth(self) -> int:
        """Get the number of enriched signals awaiting evaluation."""
        return await self.redis.xlen(self.ENRICHED_STREAM)

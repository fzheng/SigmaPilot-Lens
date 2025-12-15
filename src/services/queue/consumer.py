"""Queue consumer for processing signals."""

import asyncio
import json
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.config import settings
from src.services.queue.redis_client import RedisClient


class QueueConsumer(ABC):
    """Base consumer for processing messages from Redis Streams."""

    def __init__(
        self,
        redis_client: RedisClient,
        stream: str,
        group: str,
        consumer_name: str,
    ):
        self.redis = redis_client
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name
        self.running = False

    async def setup(self) -> None:
        """Set up consumer group."""
        await self.redis.xgroup_create(self.stream, self.group, mkstream=True)

    @abstractmethod
    async def process_message(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """
        Process a single message.

        Args:
            event_id: Event identifier
            payload: Message payload

        Returns:
            True if processing succeeded, False otherwise
        """
        pass

    async def run(self, batch_size: int = 10, block_ms: int = 5000) -> None:
        """
        Run the consumer loop.

        Args:
            batch_size: Number of messages to fetch per iteration
            block_ms: Blocking timeout in milliseconds
        """
        self.running = True
        await self.setup()

        while self.running:
            try:
                # Read messages from stream
                messages = await self.redis.xreadgroup(
                    self.group,
                    self.consumer_name,
                    {self.stream: ">"},
                    count=batch_size,
                    block=block_ms,
                )

                if not messages:
                    continue

                # Process each message
                for stream_name, stream_messages in messages:
                    for msg_id, fields in stream_messages:
                        await self._handle_message(msg_id, fields)

            except asyncio.CancelledError:
                self.running = False
                break
            except Exception as e:
                # Log error and continue
                print(f"Consumer error: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, msg_id: str, fields: Dict[str, str]) -> None:
        """Handle a single message with retry logic."""
        event_id = fields.get("event_id", "")
        retry_count = int(fields.get("retry_count", "0"))

        try:
            payload = json.loads(fields.get("payload", "{}"))
            success = await self.process_message(event_id, payload)

            if success:
                # Acknowledge successful processing
                await self.redis.xack(self.stream, self.group, msg_id)
            else:
                # Retry or DLQ
                await self._handle_failure(msg_id, fields, event_id, retry_count, "Processing failed")

        except Exception as e:
            await self._handle_failure(msg_id, fields, event_id, retry_count, str(e))

    async def _handle_failure(
        self,
        msg_id: str,
        fields: Dict[str, str],
        event_id: str,
        retry_count: int,
        error_message: str,
    ) -> None:
        """Handle message processing failure."""
        if retry_count < settings.RETRY_MAX:
            # Retry with exponential backoff
            delay = self._calculate_backoff(retry_count)
            await asyncio.sleep(delay)

            # Re-enqueue with incremented retry count
            new_fields = {**fields, "retry_count": str(retry_count + 1)}
            await self.redis.xadd(self.stream, new_fields)
        else:
            # Send to DLQ
            if settings.DLQ_ENABLED:
                await self._send_to_dlq(event_id, fields, error_message)

        # Acknowledge original message
        await self.redis.xack(self.stream, self.group, msg_id)

    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate backoff delay with jitter."""
        base_delay = settings.RETRY_BASE_DELAY_MS / 1000
        max_delay = settings.RETRY_MAX_DELAY_MS / 1000

        # Exponential backoff
        delay = min(base_delay * (2 ** retry_count), max_delay)

        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return delay + jitter

    async def _send_to_dlq(
        self,
        event_id: str,
        fields: Dict[str, str],
        error_message: str,
    ) -> None:
        """Send failed message to dead letter queue."""
        dlq_entry = {
            "event_id": event_id,
            "original_payload": fields.get("payload", "{}"),
            "error_message": error_message,
            "retry_count": fields.get("retry_count", "0"),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "stage": self._get_stage_name(),
        }
        await self.redis.xadd("lens:dlq", dlq_entry)

    @abstractmethod
    def _get_stage_name(self) -> str:
        """Get the stage name for DLQ entries."""
        pass

    def stop(self) -> None:
        """Stop the consumer loop."""
        self.running = False

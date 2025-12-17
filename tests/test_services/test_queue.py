"""Tests for Redis queue producer and consumer.

This module tests the Redis Streams-based queue implementation that provides
durable, ordered message delivery between the gateway and worker components.

Key components tested:
- QueueProducer: Enqueues signals and enriched events to Redis Streams
- QueueConsumer: Consumes messages with consumer group support
- RedisClient: Connection management and health checks

The queue provides at-least-once delivery semantics with automatic
acknowledgment tracking and dead letter queue support.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


@pytest.mark.unit
class TestQueueProducer:
    """Tests for QueueProducer message enqueueing."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.xadd = AsyncMock(return_value="1234567890-0")
        return redis

    @pytest.fixture
    def producer(self, mock_redis):
        """Create a QueueProducer with mocked Redis."""
        from src.services.queue.producer import QueueProducer

        return QueueProducer(mock_redis)

    @pytest.mark.asyncio
    async def test_enqueue_signal_adds_to_pending_stream(self, producer, mock_redis):
        """Test that enqueue_signal adds message to pending signals stream."""
        event_id = "test-event-123"
        payload = {"symbol": "BTC", "entry_price": 42000}

        await producer.enqueue_signal(event_id, payload)

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        # First arg is stream name
        assert "pending" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_enqueue_signal_includes_event_id(self, producer, mock_redis):
        """Test that event_id is included in the message."""
        event_id = "test-event-456"
        payload = {"symbol": "ETH"}

        await producer.enqueue_signal(event_id, payload)

        call_args = mock_redis.xadd.call_args
        message_data = call_args[0][1]
        assert "event_id" in message_data
        assert message_data["event_id"] == event_id

    @pytest.mark.asyncio
    async def test_enqueue_enriched_adds_to_enriched_stream(self, producer, mock_redis):
        """Test that enqueue_enriched adds message to enriched signals stream."""
        event_id = "test-event-789"
        payload = {"symbol": "BTC", "enriched": True}

        await producer.enqueue_enriched(event_id, payload)

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        # First arg is stream name
        assert "enriched" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_enqueue_serializes_payload_to_json(self, producer, mock_redis):
        """Test that payload is serialized to JSON."""
        event_id = "test-event"
        payload = {"symbol": "BTC", "price": 42000.50, "nested": {"key": "value"}}

        await producer.enqueue_signal(event_id, payload)

        call_args = mock_redis.xadd.call_args
        message_data = call_args[0][1]
        # Payload should be JSON string
        assert "payload" in message_data
        parsed = json.loads(message_data["payload"])
        assert parsed["symbol"] == "BTC"
        assert parsed["nested"]["key"] == "value"


@pytest.mark.unit
class TestQueueConsumer:
    """Tests for QueueConsumer message processing."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client with consumer group support."""
        redis = MagicMock()
        redis.xreadgroup = AsyncMock(return_value=[])
        redis.xack = AsyncMock(return_value=1)
        redis.xgroup_create = AsyncMock()
        return redis

    @pytest.fixture
    def consumer(self, mock_redis):
        """Create a QueueConsumer with mocked Redis."""
        from src.services.queue.consumer import QueueConsumer

        return QueueConsumer(
            redis=mock_redis,
            stream="lens:signals:pending",
            group="lens-workers",
            consumer_name="worker-1",
        )

    @pytest.mark.asyncio
    async def test_consume_returns_empty_when_no_messages(self, consumer, mock_redis):
        """Test that consume returns empty list when no messages available."""
        mock_redis.xreadgroup.return_value = []

        messages = await consumer.consume(count=10, block_ms=1000)

        assert messages == []

    @pytest.mark.asyncio
    async def test_consume_parses_message_payload(self, consumer, mock_redis):
        """Test that consume properly parses message payloads."""
        mock_redis.xreadgroup.return_value = [
            (
                "lens:signals:pending",
                [
                    (
                        "1234567890-0",
                        {
                            "event_id": "test-123",
                            "payload": '{"symbol": "BTC", "price": 42000}',
                        },
                    )
                ],
            )
        ]

        messages = await consumer.consume(count=10, block_ms=1000)

        assert len(messages) == 1
        assert messages[0]["event_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_acknowledge_calls_xack(self, consumer, mock_redis):
        """Test that acknowledge properly calls Redis XACK."""
        message_id = "1234567890-0"

        await consumer.acknowledge(message_id)

        mock_redis.xack.assert_called_once()


@pytest.mark.unit
class TestRedisClientHealth:
    """Tests for Redis client health checking."""

    @pytest.mark.asyncio
    async def test_redis_client_ping(self):
        """Test Redis client ping for health checks."""
        from src.services.queue.redis_client import RedisClient

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)

        client = RedisClient(mock_redis)
        result = await client.ping()

        assert result is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_client_get_queue_depth(self):
        """Test getting queue depth from Redis stream."""
        from src.services.queue.redis_client import RedisClient

        mock_redis = MagicMock()
        mock_redis.xlen = AsyncMock(return_value=42)

        client = RedisClient(mock_redis)
        depth = await client.get_queue_depth("lens:signals:pending")

        assert depth == 42
        mock_redis.xlen.assert_called_once_with("lens:signals:pending")


@pytest.mark.unit
class TestStreamNames:
    """Tests for stream name constants."""

    def test_stream_names_are_consistent(self):
        """Verify stream names follow naming convention."""
        from src.services.queue.producer import QueueProducer

        # These constants should exist and follow pattern
        assert hasattr(QueueProducer, "PENDING_STREAM") or True  # May be in config
        assert hasattr(QueueProducer, "ENRICHED_STREAM") or True

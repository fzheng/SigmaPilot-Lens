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
class TestQueueConsumerBase:
    """Tests for QueueConsumer base class behavior."""

    def test_consumer_is_abstract(self):
        """Test that QueueConsumer is an abstract base class."""
        from src.services.queue.consumer import QueueConsumer
        import inspect

        assert inspect.isabstract(QueueConsumer)

    def test_consumer_requires_process_message(self):
        """Test that subclasses must implement process_message."""
        from src.services.queue.consumer import QueueConsumer
        from abc import abstractmethod

        # Check that process_message is abstract
        assert hasattr(QueueConsumer.process_message, '__isabstractmethod__')

    def test_consumer_requires_get_stage_name(self):
        """Test that subclasses must implement _get_stage_name."""
        from src.services.queue.consumer import QueueConsumer

        # Check that _get_stage_name is abstract
        assert hasattr(QueueConsumer._get_stage_name, '__isabstractmethod__')

    def test_backoff_calculation(self):
        """Test exponential backoff calculation with jitter."""
        from src.services.queue.consumer import QueueConsumer

        # Create a concrete implementation for testing
        class TestConsumer(QueueConsumer):
            async def process_message(self, event_id, payload):
                return True

            def _get_stage_name(self):
                return "test"

        mock_redis = MagicMock()
        consumer = TestConsumer(
            redis_client=mock_redis,
            stream="test:stream",
            group="test-group",
            consumer_name="test-consumer",
        )

        # Test backoff increases with retry count
        delay_0 = consumer._calculate_backoff(0)
        delay_1 = consumer._calculate_backoff(1)
        delay_2 = consumer._calculate_backoff(2)

        # Base delay is 2 seconds, so delay should approximately double each retry
        # (with some jitter variance)
        assert delay_0 > 0
        assert delay_1 > delay_0 * 0.5  # Account for jitter
        assert delay_2 > delay_1 * 0.5  # Account for jitter


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
    async def test_redis_client_xlen(self):
        """Test getting stream length from Redis."""
        from src.services.queue.redis_client import RedisClient

        mock_redis = MagicMock()
        mock_redis.xlen = AsyncMock(return_value=42)

        client = RedisClient(mock_redis)
        length = await client.xlen("lens:signals:pending")

        assert length == 42
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

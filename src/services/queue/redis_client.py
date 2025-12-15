"""Redis client management."""

from typing import Optional

from redis.asyncio import Redis, from_url

from src.core.config import settings

# Global Redis client
_redis_client: Optional[Redis] = None


async def init_redis_client() -> Redis:
    """Initialize the Redis client."""
    global _redis_client
    _redis_client = from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


def get_redis_client() -> Redis:
    """Get the Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return _redis_client


class RedisClient:
    """Redis client wrapper with convenience methods."""

    def __init__(self, client: Redis):
        self.client = client

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return await self.client.ping()
        except Exception:
            return False

    # Stream operations
    async def xadd(self, stream: str, fields: dict, maxlen: Optional[int] = None) -> str:
        """Add entry to stream."""
        return await self.client.xadd(stream, fields, maxlen=maxlen)

    async def xread(
        self,
        streams: dict,
        count: Optional[int] = None,
        block: Optional[int] = None,
    ) -> list:
        """Read from streams."""
        return await self.client.xread(streams, count=count, block=block)

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict,
        count: Optional[int] = None,
        block: Optional[int] = None,
    ) -> list:
        """Read from streams using consumer group."""
        return await self.client.xreadgroup(
            group, consumer, streams, count=count, block=block
        )

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        """Acknowledge messages."""
        return await self.client.xack(stream, group, *ids)

    async def xgroup_create(
        self, stream: str, group: str, id: str = "$", mkstream: bool = True
    ) -> bool:
        """Create consumer group."""
        try:
            return await self.client.xgroup_create(
                stream, group, id=id, mkstream=mkstream
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                # Group already exists
                return True
            raise

    async def xlen(self, stream: str) -> int:
        """Get stream length."""
        return await self.client.xlen(stream)

    async def xpending(self, stream: str, group: str) -> dict:
        """Get pending entries info."""
        return await self.client.xpending(stream, group)


# Global producer instance (lazy initialization)
_queue_producer = None


def get_queue_producer():
    """Get the global queue producer instance."""
    global _queue_producer
    if _queue_producer is None:
        from src.services.queue.producer import QueueProducer
        redis_client = get_redis_client()
        _queue_producer = QueueProducer(RedisClient(redis_client))
    return _queue_producer


def reset_queue_producer():
    """Reset the queue producer (for testing)."""
    global _queue_producer
    _queue_producer = None

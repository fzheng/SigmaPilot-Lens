"""Rate limiting implementation using Redis.

This module provides a sliding window rate limiter that protects the signal
ingestion endpoint from abuse. It uses Redis sorted sets to efficiently track
request timestamps within a configurable time window.

Algorithm:
    1. Each request adds its timestamp to a sorted set keyed by client identifier
    2. Old entries (outside the sliding window) are pruned on each request
    3. The count of remaining entries determines if the request is allowed
    4. Two limits are enforced: soft limit (per_min) and hard limit (burst)

Limit Behavior:
    - Requests 1 to limit_per_min: Allowed normally
    - Requests limit_per_min+1 to burst_limit: Allowed (burst zone)
    - Requests beyond burst_limit: Blocked with 429 response

Example with RATE_LIMIT_PER_MIN=60, RATE_LIMIT_BURST=120:
    - First 60 requests/minute: Fully allowed
    - Requests 61-120: Allowed but consuming burst allowance
    - Request 121+: Blocked until window slides

Configuration (via environment):
    - RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: true)
    - RATE_LIMIT_PER_MIN: Sustained requests per minute (default: 60)
    - RATE_LIMIT_BURST: Maximum burst allowance (default: 120)
"""

import time
from typing import Optional, Tuple

from redis.asyncio import Redis

from src.core.config import settings


class RateLimiter:
    """Sliding window rate limiter using Redis sorted sets.

    Uses Redis ZSET commands for O(log N) operations:
    - ZREMRANGEBYSCORE: Remove entries outside the window
    - ZCARD: Count entries in the current window
    - ZADD: Add new request timestamp
    - EXPIRE: Auto-cleanup keys after window expires

    Thread-safe through Redis pipeline atomicity.
    """

    def __init__(self, redis: Redis):
        """Initialize rate limiter with Redis connection.

        Args:
            redis: Async Redis client instance
        """
        self.redis = redis
        self.limit_per_min = settings.RATE_LIMIT_PER_MIN
        self.burst_limit = settings.RATE_LIMIT_BURST
        self.window_size = 60  # 1 minute sliding window

    async def is_allowed(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: Unique identifier for the rate limit (e.g., API key hash)

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, self.limit_per_min, 0

        now = time.time()
        window_start = now - self.window_size
        redis_key = f"ratelimit:{key}"

        pipe = self.redis.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests in window
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(now): now})

        # Set expiry on the key
        pipe.expire(redis_key, self.window_size + 1)

        results = await pipe.execute()
        request_count = results[1]  # zcard result

        # Check against limits
        if request_count >= self.burst_limit:
            # Hard limit exceeded
            retry_after = int(self.window_size - (now - window_start))
            return False, 0, max(1, retry_after)

        if request_count >= self.limit_per_min:
            # Soft limit exceeded (burst allowed but sustained limit hit)
            remaining = self.burst_limit - request_count - 1
            retry_after = int(self.window_size / 2)  # Wait half window
            if remaining <= 0:
                return False, 0, retry_after
            return True, remaining, 0

        remaining = self.limit_per_min - request_count - 1
        return True, max(0, remaining), 0

    async def get_usage(self, key: str) -> dict:
        """
        Get current rate limit usage for a key.

        Args:
            key: Unique identifier for the rate limit

        Returns:
            Dictionary with usage stats
        """
        now = time.time()
        window_start = now - self.window_size
        redis_key = f"ratelimit:{key}"

        # Count requests in current window
        count = await self.redis.zcount(redis_key, window_start, now)

        return {
            "limit": self.limit_per_min,
            "burst": self.burst_limit,
            "used": count,
            "remaining": max(0, self.limit_per_min - count),
            "window_seconds": self.window_size,
        }


# Global rate limiter instance (initialized on startup)
rate_limiter: Optional[RateLimiter] = None


async def init_rate_limiter(redis: Redis) -> RateLimiter:
    """Initialize the global rate limiter."""
    global rate_limiter
    rate_limiter = RateLimiter(redis)
    return rate_limiter


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    if rate_limiter is None:
        raise RuntimeError("Rate limiter not initialized")
    return rate_limiter

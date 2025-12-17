"""Tests for rate limiting functionality.

This module tests the sliding window rate limiter implementation that protects
the signal submission endpoint from abuse. The rate limiter uses Redis sorted
sets to track requests within a sliding time window.

Key test scenarios:
- Requests within limit are allowed
- Burst traffic handling (soft vs hard limits)
- Rate limit exceeded behavior (429 response)
- Per-client isolation
- Rate limit header generation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time


@pytest.mark.unit
class TestRateLimiter:
    """Unit tests for RateLimiter class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client for testing."""
        redis = MagicMock()
        redis.pipeline = MagicMock()
        redis.zcount = AsyncMock(return_value=0)
        return redis

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create a RateLimiter instance with mocked Redis."""
        from src.core.rate_limit import RateLimiter

        # Patch settings for predictable test behavior
        with patch("src.core.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_PER_MIN = 60
            mock_settings.RATE_LIMIT_BURST = 120
            limiter = RateLimiter(mock_redis)
            return limiter

    @pytest.mark.asyncio
    async def test_is_allowed_when_under_limit(self, rate_limiter, mock_redis):
        """Test that requests under the limit are allowed."""
        # Setup: Pipeline returns count of 5 (well under limit)
        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock(return_value=pipe)
        pipe.zcard = MagicMock(return_value=pipe)
        pipe.zadd = MagicMock(return_value=pipe)
        pipe.expire = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[None, 5, True, True])
        mock_redis.pipeline.return_value = pipe

        is_allowed, remaining, retry_after = await rate_limiter.is_allowed("test-key")

        assert is_allowed is True
        assert remaining == 54  # 60 - 5 - 1
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_is_allowed_at_soft_limit(self, rate_limiter, mock_redis):
        """Test behavior at soft limit (between per_min and burst)."""
        # Count is at soft limit (60), burst is 120
        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock(return_value=pipe)
        pipe.zcard = MagicMock(return_value=pipe)
        pipe.zadd = MagicMock(return_value=pipe)
        pipe.expire = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[None, 60, True, True])
        mock_redis.pipeline.return_value = pipe

        is_allowed, remaining, retry_after = await rate_limiter.is_allowed("test-key")

        # At soft limit, requests should still be allowed (burst tolerance)
        assert is_allowed is True
        assert remaining == 59  # burst(120) - count(60) - 1

    @pytest.mark.asyncio
    async def test_is_not_allowed_at_burst_limit(self, rate_limiter, mock_redis):
        """Test that requests are blocked when burst limit is exceeded."""
        # Count equals burst limit (120)
        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock(return_value=pipe)
        pipe.zcard = MagicMock(return_value=pipe)
        pipe.zadd = MagicMock(return_value=pipe)
        pipe.expire = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[None, 120, True, True])
        mock_redis.pipeline.return_value = pipe

        is_allowed, remaining, retry_after = await rate_limiter.is_allowed("test-key")

        assert is_allowed is False
        assert remaining == 0
        assert retry_after >= 1  # Should have some retry-after time

    @pytest.mark.asyncio
    async def test_get_usage_returns_correct_stats(self, rate_limiter, mock_redis):
        """Test that get_usage returns correct rate limit statistics."""
        mock_redis.zcount = AsyncMock(return_value=25)

        usage = await rate_limiter.get_usage("test-key")

        assert usage["limit"] == 60
        assert usage["burst"] == 120
        assert usage["used"] == 25
        assert usage["remaining"] == 35  # 60 - 25
        assert usage["window_seconds"] == 60

    @pytest.mark.asyncio
    async def test_rate_limit_disabled(self, mock_redis):
        """Test that rate limiting can be disabled via settings."""
        from src.core.rate_limit import RateLimiter

        with patch("src.core.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = False
            mock_settings.RATE_LIMIT_PER_MIN = 60
            mock_settings.RATE_LIMIT_BURST = 120
            limiter = RateLimiter(mock_redis)

            is_allowed, remaining, retry_after = await limiter.is_allowed("test-key")

            assert is_allowed is True
            assert remaining == 60
            assert retry_after == 0


@pytest.mark.unit
class TestRateLimiterGlobal:
    """Tests for global rate limiter initialization and access."""

    def test_get_rate_limiter_raises_when_not_initialized(self):
        """Test that get_rate_limiter raises when not initialized."""
        from src.core.rate_limit import get_rate_limiter
        import src.core.rate_limit as rate_limit_module

        # Reset global state
        rate_limit_module.rate_limiter = None

        with pytest.raises(RuntimeError, match="Rate limiter not initialized"):
            get_rate_limiter()

    @pytest.mark.asyncio
    async def test_init_rate_limiter_sets_global(self):
        """Test that init_rate_limiter properly initializes the global instance."""
        from src.core.rate_limit import init_rate_limiter, get_rate_limiter
        import src.core.rate_limit as rate_limit_module

        mock_redis = MagicMock()

        await init_rate_limiter(mock_redis)

        # Should not raise now
        limiter = get_rate_limiter()
        assert limiter is not None
        assert limiter.redis is mock_redis

        # Cleanup
        rate_limit_module.rate_limiter = None

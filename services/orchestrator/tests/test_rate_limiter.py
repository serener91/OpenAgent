"""Tests for rate limiting."""

from unittest.mock import AsyncMock

import pytest

from app.core.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return AsyncMock()

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create a RateLimiter with mock Redis."""
        return RateLimiter(
            redis_client=mock_redis,
            per_user_limit=60,
            per_endpoint_limit=100,
            global_limit=1000,
            window_seconds=60,
        )

    @pytest.mark.asyncio
    async def test_check_allowed(self, rate_limiter, mock_redis):
        """Test that request is allowed when under all limits."""
        mock_redis.zremrangebyscore = AsyncMock()
        mock_redis.zcard = AsyncMock(side_effect=[0, 0, 0])  # All counts under limit
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()

        allowed, limit = await rate_limiter.check("user-123", "/api/test")

        assert allowed is True
        assert limit is None
        mock_redis.zadd.assert_called()  # Should add entries when allowed

    @pytest.mark.asyncio
    async def test_check_user_limit_exceeded(self, rate_limiter, mock_redis):
        """Test that user limit is enforced."""
        mock_redis.zremrangebyscore = AsyncMock()
        # User count at limit (60), endpoint (0), global (0)
        mock_redis.zcard = AsyncMock(side_effect=[60, 0, 0])
        mock_redis.zadd = AsyncMock()

        allowed, limit = await rate_limiter.check("user-123", "/api/test")

        assert allowed is False
        assert limit == 60
        mock_redis.zadd.assert_not_called()  # Should not add entries when denied

    @pytest.mark.asyncio
    async def test_check_endpoint_limit_exceeded(self, rate_limiter, mock_redis):
        """Test that endpoint limit is enforced."""
        mock_redis.zremrangebyscore = AsyncMock()
        # User count under limit (0), endpoint at limit (100), global (0)
        mock_redis.zcard = AsyncMock(side_effect=[0, 100, 0])
        mock_redis.zadd = AsyncMock()

        allowed, limit = await rate_limiter.check("user-123", "/api/test")

        assert allowed is False
        assert limit == 100
        mock_redis.zadd.assert_not_called()  # Should not add entries when denied
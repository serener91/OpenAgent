"""Rate limiting with Redis sliding window algorithm."""

import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis


class RateLimiter:
    """Rate limiter using Redis sorted sets with sliding window algorithm."""

    USER_KEY_PREFIX = "ratelimit:user:"
    ENDPOINT_KEY_PREFIX = "ratelimit:endpoint:"
    GLOBAL_KEY = "ratelimit:global"

    def __init__(
        self,
        redis_client: redis.Redis,
        per_user_limit: int = 60,
        per_endpoint_limit: int = 100,
        global_limit: int = 1000,
        window_seconds: int = 60,
    ):
        """Initialize rate limiter.

        Args:
            redis_client: Async Redis client instance.
            per_user_limit: Maximum requests per user within the window.
            per_endpoint_limit: Maximum requests per endpoint within the window.
            global_limit: Maximum global requests within the window.
            window_seconds: Sliding window size in seconds.
        """
        self.redis = redis_client
        self.per_user_limit = per_user_limit
        self.per_endpoint_limit = per_endpoint_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds

    def _user_key(self, user_id: str) -> str:
        """Generate Redis key for user rate limit.

        Args:
            user_id: The user identifier.

        Returns:
            Redis key string.
        """
        return f"{self.USER_KEY_PREFIX}{user_id}"

    def _endpoint_key(self, endpoint: str) -> str:
        """Generate Redis key for endpoint rate limit.

        Args:
            endpoint: The endpoint identifier.

        Returns:
            Redis key string.
        """
        return f"{self.ENDPOINT_KEY_PREFIX}{endpoint}"

    async def check(self, user_id: str, endpoint: str) -> tuple[bool, Optional[int]]:
        """Check if request is allowed under rate limits.

        Uses a sliding window algorithm with Redis sorted sets.
        Removes expired entries, counts current entries, and checks limits.
        If allowed, adds new entry and sets TTL on keys.

        Args:
            user_id: The user identifier.
            endpoint: The endpoint identifier.

        Returns:
            Tuple of (allowed: bool, limit_type: Optional[int]).
            (True, None) if request is allowed.
            (False, limit) if request exceeds limit, where limit is one of:
            - per_user_limit
            - per_endpoint_limit
            - global_limit
        """
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        window_start = now_ts - self.window_seconds

        user_key = self._user_key(user_id)
        endpoint_key = self._endpoint_key(endpoint)

        # Remove old entries outside the window using ZREMRANGEBYSCORE
        await self.redis.zremrangebyscore(user_key, "-inf", window_start)
        await self.redis.zremrangebyscore(endpoint_key, "-inf", window_start)
        await self.redis.zremrangebyscore(self.GLOBAL_KEY, "-inf", window_start)

        # Count entries in each window using ZCARD
        user_count = await self.redis.zcard(user_key)
        endpoint_count = await self.redis.zcard(endpoint_key)
        global_count = await self.redis.zcard(self.GLOBAL_KEY)

        # Check user limit first
        if user_count >= self.per_user_limit:
            return (False, self.per_user_limit)

        # Check endpoint limit
        if endpoint_count >= self.per_endpoint_limit:
            return (False, self.per_endpoint_limit)

        # Check global limit
        if global_count >= self.global_limit:
            return (False, self.global_limit)

        # Generate unique entry ID for this request
        entry_id = str(uuid.uuid4())
        entry_score = now_ts

        # Add entries using ZADD
        await self.redis.zadd(user_key, {entry_id: entry_score})
        await self.redis.zadd(endpoint_key, {entry_id: entry_score})
        await self.redis.zadd(self.GLOBAL_KEY, {entry_id: entry_score})

        # Set expire on keys to auto-cleanup
        await self.redis.expire(user_key, self.window_seconds + 1)
        await self.redis.expire(endpoint_key, self.window_seconds + 1)
        await self.redis.expire(self.GLOBAL_KEY, self.window_seconds + 1)

        return (True, None)
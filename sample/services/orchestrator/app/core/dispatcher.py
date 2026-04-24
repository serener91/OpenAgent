"""Redis Streams task dispatcher."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis

from app.config import get_settings


class TaskDispatcher:
    """Task dispatcher using Redis Streams."""

    def __init__(self) -> None:
        """Initialize the dispatcher."""
        self._settings = get_settings()
        self._redis_url = self._settings.redis.url
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection.

        Returns:
            Redis client instance.
        """
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    def dispatch(
        self,
        agent_name: str,
        user_id: str,
        session_id: str,
        prompt: str,
        context: dict[str, Any],
        priority: int,
    ) -> str:
        """Dispatch a task to an agent via Redis Stream.

        Args:
            agent_name: Name of the target agent.
            user_id: User identifier.
            session_id: Session identifier.
            prompt: Task prompt/instruction.
            context: Additional context data.
            priority: Task priority (1=critical, 5=trivial).

        Returns:
            Generated task ID.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        message = {
            "task_id": task_id,
            "agent_name": agent_name,
            "user_id": user_id,
            "session_id": session_id,
            "prompt": prompt,
            "context": json.dumps(context),
            "priority": priority,
            "created_at": created_at,
        }

        stream_name = f"stream:agent:{agent_name}"
        self._async_xadd(stream_name, message)

        return task_id

    def _async_xadd(self, stream_name: str, message: dict[str, Any]) -> None:
        """Execute XADD asynchronously.

        Args:
            stream_name: Redis stream name.
            message: Message data to add.
        """
        import asyncio

        async def _xadd() -> None:
            client = await self._get_redis()
            await client.xadd(stream_name, message)

        asyncio.create_task(_xadd())

    def get_result(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get task result from Redis.

        Args:
            task_id: Task identifier.

        Returns:
            Result dict if found, None otherwise.
        """
        import asyncio

        async def _get() -> Optional[dict[str, Any]]:
            client = await self._get_redis()
            key = f"response:{task_id}"
            data = await client.get(key)
            if data is None:
                return None
            return json.loads(data)

        # Run async code synchronously using a new event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, we need to use a different approach
                # For simplicity in this sync wrapper, create a new loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _get())
                    return future.result()
            else:
                return asyncio.run(_get())
        except RuntimeError:
            # No event loop running
            return asyncio.run(_get())

    def wait_for_result(self, task_id: str, timeout_seconds: int = 30) -> Optional[dict[str, Any]]:
        """Wait for task result with polling.

        Args:
            task_id: Task identifier.
            timeout_seconds: Maximum time to wait.

        Returns:
            Result dict if found within timeout, None otherwise.
        """
        elapsed = 0.0
        interval = 0.5

        while elapsed < timeout_seconds:
            result = self.get_result(task_id)
            if result is not None:
                return result
            time.sleep(interval)
            elapsed += interval

        return None
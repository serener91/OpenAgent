"""Abstract AgentWorker base class with Redis Streams consumer."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import redis
import structlog
from opentelemetry import trace

from app.config import settings


class AgentWorker(ABC):
    """Abstract base class for agent workers using Redis Streams."""

    def __init__(self):
        """Initialize the agent worker."""
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.redis_client: redis.Redis | None = None
        self._setup_tracing()

    def _setup_tracing(self) -> None:
        """Setup OpenTelemetry tracing for this worker."""
        resource = trace.Resource.create(
            {
                "service.name": settings.otel.service_name,
                "service.version": "0.1.0",
            }
        )
        provider = trace.TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

    async def connect(self) -> None:
        """Establish connection to Redis."""
        self.redis_client = redis.from_url(
            settings.redis.url,
            decode_responses=True,
        )
        self.logger.info("connected to redis", url=settings.redis.url)

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.aclose()
            self.logger.info("disconnected from redis")

    async def ensure_consumer_group(self) -> None:
        """Ensure the consumer group exists for the stream."""
        if not self.redis_client:
            raise RuntimeError("Not connected to Redis")

        try:
            await self.redis_client.xgroup_create(
                settings.redis.stream_name,
                settings.redis.consumer_group,
                id="0",
                mkstream=True,
            )
            self.logger.info(
                "created consumer group",
                group=settings.redis.consumer_group,
                stream=settings.redis.stream_name,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            self.logger.debug(
                "consumer group already exists",
                group=settings.redis.consumer_group,
            )

    @abstractmethod
    async def process_message(self, message_id: str, data: dict[str, Any]) -> None:
        """Process a single message from the stream.

        Args:
            message_id: The Redis stream message ID
            data: The message data
        """
        pass

    async def run(self) -> None:
        """Run the agent worker, consuming messages from the stream."""
        await self.connect()
        await self.ensure_consumer_group()

        self.logger.info(
            "agent worker starting",
            consumer_group=settings.redis.consumer_group,
            consumer_name=settings.redis.consumer_name,
            stream=settings.redis.stream_name,
        )

        try:
            while True:
                messages = await self.redis_client.xreadgroup(
                    groupname=settings.redis.consumer_group,
                    consumername=settings.redis.consumer_name,
                    streams={settings.redis.stream_name: ">"},
                    count=1,
                    block=1000,
                )

                if not messages:
                    continue

                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        self.logger.info(
                            "processing message",
                            message_id=message_id,
                            agent_type=settings.agent_type,
                        )
                        try:
                            await self.process_message(message_id, data)
                            await self.redis_client.xack(
                                settings.redis.stream_name,
                                settings.redis.consumer_group,
                                message_id,
                            )
                        except Exception as e:
                            self.logger.error(
                                "failed to process message",
                                message_id=message_id,
                                error=str(e),
                            )
        finally:
            await self.disconnect()

    async def submit_task(self, task_data: dict[str, Any]) -> str:
        """Submit a task to the stream.

        Args:
            task_data: The task data to submit

        Returns:
            The message ID of the submitted task
        """
        if not self.redis_client:
            raise RuntimeError("Not connected to Redis")

        message_id = await self.redis_client.xadd(
            settings.redis.stream_name,
            {
                "agent_type": settings.agent_type,
                "data": str(task_data),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.logger.info("task submitted", message_id=message_id)
        return message_id
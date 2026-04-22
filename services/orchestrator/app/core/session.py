"""Session management with Redis backend."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis
from pydantic import BaseModel, Field


class Message(BaseModel):
    """A message in a session."""

    role: str
    content: str
    agent_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionData(BaseModel):
    """Session data model."""

    session_id: str
    user_id: str
    created_at: datetime
    last_active: datetime
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[Message] = Field(default_factory=list)


class SessionManager:
    """Session manager with Redis backend."""

    SESSION_TTL = 24 * 60 * 60  # 24 hours in seconds
    KEY_PREFIX = "session:"

    def __init__(self, redis_client: redis.Redis):
        """Initialize session manager.

        Args:
            redis_client: Async Redis client instance.
        """
        self.redis = redis_client

    def _key(self, session_id: str) -> str:
        """Generate Redis key for session.

        Args:
            session_id: The session identifier.

        Returns:
            Redis key string.
        """
        return f"{self.KEY_PREFIX}{session_id}"

    async def create(self, user_id: str, metadata: Optional[dict[str, Any]] = None) -> SessionData:
        """Create a new session.

        Args:
            user_id: The user identifier.
            metadata: Optional initial context metadata.

        Returns:
            The created SessionData.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_active=now,
            context=metadata or {},
            messages=[],
        )

        await self.redis.setex(
            self._key(session_id),
            self.SESSION_TTL,
            session.model_dump_json(),
        )

        return session

    async def get(self, session_id: str) -> Optional[SessionData]:
        """Get a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            SessionData if found, None otherwise.
        """
        data = await self.redis.get(self._key(session_id))
        if data is None:
            return None

        return SessionData.model_validate_json(data)

    async def update(
        self, session_id: str, context_update: dict[str, Any]
    ) -> Optional[SessionData]:
        """Update session context.

        Args:
            session_id: The session identifier.
            context_update: Dictionary to merge into session context.

        Returns:
            Updated SessionData if found, None otherwise.
        """
        session = await self.get(session_id)
        if session is None:
            return None

        session.context.update(context_update)
        session.last_active = datetime.now(timezone.utc)

        await self.redis.setex(
            self._key(session_id),
            self.SESSION_TTL,
            session.model_dump_json(),
        )

        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
    ) -> Optional[SessionData]:
        """Add a message to a session.

        Args:
            session_id: The session identifier.
            role: Message role (user, assistant, etc.).
            content: Message content.
            agent_name: Optional name of the agent that sent the message.

        Returns:
            Updated SessionData if found, None otherwise.
        """
        session = await self.get(session_id)
        if session is None:
            return None

        message = Message(role=role, content=content, agent_name=agent_name)
        session.messages.append(message)
        session.last_active = datetime.now(timezone.utc)

        await self.redis.setex(
            self._key(session_id),
            self.SESSION_TTL,
            session.model_dump_json(),
        )

        return session

    async def delete(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The session identifier.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.redis.delete(self._key(session_id))
        return result > 0
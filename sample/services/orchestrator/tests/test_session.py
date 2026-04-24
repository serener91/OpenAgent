"""Tests for session management."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.core.session import Message, SessionData, SessionManager


class TestSessionData:
    """Tests for SessionData model."""

    def test_session_data_creation(self):
        """Test basic SessionData creation."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            session_id="test-123",
            user_id="user-456",
            created_at=now,
            last_active=now,
        )
        assert session.session_id == "test-123"
        assert session.user_id == "user-456"
        assert session.context == {}
        assert session.messages == []

    def test_session_data_with_context(self):
        """Test SessionData with context."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            session_id="test-123",
            user_id="user-456",
            created_at=now,
            last_active=now,
            context={"key": "value"},
        )
        assert session.context == {"key": "value"}


class TestMessage:
    """Tests for Message model."""

    def test_message_creation(self):
        """Test basic Message creation."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.agent_name is None
        assert msg.timestamp is not None

    def test_message_with_agent_name(self):
        """Test Message with agent name."""
        msg = Message(role="assistant", content="Hi", agent_name="test-agent")
        assert msg.agent_name == "test-agent"


class TestSessionManager:
    """Tests for SessionManager with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return AsyncMock()

    @pytest.fixture
    def session_manager(self, mock_redis):
        """Create a SessionManager with mock Redis."""
        return SessionManager(mock_redis)

    @pytest.mark.asyncio
    async def test_create_session(self, session_manager, mock_redis):
        """Test creating a new session."""
        mock_redis.setex = AsyncMock(return_value=True)

        session = await session_manager.create(user_id="user-123")

        assert session.user_id == "user-123"
        assert session.session_id is not None
        assert session.context == {}
        assert session.messages == []
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_with_metadata(self, session_manager, mock_redis):
        """Test creating a session with metadata."""
        mock_redis.setex = AsyncMock(return_value=True)

        session = await session_manager.create(
            user_id="user-123",
            metadata={"theme": "dark"},
        )

        assert session.context == {"theme": "dark"}
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_found(self, session_manager, mock_redis):
        """Test getting an existing session."""
        now = datetime.now(timezone.utc)
        session_data = SessionData(
            session_id="test-123",
            user_id="user-456",
            created_at=now,
            last_active=now,
        )
        mock_redis.get = AsyncMock(return_value=session_data.model_dump_json())

        session = await session_manager.get("test-123")

        assert session is not None
        assert session.session_id == "test-123"
        assert session.user_id == "user-456"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, session_manager, mock_redis):
        """Test getting a non-existent session."""
        mock_redis.get = AsyncMock(return_value=None)

        session = await session_manager.get("nonexistent")

        assert session is None

    @pytest.mark.asyncio
    async def test_add_message(self, session_manager, mock_redis):
        """Test adding a message to a session."""
        now = datetime.now(timezone.utc)
        session_data = SessionData(
            session_id="test-123",
            user_id="user-456",
            created_at=now,
            last_active=now,
        )
        mock_redis.get = AsyncMock(return_value=session_data.model_dump_json())
        mock_redis.setex = AsyncMock(return_value=True)

        updated = await session_manager.add_message(
            session_id="test-123",
            role="user",
            content="Hello, world!",
            agent_name=None,
        )

        assert updated is not None
        assert len(updated.messages) == 1
        assert updated.messages[0].role == "user"
        assert updated.messages[0].content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager, mock_redis):
        """Test deleting a session."""
        mock_redis.delete = AsyncMock(return_value=1)

        result = await session_manager.delete("test-123")

        assert result is True
        mock_redis.delete.assert_called_once_with("session:test-123")

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, session_manager, mock_redis):
        """Test deleting a non-existent session."""
        mock_redis.delete = AsyncMock(return_value=0)

        result = await session_manager.delete("nonexistent")

        assert result is False
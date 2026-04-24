"""Tests for task dispatcher."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.dispatcher import TaskDispatcher


class TestTaskDispatcher:
    """Tests for TaskDispatcher."""

    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher instance."""
        return TaskDispatcher()

    def test_dispatch(self, dispatcher):
        """Test task dispatch creates task with correct format."""
        agent_name = "test-agent"
        user_id = "user123"
        session_id = "sess456"
        prompt = "Analyze this data"
        context = {"key": "value"}
        priority = 2

        with patch.object(dispatcher, "_async_xadd") as mock_xadd:
            task_id = dispatcher.dispatch(
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                prompt=prompt,
                context=context,
                priority=priority,
            )

        # Verify task_id format
        assert task_id.startswith("task_")
        assert len(task_id) == 17  # "task_" + 12 hex chars

        # Verify XADD was called with correct stream name
        mock_xadd.assert_called_once()
        call_args = mock_xadd.call_args
        stream_name = call_args[0][0]
        assert stream_name == f"stream:agent:{agent_name}"

        # Verify message contents
        message = call_args[0][1]
        assert message["task_id"] == task_id
        assert message["agent_name"] == agent_name
        assert message["user_id"] == user_id
        assert message["session_id"] == session_id
        assert message["prompt"] == prompt
        assert message["context"] == '{"key": "value"}'
        assert message["priority"] == priority
        assert "created_at" in message

    def test_get_result_found(self, dispatcher):
        """Test get_result returns parsed result when found."""
        task_id = "task_abc123def456"
        expected_result = {"status": "completed", "data": {"result": "test"}}

        with patch.object(dispatcher, "_get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value='{"status": "completed", "data": {"result": "test"}}')
            mock_get_redis.return_value = mock_redis

            result = dispatcher.get_result(task_id)

        assert result == expected_result
        mock_redis.get.assert_called_once_with(f"response:{task_id}")

    def test_get_result_not_found(self, dispatcher):
        """Test get_result returns None when not found."""
        task_id = "task_xyz789abc123"

        with patch.object(dispatcher, "_get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_get_redis.return_value = mock_redis

            result = dispatcher.get_result(task_id)

        assert result is None
        mock_redis.get.assert_called_once_with(f"response:{task_id}")
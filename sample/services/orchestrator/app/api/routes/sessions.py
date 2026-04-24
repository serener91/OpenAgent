"""Session API routes."""

from typing import Any, Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.session import SessionData, SessionManager

router = APIRouter(tags=["sessions"])


async def get_redis() -> redis.Redis:
    """Get Redis client dependency.

    Returns:
        Redis client instance.
    """
    # This will be overridden by the dependency injection in main.py
    # when a Redis client is provided via the app state or dependency
    raise NotImplementedError("Redis dependency not configured")


def get_session_manager() -> SessionManager:
    """Get SessionManager dependency.

    Returns:
        SessionManager instance.
    """
    # Placeholder - actual implementation uses dependency override
    raise NotImplementedError("Session manager dependency not configured")


class SessionManagerDepends:
    """Dependency provider for SessionManager."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def get_session_manager(self) -> SessionManager:
        """Get a SessionManager instance."""
        return SessionManager(self.redis)


@router.post(
    "/sessions",
    response_model=SessionData,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    user_id: str,
    metadata: Optional[dict[str, Any]] = None,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionData:
    """Create a new session.

    Args:
        user_id: The user identifier.
        metadata: Optional initial context metadata.
        session_manager: Session manager dependency.

    Returns:
        The created session data.
    """
    return await session_manager.create(user_id=user_id, metadata=metadata)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionData,
)
async def get_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionData:
    """Get a session by ID.

    Args:
        session_id: The session identifier.
        session_manager: Session manager dependency.

    Returns:
        The session data.

    Raises:
        HTTPException: If session not found.
    """
    session = await session_manager.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> None:
    """Delete a session.

    Args:
        session_id: The session identifier.
        session_manager: Session manager dependency.

    Raises:
        HTTPException: If session not found.
    """
    deleted = await session_manager.delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
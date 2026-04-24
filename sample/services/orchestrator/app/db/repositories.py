"""Database repositories for the orchestrator service."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Agent, AgentStatus, UserPreferences

engine = create_async_engine(get_settings().database.url, echo=get_settings().database.echo)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Initialize the database by creating all tables."""
    from app.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Yields:
        AsyncSession: Database session.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class AgentRepository:
    """Repository for Agent model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session.

        Args:
            session: Database session.
        """
        self.session = session

    async def create(self, name: str, description: str, capabilities: dict[str, Any] | None = None) -> Agent:
        """Create a new agent.

        Args:
            name: Agent name.
            description: Agent description.
            capabilities: Agent capabilities.

        Returns:
            Created agent instance.
        """
        agent = Agent(
            name=name,
            description=description,
            capabilities=capabilities or {},
            status=AgentStatus.ACTIVE,
        )
        self.session.add(agent)
        await self.session.flush()
        await self.session.refresh(agent)
        return agent

    async def get_by_name(self, name: str) -> Agent | None:
        """Get an agent by name.

        Args:
            name: Agent name.

        Returns:
            Agent instance or None if not found.
        """
        result = await self.session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Agent]:
        """List all active agents.

        Returns:
            List of active agents.
        """
        result = await self.session.execute(
            select(Agent).where(Agent.status == AgentStatus.ACTIVE).order_by(Agent.name)
        )
        return list(result.scalars().all())

    async def update_status(self, agent_id: Any, status: AgentStatus) -> Agent | None:
        """Update agent status.

        Args:
            agent_id: Agent UUID.
            status: New status.

        Returns:
            Updated agent or None if not found.
        """
        result = await self.session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            return None
        agent.status = status
        await self.session.flush()
        await self.session.refresh(agent)
        return agent


class UserPreferencesRepository:
    """Repository for UserPreferences model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session.

        Args:
            session: Database session.
        """
        self.session = session

    async def get_or_create(self, user_id: str) -> UserPreferences:
        """Get or create user preferences.

        Args:
            user_id: User identifier.

        Returns:
            User preferences instance.
        """
        result = await self.session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            self.session.add(prefs)
            await self.session.flush()
            await self.session.refresh(prefs)
        return prefs

    async def update(self, user_id: str, **kwargs: Any) -> UserPreferences | None:
        """Update user preferences.

        Args:
            user_id: User identifier.
            **kwargs: Fields to update.

        Returns:
            Updated user preferences or None if not found.
        """
        result = await self.session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs is None:
            return None
        for key, value in kwargs.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        await self.session.flush()
        await self.session.refresh(prefs)
        return prefs
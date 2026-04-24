"""SQLAlchemy ORM models shared across services.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §9.1

Design note: this is the canonical schema registry. Alembic lives alongside
(at services/common/alembic/) and is driven by `Base.metadata`. Services
that need repository-layer code (e.g., orchestrator) import these models
rather than redefining them. Service-local tables (e.g., messages, api_keys)
land in their owning service's db/models.py in later phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. All tables anchored here feed Alembic."""


class Agent(Base):
    """Canonical agent registry row. See umbrella §9.1."""

    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tool_allowlist: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Column name `metadata` is a reserved attribute on DeclarativeBase, so
    # we map the attribute to a differently-named column via `name=`.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )

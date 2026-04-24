"""initial: agents table

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("name", sa.String(length=255), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "tool_allowlist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column(
            "registered_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_heartbeat", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_table("agents")

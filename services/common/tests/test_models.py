"""Tests for openagent_common.db.models.

These are schema-level unit tests — they inspect the SQLAlchemy mapper,
not a live DB. Migration behavior against real Postgres is covered in
tests/integration/test_alembic.py.
"""

from __future__ import annotations

from openagent_common.db.models import Agent, Base


def test_base_is_declarative_base() -> None:
    # Declarative Base exposes a registry
    assert hasattr(Base, "registry")


def test_agent_tablename() -> None:
    assert Agent.__tablename__ == "agents"


def test_agent_has_expected_columns() -> None:
    col_names = {c.name for c in Agent.__table__.columns}
    assert col_names == {
        "name",
        "description",
        "capabilities",
        "tool_allowlist",
        "status",
        "version",
        "registered_at",
        "last_heartbeat",
        "metadata",
    }


def test_agent_primary_key_is_name() -> None:
    pk = Agent.__table__.primary_key.columns.keys()
    assert pk == ["name"]


def test_agent_nullable_columns() -> None:
    cols = {c.name: c for c in Agent.__table__.columns}
    assert cols["description"].nullable is False
    assert cols["capabilities"].nullable is False
    assert cols["version"].nullable is False
    assert cols["last_heartbeat"].nullable is True


def test_agent_defaults() -> None:
    cols = {c.name: c for c in Agent.__table__.columns}
    # server_defaults should exist on status, tool_allowlist, metadata, registered_at
    assert cols["status"].server_default is not None
    assert cols["tool_allowlist"].server_default is not None
    assert cols["metadata"].server_default is not None
    assert cols["registered_at"].server_default is not None

"""Integration test: Alembic migration 0001 against real Postgres.

Requires docker compose stack from Task 7 to be up.
Runs against a throwaway database: `openagent_migration_test`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.integration

# Admin URL for creating/dropping the throwaway test DB.
_ADMIN_DSN = "postgresql://openagent:openagent@localhost:5432/postgres"
_TEST_DB = "openagent_migration_test"
_TEST_DSN = f"postgresql+asyncpg://openagent:openagent@localhost:5432/{_TEST_DB}"
_TEST_DSN_SYNC = f"postgresql://openagent:openagent@localhost:5432/{_TEST_DB}"
_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest.fixture
def fresh_db() -> str:
    """Drop-and-recreate a test database. Yields the sync DSN."""
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(_TEST_DB)
                )
            )
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_TEST_DB))
            )
    yield _TEST_DSN_SYNC
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(_TEST_DB)
                )
            )


def _alembic(args: list[str], dsn: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn.replace("postgresql://", "postgresql+asyncpg://")
    return subprocess.run(
        ["uv", "run", "alembic", "-c", str(_ALEMBIC_INI), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_upgrade_creates_agents_table(fresh_db: str) -> None:
    result = _alembic(["upgrade", "head"], fresh_db)
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

    with psycopg.connect(fresh_db, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'agents' ORDER BY ordinal_position"
        )
        cols = cur.fetchall()

    names = {c[0] for c in cols}
    assert names == {
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


def test_downgrade_drops_agents_table(fresh_db: str) -> None:
    up = _alembic(["upgrade", "head"], fresh_db)
    assert up.returncode == 0
    down = _alembic(["downgrade", "base"], fresh_db)
    assert down.returncode == 0, f"alembic downgrade failed:\n{down.stderr}"

    with psycopg.connect(fresh_db, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'agents'"
        )
        assert cur.fetchone() is None


def test_upgrade_is_idempotent(fresh_db: str) -> None:
    # Running upgrade twice must be a no-op the second time.
    r1 = _alembic(["upgrade", "head"], fresh_db)
    r2 = _alembic(["upgrade", "head"], fresh_db)
    assert r1.returncode == 0 and r2.returncode == 0

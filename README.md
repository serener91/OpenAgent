#### My personal space to build, play, and experiment with the agent system.


[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)

# OpenAgent

Multi-agent orchestration system — see `docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md` for the umbrella design.

## Developer Quickstart

Prerequisites:
- Docker Desktop or Docker Engine 24+ with Compose v2
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- CPython 3.13 (uv will install if missing)

### 1. Install Python deps

```bash
uv sync
```

### 2. Start infra

```bash
cp .env.example .env
docker compose up -d
docker compose ps   # wait for postgres/redis/meilisearch = healthy
```

Infra URLs on the host:
- Postgres: `localhost:5432` (user/password: `openagent`/`openagent`, db: `openagent`)
- Redis: `localhost:6379`
- Meilisearch: `http://localhost:7700`
- Jaeger UI: `http://localhost:16686`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (anonymous Viewer access enabled)

### 3. Apply DB migrations

```bash
cd services/common
DATABASE_URL=postgresql+asyncpg://openagent:openagent@localhost:5432/openagent \
  uv run alembic upgrade head
cd ../..
```

### 4. Run tests

Unit tests (fast, no infra):

```bash
uv run pytest services/common/tests -v --ignore=services/common/tests/integration
```

Integration + smoke tests (require `docker compose up`):

```bash
uv run pytest -v -m integration
```

## Repository Layout

```
.
├── docs/superpowers/specs/   # design specs (v1.2 umbrella + sub-specs)
├── docs/superpowers/plans/   # phased implementation plans
├── sample/                   # v1.1-era scaffolding kept for reference only
├── services/common/          # shared primitives (schemas, Protocols, OTEL, DB)
├── ops/                      # Prometheus + Grafana provisioning
├── tests/smoke/              # end-to-end infra reachability checks
├── docker-compose.yml
└── pyproject.toml            # UV workspace root
```

## Troubleshooting

- **`uv sync` fails on `openagent-common`:** ensure `services/common/pyproject.toml` exists and the `hatchling` backend can find `src/openagent_common`.
- **Alembic can't import `openagent_common`:** run `uv sync` from the repo root (the workspace install makes `openagent_common` available to any subpackage).
- **Postgres container unhealthy:** `docker compose logs postgres`. Most common cause is a stale `postgres_data` volume from a previous user/password — `docker compose down -v` to reset.
- **Jaeger UI blank:** generate traffic first; the UI only lists services that have emitted spans.

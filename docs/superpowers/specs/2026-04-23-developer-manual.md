# Multi-Agent Orchestration System — Developer Manual

**Document Version:** 1.0
**Date:** 2026-04-23
**For:** Developers building on or maintaining this system

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technical Stack](#2-technical-stack)
3. [Architecture](#3-architecture)
4. [Services Reference](#4-services-reference)
5. [API Reference](#5-api-reference)
6. [Data Flow](#6-data-flow)
7. [Configuration](#7-configuration)
8. [Deployment](#8-deployment)
9. [Adding a New Agent](#9-adding-a-new-agent)
10. [Observability](#10-observability)
11. [Framework Notes](#11-framework-notes)

---

## 1. System Overview

This is a **workplace AI assistant platform** — a standalone multi-agent orchestration system that receives tasks from users via a REST API, decomposes them using an LLM-powered orchestrator, and dispatches them to specialized agents equipped with tools via MCP (Model Context Protocol).

### What it does

```
User → REST API → Orchestrator → [LLM Routing] → Agent (via Redis Streams)
                                                          ↓
                                                    MCP Gateway → Tools
```

- **Orchestrator**: Receives messages, manages sessions, routes tasks to agents via LLM, enforces rate limits
- **Agents**: Long-running worker services that consume tasks from Redis Streams and execute them (e.g., file operations, PDF analysis)
- **MCP Gateway**: Central registry and execution layer for tools that agents can call

### Target scale

- 100+ concurrent users
- 20+ concurrent active agents
- On-premise deployment (private server or Kubernetes)

### Target users

- Enterprise employees requiring AI assistance
- External systems (Slack, Teams, internal portals) via REST API
- Frontend developers building chat interfaces on the API

---

## 2. Technical Stack

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Language | Python | 3.13 | Primary language |
| Package Manager | UV | latest | Fast Rust-based Python package manager |
| API Framework | FastAPI | ≥0.115.0 | Async REST API with OpenAPI |
| Agent Framework | OpenAI Agents SDK | ≥0.0.11 | Native LLM agent execution |
| MCP Framework | FastMCP | ≥1.6.0 | Tool server development |
| Message Queue | Redis Streams | 7-alpine | Async task dispatch between services |
| Database | PostgreSQL | 16-alpine | Persistent storage (sessions, conversations) |
| Vector Search | Meilisearch | latest | Semantic search capability |
| Tracing | OpenTelemetry | ≥1.28.0 | Distributed tracing (OTLP → Jaeger) |
| Logging | structlog | ≥25.0.0 | Structured JSON logging with trace injection |
| Metrics | Prometheus | — | `/metrics` endpoint on orchestrator |
| Containerization | Docker Compose | — | Local development; Kubernetes-ready |

> **Note on UV:** UV replaces pip/poetry/pipenv. It is used across all services. Install via:
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```

> **Version Check:** Verify all package versions against PyPI before use. Documented versions were current as of 2026-04-23.

---

## 3. Architecture

### High-level diagram

```
┌─────────────────────────────────────────────────────┐
│                    External Clients                  │
│         (REST API / Slack / Teams / Frontends)       │
└────────────────────────┬────────────────────────────┘
                         │ HTTP/REST
                         ▼
┌─────────────────────────────────────────────────────┐
│                   Orchestrator (8000)                │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────┐│
│  │  Router   │ │ Dispatcher│ │  Session  │ │ Rate ││
│  │  (LLM)    │ │  (Redis   │ │  Manager  │ │ Limiter│
│  │           │ │  Streams) │ │  (Redis)  │ │      ││
│  └───────────┘ └───────────┘ └───────────┘ └──────┘│
└────────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
┌────────────┐   ┌────────────┐   ┌────────────┐
│ File Agent │   │ Agent B    │   │ Agent N    │
│ (worker)   │   │ (worker)   │   │ (worker)   │
└─────┬──────┘   └─────┬──────┘   └─────┬──────┘
      │                │                │
      └────────────────┼────────────────┘
                       ▼
            ┌─────────────────────┐
            │    MCP Gateway      │
            │  (8001) + Tools     │
            └─────────────────────┘
```

### Key architectural decisions

- **LLM-powered routing**: The orchestrator calls an LLM (at `base_url/chat/completions`) to decide which agent should handle a message. No hardcoded intent classification.
- **Redis Streams for task dispatch**: Tasks are written to agent-specific streams (`stream:agent:{agent_name}`). Workers consume via `xreadgroup()`.
- **Stateless sessions**: Session data (conversation history) is stored in Redis with a 24-hour TTL. Token-carrying so any orchestrator instance can handle any request.
- **PostgreSQL for persistent memory**: SQLAlchemy models exist for `Conversation`, `Message`, `Agent`, `UserPreferences`. Currently Redis handles active sessions; PostgreSQL layer is available for future persistent memory (Mem0 swap).
- **Central MCP Gateway**: All tool registration/execution goes through one gateway service. Agents are tool consumers, not tool hosts.
- **Async throughout**: All I/O (Redis, PostgreSQL, HTTP calls) is async via `asyncio` and `asyncpg` / `redis.asyncio`.

---

## 4. Services Reference

### 4.1 Orchestrator (port 8000)

**Purpose**: Central API gateway, session management, LLM routing, task dispatch, rate limiting.

**Entry point**: `services/orchestrator/app/main.py` → `app.main:app`

**Key components**:

| File | Responsibility |
|------|----------------|
| `api/routes/messages.py` | `POST /messages` (send), `GET /messages/{id}` (result), `GET /messages` (list) |
| `api/routes/sessions.py` | `POST/GET/DELETE /sessions` |
| `api/routes/health.py` | `GET /health`, `GET /ready` |
| `core/router.py` | `LLMRouter` — calls LLM to select agent based on registered capabilities |
| `core/dispatcher.py` | `TaskDispatcher` — writes tasks to Redis Streams per agent |
| `core/session.py` | `SessionManager` — Redis-backed session CRUD with 24h TTL |
| `core/rate_limiter.py` | `RateLimiter` — sliding window via Redis sorted sets |
| `db/models.py` | SQLAlchemy models (Conversation, Message, Agent, UserPreferences) |
| `observability/logging.py` | structlog setup with trace ID injection |
| `observability/metrics.py` | Prometheus counters/gauges/histograms |
| `observability/tracing.py` | OpenTelemetry OTLP setup |

### 4.2 MCP Gateway (port 8001)

**Purpose**: Central tool registry and execution layer implementing MCP.

**Entry point**: `services/mcp_gateway/app/server.py` → `app.server:app`

**Key components**:

| File | Responsibility |
|------|----------------|
| `app/server.py` | FastAPI app with `POST /tools/execute` endpoint |
| `app/tool_registry.py` | `ToolRegistry` class — registers tools, executes by name |
| `mcp_servers/file_tools/server.py` | FastMCP server with `@mcp.tool()` decorated tools |
| `app/observability/__init__.py` | structlog + trace ID injection |

**Registered tools** (at startup):
- `read_file` — reads file contents, supports `max_lines` truncation
- `list_directory` — lists directory contents with size info

### 4.3 Agent Base (`agents/base`)

**Purpose**: Abstract base class for all agent workers.

**Package**: `agents-base` (pip package, workspace member)

**Key file**: `services/agents/base/app/worker.py`

**`AgentWorker` abstract class**:

```python
class AgentWorker(ABC):
    async def connect(self) -> None
    async def disconnect(self) -> None
    async def ensure_consumer_group(self) -> None  # Creates consumer group on Redis Stream
    async def run(self) -> None  # Main loop: xreadgroup → process_message → xack
    async def submit_task(self, task_data: dict) -> str  # Writes to stream

    @abstractmethod
    async def process_message(self, message_id: str, data: dict) -> None
```

The `run()` method implements the consumer loop:

```python
while True:
    messages = self.redis_client.xreadgroup(
        groupname=settings.redis.consumer_group,  # "agents"
        consumername=settings.redis.consumer_name,  # e.g., "file_agent"
        streams={settings.redis.stream_name: ">"},  # "agent_tasks"
        count=1,
        block=1000,
    )
    for stream, stream_messages in messages:
        for message_id, data in stream_messages:
            await self.process_message(message_id, data)
            self.redis_client.xack(...)  # Acknowledge on success
```

**Important**: `xreadgroup`, `xadd`, `xack`, and `xgroup_create` are **sync methods** in redis-py 7.x. Do NOT use `await` with them.

### 4.4 File Agent (`agents/file_agent`)

**Purpose**: Concrete agent implementing file operations using the OpenAI Agents SDK.

**Entry point**: `services/agents/file_agent/app/agent.py` → `python -m app.agent`

**`FileAgent` class** (extends `AgentWorker`):

```python
class FileAgent(AgentWorker):
    def __init__(self):
        self.capabilities = ["read_file", "list_directory"]
        self.agent = Agent(
            name="file_agent",
            instructions="...",
            tools=file_tools,  # @function_tool decorated functions
        )

    async def process_message(self, message_id: str, data: dict) -> None:
        task_type = data.get("task_type")
        if task_type == "agent_task":
            result = await self.process_task(data)
        elif task_type == "read_file":
            await self._handle_read_file(data)
        elif task_type == "list_directory":
            await self._handle_list_directory(data)
```

Uses `@function_tool` decorator from `openai-agents` for tool definitions:

```python
@function_tool
def read_file(path: str, max_lines: int = 100) -> str:
    """Read contents of a file..."""
    ...
```

---

## 5. API Reference

### Orchestrator (port 8000)

#### `POST /api/v1/sessions`
Create a new session.

**Request**:
```json
{
  "user_id": "user_123"
}
```

**Response** (201):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_123",
  "created_at": "2026-04-23T10:00:00Z",
  "last_active": "2026-04-23T10:00:00Z",
  "context": {},
  "messages": []
}
```

#### `GET /api/v1/sessions/{session_id}`
Get session with messages.

**Response** (200): `SessionData` object (same as above, with messages populated).

#### `DELETE /api/v1/sessions/{session_id}`
Delete session and all messages.

**Response** (204): No content.

#### `POST /api/v1/sessions/{session_id}/messages`
Send a message. Triggers LLM routing and task dispatch.

**Request**:
```json
{
  "content": "read the file at /tmp/data.txt",
  "agent_name": "auto"  // "auto" = LLM decides, or specify agent
}
```

**Response** (202):
```json
{
  "message_id": "msg_abc123",
  "task_id": "task_a1b2c3d4e5f6",
  "status": "processing"
}
```

#### `GET /api/v1/sessions/{session_id}/messages/{message_id}`
Poll for task result.

**Response** (200):
```json
{
  "message_id": "msg_abc123",
  "task_id": "task_a1b2c3d4e5f6",
  "status": "completed",
  "response": {
    "agent_name": "file_agent",
    "result": "File contents..."
  }
}
```

Status values: `processing`, `completed`, `failed`.

#### `GET /api/v1/health`
Liveness probe.

**Response**: `{"status": "healthy", "timestamp": "..."}`

#### `GET /api/v1/ready`
Readiness probe.

**Response**: `{"status": "ready", "timestamp": "..."}`

#### `GET /metrics`
Prometheus metrics endpoint.

### MCP Gateway (port 8001)

#### `POST /tools/execute`
Execute a registered tool directly.

**Request**:
```json
{
  "tool_name": "read_file",
  "arguments": {
    "path": "/tmp/data.txt",
    "max_lines": 50
  }
}
```

**Response**:
```json
{
  "result": "file contents here..."
}
```

#### `GET /health`
Health check.

**Response**: `{"status": "healthy", "timestamp": "..."}`

---

## 6. Data Flow

### Sending a message (happy path)

```
1. Client → POST /api/v1/sessions/{id}/messages
   Body: {"content": "read file /tmp/data.txt"}

2. Orchestrator:
   a. SessionManager.get(session_id) → validates session exists in Redis
   b. RateLimiter.check(user_id, "messages") → sliding window, 429 if exceeded
   c. LLMRouter.route(content, history) → POST to LLM base_url/chat/completions
      → Returns agent_name = "file_agent"
   d. TaskDispatcher.dispatch(agent_name, user_id, session_id, prompt, context)
      → redis.xadd("stream:agent:file_agent", {...})
      → Returns task_id = "task_a1b2c3d4e5f6"
   e. Returns 202 Accepted: {"message_id": "...", "task_id": "..."}

3. File Agent (background, consuming from stream):
   a. redis.xreadgroup() → receives message with task_id
   b. process_message() → calls self.agent.run() with prompt
   c. Stores result: redis.set("response:task_a1b2c3d4e5f6", json.dumps(result))
   d. redis.xack() → acknowledges message

4. Client → GET /api/v1/sessions/{id}/messages/{message_id}
   → dispatcher.get_result(task_id) → redis.get("response:task_a1b2c3d4e5f6")
   → Returns {"status": "completed", "response": {...}}
```

### Redis key patterns

| Key | Type | Purpose | TTL |
|-----|------|---------|-----|
| `session:{session_id}` | String (JSON) | Session data with messages | 24h |
| `stream:agent:{agent_name}` | Stream | Task queue per agent | None |
| `response:{task_id}` | String (JSON) | Task result | 1h |
| `rate_limit:{user_id}:{endpoint}` | Sorted Set | Sliding window timestamps | Per window |

---

## 7. Configuration

### Environment variables

All services use **Pydantic Settings** with `env_nested_delimiter = "__"`. This means nested settings use double underscore in env vars:

```
REDIS__URL=redis://redis:6379/0        → settings.redis.url
DATABASE__URL=postgresql+asyncpg://... → settings.database.url
OTEL__EXPORTER_OTLP_ENDPOINT=...       → settings.otel.exporter_otlp_endpoint
OTEL__SERVICE_NAME=orchestrator        → settings.otel.service_name
```

### Per-service configuration

**Orchestrator** (`services/orchestrator/app/config.py`):
- `REDIS__URL` — Redis connection
- `DATABASE__URL` — PostgreSQL connection
- `OTEL_EXPORTER_OTLP_ENDPOINT` — Jaeger OTLP endpoint (default: `http://localhost:4317`)
- `OTEL_SERVICE_NAME` — Service name for tracing (default: `orchestrator`)
- `LLM__BASE_URL` — LLM backend URL (default: `http://localhost:8000`)
- `LLM__MODEL` — Model name (default: `gpt-4o`)
- `LLM__API_KEY` — API key (optional, for external LLMs)

**MCP Gateway** (`services/mcp_gateway/app/config.py`):
- `REDIS__URL`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_SERVICE_NAME` (default: `mcp_gateway`)

**File Agent** (`services/agents/file_agent/app/config.py`):
- `REDIS__URL` (default: `redis://localhost:6379/0`)
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_SERVICE_NAME` (default: `file_agent`)
- `AGENT_TYPE` (default: `file`)

**Agent Base** (`services/agents/base/app/config.py`):
- `REDIS__URL`
- `REDIS__STREAM_NAME` (default: `agent_tasks`)
- `REDIS__CONSUMER_GROUP` (default: `agents`)
- `REDIS__CONSUMER_NAME` (default: `consumer`)

### Docker Compose environment

In `docker-compose.yml`, services pass environment variables directly:

```yaml
orchestrator:
  environment:
    - REDIS__URL=redis://redis:6379/0
    - DATABASE__URL=postgresql+asyncpg://postgres:postgres@postgres:5432/openagent
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    - OTEL_SERVICE_NAME=orchestrator

mcp_gateway:
  environment:
    - REDIS__URL=redis://redis:6379/0
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    - OTEL_SERVICE_NAME=mcp_gateway

agent_file:
  environment:
    - REDIS__URL=redis://redis:6379/0
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    - OTEL_SERVICE_NAME=file_agent
    - AGENT_TYPE=file
```

---

## 8. Deployment

### Local development

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# View logs for specific service
docker compose logs -f orchestrator

# Restart a specific service (rebuilds if code changed)
docker compose up -d --build orchestrator

# Stop all services
docker compose down

# Full clean rebuild
docker compose down --volumes
docker compose up -d --build
```

### Ports

| Service | Port | Endpoint |
|---------|------|----------|
| Orchestrator | 8000 | http://localhost:8000 |
| MCP Gateway | 8001 | http://localhost:8001 |
| Redis | 6379 | redis://localhost:6379 |
| PostgreSQL | 5432 | localhost:5432 |
| Meilisearch | 7700 | http://localhost:7700 |
| Jaeger UI | 16686 | http://localhost:16686 |
| Jaeger OTLP | 4317 | grpc://localhost:4317 |

### Health checks

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
curl http://localhost:8001/health
```

### Volumes

| Volume | Purpose |
|--------|---------|
| `redis_data` | Redis persistence |
| `postgres_data` | PostgreSQL persistence |
| `meilisearch_data` | Meilisearch persistence |

### Kubernetes readiness

The system is designed for Kubernetes deployment. All services:
- Expose health/readiness endpoints
- Have non-root Docker users
- Accept configuration via environment variables
- Log in structured JSON format for log aggregation

---

## 9. Adding a New Agent

This is the most common extension point. Follow these steps to add a new agent (e.g., a `web_agent` for web search).

### Step 1: Create agent directory structure

```bash
services/agents/
  web_agent/
    app/
      __init__.py
      agent.py      # Your AgentWorker subclass
      config.py     # Pydantic settings
    pyproject.toml
    Dockerfile
    uv.lock
```

### Step 2: Define pyproject.toml

```toml
[project]
name = "web-agent"
version = "0.1.0"
description = "Web search agent"
requires-python = ">=3.11"
dependencies = [
    "agents-base",  # Use the base package
    "redis>=5.2.0",
    "opentelemetry-api>=1.28.0",
    "opentelemetry-sdk>=1.28.0",
    "openai-agents>=0.0.11",
    "pydantic-settings>=2.6.0",
    "structlog>=25.0.0",
    "python-dotenv>=1.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

### Step 3: Create config.py

```python
"""Configuration for web agent service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"
    stream_name: str = "agent_tasks"
    consumer_group: str = "agents"
    consumer_name: str = "web_agent"


class OTelSettings(BaseSettings):
    service_name: str = "web_agent"
    exporter_otlp_endpoint: str = "http://localhost:4317"
    exporter_otlp_insecure: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    agent_type: str = "web"

    redis: RedisSettings = RedisSettings()
    otel: OTelSettings = OTelSettings()


settings = Settings()
```

### Step 4: Implement agent.py

```python
"""Web agent implementation using OpenAI Agents SDK."""

import asyncio
from typing import Any

import structlog
from agents import Agent, function_tool

from app.config import settings
from app.worker import AgentWorker


def create_web_tools() -> list:
    """Create web operation tools."""

    @function_tool
    def search(query: str, max_results: int = 5) -> str:
        """Search the web for information."""
        # Your implementation
        return f"Search results for: {query}"

    @function_tool
    def fetch_url(url: str) -> str:
        """Fetch content from a URL."""
        # Your implementation
        return f"Content from: {url}"

    return [search, fetch_url]


class WebAgent(AgentWorker):
    """Web search agent using OpenAI Agents SDK."""

    def __init__(self):
        super().__init__()
        self.capabilities = ["web_search", "url_fetch"]
        web_tools = create_web_tools()
        self.agent = Agent(
            name="web_agent",
            instructions="You are a helpful web search assistant...",
            tools=web_tools,
        )
        self.logger.info("web agent initialized", capabilities=self.capabilities)

    async def process_message(self, message_id: str, data: dict[str, Any]) -> None:
        task_type = data.get("task_type", "unknown")
        if task_type == "agent_task":
            result = await self.process_task(data)
        elif task_type == "search":
            await self._handle_search(data)
        else:
            self.logger.warning("unknown task type", task_type=task_type)


async def main():
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(min_level=20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
    agent = WebAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 5: Register the agent with the orchestrator

In `services/orchestrator/app/api/routes/messages.py`, add to the router initialization:

```python
_router.register_agent(AgentCapability(
    name="web_agent",
    description="Handles web search, URL fetching, and online research",
    capabilities=["web_search", "url_fetch", "online_research"],
))
```

### Step 6: Add to Docker Compose

```yaml
web_agent:
  build:
    context: ./services/agents/web_agent
    dockerfile: Dockerfile
  environment:
    - REDIS__URL=redis://redis:6379/0
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    - OTEL_SERVICE_NAME=web_agent
    - AGENT_TYPE=web
  depends_on:
    - redis
    - jaeger
  volumes:
    - ./services/agents/web_agent:/app
```

### Step 7: Add to Dockerfile

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync
COPY . .
CMD ["uv", "run", "python", "-m", "app.agent"]
```

---

## 10. Observability

### Tracing

All services export traces to Jaeger via OTLP (OpenTelemetry Protocol).

**Endpoint**: `http://jaeger:4317` (gRPC)

**What is traced**:
- Every HTTP request (FastAPI instrumentation)
- Redis operations (Redis instrumentation)
- LLM API calls (manual span creation in `router.py`)

**Viewing traces**: Open http://localhost:16686 in your browser.

**Trace ID in logs**: Every log entry includes `trace_id` and `span_id` fields extracted from the current OpenTelemetry span, enabling correlation between logs and traces.

### Logging

All services use structured JSON logging via `structlog`:

```json
{
  "name": "FileAgent",
  "event": "processing message",
  "message_id": "1234567890-0",
  "agent_type": "file",
  "level": "info",
  "timestamp": "2026-04-23T10:00:00.000000Z",
  "trace_id": "abc123def456...",
  "span_id": "1234567890abcdef"
}
```

The `inject_trace_id` processor adds trace/span IDs from the current OpenTelemetry span to every log entry.

### Metrics

The orchestrator exposes Prometheus metrics at `GET /metrics`.

**Key metrics**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `orchestrator_requests_total` | Counter | endpoint, method, status | Total HTTP requests |
| `orchestrator_requests_active` | Gauge | — | Currently processing requests |
| `agent_tasks_total` | Counter | agent_name, status | Tasks dispatched to agents |
| `agent_tasks_duration_seconds` | Histogram | agent_name | Task processing time |
| `mcp_tool_calls_total` | Counter | tool_name, status | Tool executions |
| `mcp_tool_duration_seconds` | Histogram | tool_name | Tool execution time |
| `session_active` | Gauge | — | Active sessions in Redis |

### Log levels

| Level | Value | Usage |
|-------|-------|-------|
| DEBUG | 10 | Detailed diagnostic info |
| INFO | 20 | Normal operation events |
| WARNING | 30 | Unexpected but handled situations |
| ERROR | 40 | Errors that may require attention |

Set via `LOG_LEVEL` environment variable (defaults to `INFO`).

---

## 11. Framework Notes

### structlog v25+ `make_filtering_bound_logger`

**Important API change**: In structlog ≥25.0, the `make_filtering_bound_logger` function requires a `min_level` keyword argument (not `level`):

```python
# ❌ Wrong (will raise TypeError)
structlog.make_filtering_bound_logger(level=20)

# ✅ Correct
structlog.make_filtering_bound_logger(min_level=20)
```

This affects all services. The wrapper class configured in `setup_logging()` uses `min_level=20` (INFO).

### redis-py 7.x — Sync vs Async Methods

redis-py 7.x **separated sync and async APIs**. Many methods that were previously async are now sync in the `Redis` client:

**Sync methods** (do NOT use `await`):
- `xadd()`
- `xreadgroup()`
- `xack()`
- `xgroup_create()`

**Async methods** (use `await`):
- `aclose()` — close the connection
- Any method on `redis.asyncio.Redis` (the async client class)

The `AgentWorker` base class uses `redis.Redis` (sync client) for stream operations:

```python
self.redis_client = redis.from_url(settings.redis.url, decode_responses=True)
# xadd, xreadgroup, xack are all sync — no await
```

### OpenTelemetry SDK API

In `opentelemetry-sdk` ≥1.28.0, tracing components moved to submodules:

```python
# ❌ Wrong
from opentelemetry import trace
resource = trace.Resource.create({"service.name": "my-service"})
provider = trace.TracerProvider(resource=resource)

# ✅ Correct
from opentelemetry.sdk.trace import Resource, TracerProvider
resource = Resource.create({"service.name": "my-service"})
provider = TracerProvider(resource=resource)
```

### Pydantic Settings Nested Env Vars

For nested settings (e.g., `settings.redis.url`), Pydantic Settings requires an explicit `env_nested_delimiter` in `SettingsConfigDict`:

```python
model_config = SettingsConfigDict(
    env_nested_delimiter="__",
)
```

This allows environment variables like `REDIS__URL=value` to set `settings.redis.url`.

Without this, nested settings only accept env vars matching the full attribute path literally (e.g., `REDIS_URL` would not populate `settings.redis.url`).

### Hatchling Package Discovery

When building packages with hatchling, the `packages` argument in `[tool.hatch.build.targets.wheel]` must explicitly list packages because hatchling cannot infer them from an `src/` layout:

```toml
[tool.hatch.build.targets.wheel]
packages = ["app"]
```

Without this, you'll see: `ValueError: Unable to determine which files to ship`.

### OpenAI Agents SDK

The `openai-agents` SDK (`agents` package) provides:

- `Agent` class — LLM agent with tool calling
- `@function_tool` decorator — marks functions as tools for the agent
- `agent.run(user_message)` — runs the agent with a user message

```python
from agents import Agent, function_tool

@function_tool
def my_tool(arg: str) -> str:
    """Tool description for the LLM."""
    return result

agent = Agent(
    name="my_agent",
    instructions="You are a helpful agent...",
    tools=[my_tool],
)

response = await agent.run("user message here")
```

The returned `response` is an agent response object. Access the text via `str(response)` or `.output`.
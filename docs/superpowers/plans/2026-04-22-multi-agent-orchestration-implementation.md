# Multi-Agent Orchestration System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete multi-agent orchestration system with LLM-powered routing, Redis Streams async task processing, Central MCP Gateway, and OpenTelemetry observability.

**Architecture:** Monolithic orchestrator service that receives REST requests, routes via LLM to specialized agent workers, which use tools via a central FastMCP gateway. Redis Streams handles async task dispatch. PostgreSQL stores persistent memory.

**Tech Stack:** Python 3.13, UV, FastAPI 0.128.0, OpenAI Agents SDK v0.7.0, FastMCP v3.2.4, Redis, PostgreSQL, Meilisearch, OpenTelemetry, Docker Compose

---

## Phase 1: Foundation (Scaffold)

### Task 1: Create Project Structure

**Files:**
- Create: `services/__init__.py`
- Create: `services/orchestrator/pyproject.toml`
- Create: `services/orchestrator/app/__init__.py`
- Create: `services/orchestrator/app/config.py`
- Create: `services/orchestrator/app/main.py`
- Create: `services/orchestrator/app/api/__init__.py`
- Create: `services/orchestrator/app/api/routes/__init__.py`
- Create: `services/orchestrator/app/api/routes/health.py`
- Create: `services/orchestrator/app/core/__init__.py`
- Create: `services/orchestrator/app/db/__init__.py`
- Create: `services/orchestrator/app/observability/__init__.py`
- Create: `services/orchestrator/tests/__init__.py`
- Create: `services/orchestrator/Dockerfile`
- Create: `services/orchestrator/.dockerignore`
- Create: `services/agents/base/pyproject.toml`
- Create: `services/agents/base/app/__init__.py`
- Create: `services/agents/base/app/worker.py`
- Create: `services/agents/base/app/config.py`
- Create: `services/agents/base/tests/__init__.py`
- Create: `services/agents/base/Dockerfile`
- Create: `services/agents/file_agent/pyproject.toml`
- Create: `services/agents/file_agent/app/__init__.py`
- Create: `services/agents/file_agent/app/agent.py`
- Create: `services/agents/file_agent/tests/__init__.py`
- Create: `services/agents/file_agent/Dockerfile`
- Create: `services/mcp_gateway/pyproject.toml`
- Create: `services/mcp_gateway/app/__init__.py`
- Create: `services/mcp_gateway/app/server.py`
- Create: `services/mcp_gateway/app/tool_registry.py`
- Create: `services/mcp_gateway/app/config.py`
- Create: `services/mcp_gateway/mcp_servers/__init__.py`
- Create: `services/mcp_gateway/mcp_servers/file_tools/__init__.py`
- Create: `services/mcp_gateway/mcp_servers/file_tools/server.py`
- Create: `services/mcp_gateway/tests/__init__.py`
- Create: `services/mcp_gateway/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create root workspace pyproject.toml**

Create: `pyproject.toml`
```toml
[tool.uv.workspace]
members = [
    "services/orchestrator",
    "services/agents/base",
    "services/agents/file_agent",
    "services/mcp_gateway",
]

[tool.pytest.ini_options]
testpaths = ["services"]
python_files = ["test_*.py", "*_test.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py313"
line-length = 100
```

- [ ] **Step 2: Create orchestrator pyproject.toml**

Create: `services/orchestrator/pyproject.toml`
```toml
[project]
name = "orchestrator"
version = "0.1.0"
description = "Multi-agent orchestration service"
requires-python = ">=3.13"
dependencies = [
    "fastapi==0.128.0",
    "uvicorn[standard]==0.34.0",
    "pydantic==2.10.6",
    "pydantic-settings==2.8.1",
    "python-dotenv==1.1.0",
    "redis==5.4.1",
    "asyncpg==0.30.0",
    "sqlalchemy[asyncio]==2.0.36",
    "structlog==25.1.0",
    "opentelemetry-api==1.30.0",
    "opentelemetry-sdk==1.30.0",
    "opentelemetry-exporter-otlp==1.30.0",
    "opentelemetry-instrumentation-fastapi==0.51b0",
    "opentelemetry-instrumentation-redis==0.51b0",
    "openai-agents-sdk==0.7.0",
    "httpx==0.28.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Create .env.example**

Create: `.env.example`
```env
# Orchestrator
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
REDIS_HOST=redis
REDIS_PORT=6379
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/orchestrator
LLM_API_BASE=http://vllm:8001/v1
LLM_MODEL=your-model-name
LLM_API_KEY=sk-...

# MCP Gateway
MCP_GATEWAY_PORT=8002

# Meilisearch
MEILISEARCH_HOST=http://meilisearch:7700
MEILISEARCH_MASTER_KEY=your_master_key

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_SERVICE_NAME=orchestrator
```

- [ ] **Step 4: Create Docker Compose**

Create: `docker-compose.yml`
```yaml
services:
  orchestrator:
    build:
      context: ./services/orchestrator
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - ../../.env.example
    environment:
      - REDIS_HOST=redis
      - DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/orchestrator
    depends_on:
      - redis
      - postgres
    volumes:
      - ./services/orchestrator:/app

  agent_file:
    build:
      context: ./services/agents/file_agent
      dockerfile: Dockerfile
    env_file:
      - ../../.env.example
    environment:
      - MCP_GATEWAY_URL=http://mcp_gateway:8002
      - REDIS_HOST=redis
    depends_on:
      - mcp_gateway
      - redis

  mcp_gateway:
    build:
      context: ./services/mcp_gateway
      dockerfile: Dockerfile
    ports:
      - "8002:8002"
    env_file:
      - ../../.env.example
    environment:
      - REDIS_HOST=redis
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=orchestrator
    volumes:
      - postgres_data:/var/lib/postgresql/data

  meilisearch:
    image: getmeili/meilisearch:v1.6
    ports:
      - "7700:7700"
    environment:
      - MEILI_MASTER_KEY=your_master_key

  jaeger:
    image: jaegertracing/all-in-one:1.52
    ports:
      - "16686:16686"
      - "4317:4317"
      - "4318:4318"

volumes:
  postgres_data:
```

- [ ] **Step 5: Create orchestrator config**

Create: `services/orchestrator/app/config.py`
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/orchestrator"

    # LLM
    llm_api_base: str = "http://localhost:8001/v1"
    llm_model: str = "your-model-name"
    llm_api_key: str = ""
    llm_timeout: int = 60

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "orchestrator"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Create orchestrator main FastAPI app**

Create: `services/orchestrator/app/main.py`
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import health
from app.observability.tracing import setup_tracing
from app.observability.logging import setup_logging
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Multi-Agent Orchestrator",
    description="LLM-powered task routing and agent orchestration",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_logging()
setup_tracing(app)


@app.get("/")
async def root():
    return {"status": "running", "service": "orchestrator"}


app.include_router(health.router, prefix="/api/v1", tags=["health"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
```

- [ ] **Step 7: Create health routes**

Create: `services/orchestrator/app/api/routes/health.py`
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.config import Settings, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    redis: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", service="orchestrator")


@router.get("/ready", response_model=ReadyResponse)
async def readiness_check(settings: Settings = Depends(get_settings)):
    redis_status = "unknown"
    db_status = "unknown"

    try:
        import redis.asyncio as redis
        r = redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}")
        await r.ping()
        redis_status = "connected"
        await r.aclose()
    except Exception:
        redis_status = "disconnected"

    return ReadyResponse(status="ready", redis=redis_status, database=db_status)
```

- [ ] **Step 8: Create observability tracing module**

Create: `services/orchestrator/app/observability/tracing.py`
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from app.config import get_settings


def setup_tracing(app):
    settings = get_settings()

    resource = Resource.create({
        "service.name": settings.otel_service_name,
    })

    provider = TracerProvider(resource=resource)

    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )

    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    return trace.get_tracer(settings.otel_service_name)
```

- [ ] **Step 9: Create observability logging module**

Create: `services/orchestrator/app/observability/logging.py`
```python
import structlog
from structlog.types import EventDict, Processor
from typing import Any
import logging


def add_trace_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        event_dict["trace_id"] = format(span.get_span_context().trace_id, "032x")
    return event_dict


def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            add_trace_id,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
```

- [ ] **Step 10: Create orchestrator Dockerfile**

Create: `services/orchestrator/Dockerfile`
```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app ./app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "app.main"]
```

- [ ] **Step 11: Create orchestrator .dockerignore**

Create: `services/orchestrator/.dockerignore`
```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
.venv/
venv/
.env
.git
.gitignore
README.md
tests/
```

- [ ] **Step 12: Create agents base pyproject.toml**

Create: `services/agents/base/pyproject.toml`
```toml
[project]
name = "agent-base"
version = "0.1.0"
description = "Base agent worker framework"
requires-python = ">=3.13"
dependencies = [
    "redis==5.4.1",
    "structlog==25.1.0",
    "opentelemetry-api==1.30.0",
    "opentelemetry-sdk==1.30.0",
    "opentelemetry-exporter-otlp==1.30.0",
    "openai-agents-sdk==0.7.0",
    "httpx==0.28.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 13: Create agents base config**

Create: `services/agents/base/app/config.py`
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    mcp_gateway_url: str = "http://localhost:8002"

    llm_api_base: str = "http://localhost:8001/v1"
    llm_model: str = "your-model-name"
    llm_api_key: str = ""
    llm_timeout: int = 60

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agent"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 14: Create agents base worker**

Create: `services/agents/base/app/worker.py`
```python
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import redis.asyncio as redis
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

from app.config import get_settings


class AgentWorker(ABC):
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.settings = get_settings()
        self.redis: Optional[redis.Redis] = None
        self.tracer = self._setup_tracing()
        self._running = False

    def _setup_tracing(self):
        resource = Resource.create({
            "service.name": f"{self.settings.otel_service_name}-{self.agent_name}",
        })
        provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(
            endpoint=self.settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)
        return trace.get_tracer(f"{self.settings.otel_service_name}-{self.agent_name}")

    async def connect(self):
        self.redis = redis.from_url(
            f"redis://{self.settings.redis_host}:{self.settings.redis_port}/{self.settings.redis_db}"
        )

    async def disconnect(self):
        if self.redis:
            await self.redis.aclose()

    @abstractmethod
    async def process_task(self, task: dict) -> dict:
        pass

    async def run(self):
        await self.connect()
        self._running = True

        stream_key = f"stream:agent:{self.agent_name}"
        consumer_group = f"cg:{self.agent_name}"
        consumer_name = f"consumer-{self.agent_name}-{id(self)}"

        try:
            await self.redis.xgroup_create(stream_key, consumer_group, id="0", mkstream=True)
        except redis.ResponseError:
            pass

        while self._running:
            try:
                messages = await self.redis.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream_key: ">"},
                    count=1,
                    block=5000,
                )

                for stream, entries in messages:
                    for message_id, fields in entries:
                        task = {k.decode("utf-8"): v.decode("utf-8") for k, v in fields.items()}
                        task["message_id"] = message_id.decode("utf-8")

                        with self.tracer.start_as_current_span("process_task") as span:
                            span.set_attribute("task.id", task.get("task_id", ""))
                            span.set_attribute("agent.name", self.agent_name)

                            try:
                                result = await self.process_task(task)
                                result["status"] = "completed"
                            except Exception as e:
                                result = {
                                    "status": "failed",
                                    "error": str(e),
                                }
                                span.record_exception(e)

                            result["agent_name"] = self.agent_name
                            result["trace_id"] = format(span.get_span_context().trace_id, "032x")

                            response_key = f"response:{task.get('task_id', message_id.decode('utf-8'))}"
                            await self.redis.set(
                                response_key,
                                json.dumps(result),
                                ex=3600,
                            )

                            await self.redis.xdel(stream_key, message_id)

            except Exception as e:
                await asyncio.sleep(1)

    def stop(self):
        self._running = False
```

- [ ] **Step 15: Create agents base Dockerfile**

Create: `services/agents/base/Dockerfile`
```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app ./app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "-m", "app"]
```

- [ ] **Step 16: Create file_agent pyproject.toml**

Create: `services/agents/file_agent/pyproject.toml`
```toml
[project]
name = "file-agent"
version = "0.1.0"
description = "File operations agent"
requires-python = ">=3.13"
dependencies = [
    "agent-base @ file:///app/packages/agent-base",
    "openai-agents-sdk==0.7.0",
    "httpx==0.28.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 17: Create file_agent agent**

Create: `services/agents/file_agent/app/agent.py`
```python
import asyncio
from app.worker import AgentWorker


class FileAgent(AgentWorker):
    def __init__(self):
        super().__init__("file_agent")
        self.capabilities = ["file_read", "file_write", "directory_list"]

    async def process_task(self, task: dict) -> dict:
        prompt = task.get("prompt", "")
        session_id = task.get("session_id", "")

        with self.tracer.start_as_current_span("file_agent_reasoning"):
            await asyncio.sleep(0.1)

            result_content = f"File agent processed: {prompt[:50]}..."

            return {
                "session_id": session_id,
                "result": {
                    "content": result_content,
                    "tools_used": [],
                },
            }


async def main():
    agent = FileAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 18: Create file_agent Dockerfile**

Create: `services/agents/file_agent/Dockerfile`
```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app ./app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "-m", "app.agent"]
```

- [ ] **Step 19: Create mcp_gateway pyproject.toml**

Create: `services/mcp_gateway/pyproject.toml`
```toml
[project]
name = "mcp-gateway"
version = "0.1.0"
description = "Central MCP Gateway for tool access"
requires-python = ">=3.13"
dependencies = [
    "fastapi==0.128.0",
    "uvicorn[standard]==0.34.0",
    "pydantic==2.10.6",
    "pydantic-settings==2.8.1",
    "fastmcp==3.2.4",
    "structlog==25.1.0",
    "redis==5.4.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 20: Create mcp_gateway config**

Create: `services/mcp_gateway/app/config.py`
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_gateway_port: int = 8002
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 21: Create mcp_gateway tool_registry**

Create: `services/mcp_gateway/app/tool_registry.py`
```python
from typing import TypedDict


class ToolDefinition(TypedDict):
    name: str
    description: str
    input_schema: dict
    mcp_server: str


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition):
    TOOL_REGISTRY[tool["name"]] = tool


def get_tool(name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[ToolDefinition]:
    return list(TOOL_REGISTRY.values())


def register_file_tools():
    register_tool({
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer", "default": 100},
            },
            "required": ["path"],
        },
        "mcp_server": "file_tools",
    })

    register_tool({
        "name": "list_directory",
        "description": "List contents of a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
        "mcp_server": "file_tools",
    })
```

- [ ] **Step 22: Create mcp_gateway server**

Create: `services/mcp_gateway/app/server.py`
```python
from fastapi import FastAPI
from fastmcp import FastMCP
from app.config import get_settings
from app.tool_registry import (
    list_tools,
    get_tool,
    register_file_tools,
)
from app.mcp_servers.file_tools.server import mcp as file_tools_mcp

settings = get_settings()

app = FastAPI(title="MCP Gateway")

register_file_tools()

mcp = FastMCP("gateway")
mcp.add_server(file_tools_mcp)


@app.get("/tools")
async def get_tools():
    return {"tools": list_tools()}


@app.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    tool = get_tool(tool_name)
    if not tool:
        return {"error": "Tool not found"}, 404
    return {"tool": tool}


@mcp.tool()
async def gateway_tool(name: str, arguments: dict) -> str:
    tool = get_tool(name)
    if not tool:
        raise ValueError(f"Unknown tool: {name}")
    return f"Tool {name} called with {arguments}"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.mcp_gateway_port)
```

- [ ] **Step 23: Create file_tools MCP server**

Create: `services/mcp_gateway/mcp_servers/file_tools/server.py`
```python
from fastmcp import FastMCP
import os

mcp = FastMCP("file_tools")


@mcp.tool()
async def read_file(path: str, max_lines: int = 100) -> str:
    """Read contents of a file."""
    if not os.path.exists(path):
        return f"Error: File not found: {path}"

    with open(path) as f:
        lines = f.readlines()[:max_lines]
    return "".join(lines)


@mcp.tool()
async def list_directory(path: str) -> str:
    """List contents of a directory."""
    if not os.path.exists(path):
        return f"Error: Directory not found: {path}"

    if not os.path.isdir(path):
        return f"Error: Not a directory: {path}"

    entries = os.listdir(path)
    return "\n".join(sorted(entries))
```

- [ ] **Step 24: Create mcp_gateway Dockerfile**

Create: `services/mcp_gateway/Dockerfile`
```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app ./app
COPY mcp_servers ./mcp_servers

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["uv", "run", "python", "-m", "app.server"]
```

- [ ] **Step 25: Commit Phase 1**

```bash
git add services/ docker-compose.yml .env.example pyproject.toml
git commit -m "feat: add multi-agent orchestration scaffold

Phase 1 - Foundation:
- Project structure with services/orchestrator, services/agents, services/mcp_gateway
- Docker Compose with all services (redis, postgres, meilisearch, jaeger)
- FastAPI orchestrator with health/ready endpoints
- OpenTelemetry tracing and structlog logging
- Base agent worker class
- File agent skeleton
- Central MCP gateway with file_tools server
- UV workspace configuration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Core Orchestration

### Task 2: Session Management

**Files:**
- Modify: `services/orchestrator/app/main.py:1-35`
- Create: `services/orchestrator/app/core/session.py`
- Create: `services/orchestrator/app/api/routes/sessions.py`
- Create: `services/orchestrator/tests/test_session.py`

- [ ] **Step 1: Create session manager**

Create: `services/orchestrator/app/core/session.py`
```python
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import redis.asyncio as redis
from pydantic import BaseModel


class SessionData(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    last_active: datetime
    context: dict = {}


class SessionManager:
    def __init__(self, redis_client: redis.Redis, ttl_hours: int = 24):
        self.redis = redis_client
        self.ttl = timedelta(hours=ttl_hours)

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def create(self, user_id: str, metadata: Optional[dict] = None) -> SessionData:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_active=now,
            context={"conversation_history": [], "metadata": metadata or {}},
        )

        await self.redis.set(
            self._key(session_id),
            session.model_dump_json(),
            ex=int(self.ttl.total_seconds()),
        )

        return session

    async def get(self, session_id: str) -> Optional[SessionData]:
        data = await self.redis.get(self._key(session_id))
        if not data:
            return None
        return SessionData.model_validate_json(data)

    async def update(self, session_id: str, context_update: dict) -> Optional[SessionData]:
        session = await self.get(session_id)
        if not session:
            return None

        session.last_active = datetime.now(timezone.utc)
        session.context.update(context_update)

        await self.redis.set(
            self._key(session_id),
            session.model_dump_json(),
            ex=int(self.ttl.total_seconds()),
        )

        return session

    async def add_message(self, session_id: str, role: str, content: str, agent_name: Optional[str] = None):
        session = await self.get(session_id)
        if not session:
            return None

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if agent_name:
            message["agent_name"] = agent_name

        session.context["conversation_history"].append(message)
        session.last_active = datetime.now(timezone.utc)

        await self.redis.set(
            self._key(session_id),
            session.model_dump_json(),
            ex=int(self.ttl.total_seconds()),
        )

        return session

    async def delete(self, session_id: str) -> bool:
        result = await self.redis.delete(self._key(session_id))
        return result > 0
```

- [ ] **Step 2: Create sessions API routes**

Create: `services/orchestrator/app/api/routes/sessions.py`
```python
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import redis.asyncio as redis

from app.core.session import SessionManager, SessionData
from app.config import get_settings

router = APIRouter()


def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}")


class CreateSessionRequest(BaseModel):
    user_id: str
    metadata: Optional[dict] = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime


@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    redis_client: redis.Redis = Depends(get_redis),
):
    manager = SessionManager(redis_client)
    session = await manager.create(request.user_id, request.metadata)

    return CreateSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.last_active,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    manager = SessionManager(redis_client)
    session = await manager.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        expires_at=session.last_active,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    manager = SessionManager(redis_client)
    deleted = await manager.delete(session_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
```

- [ ] **Step 3: Write session manager tests**

Create: `services/orchestrator/tests/test_session.py`
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.core.session import SessionManager, SessionData


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock()
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def session_manager(mock_redis):
    return SessionManager(mock_redis)


@pytest.mark.asyncio
async def test_create_session(session_manager, mock_redis):
    session = await session_manager.create("user_123", {"language": "en"})

    assert session.user_id == "user_123"
    assert session.session_id.startswith("sess_")
    assert session.context["metadata"]["language"] == "en"
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_found(session_manager, mock_redis):
    session_data = SessionData(
        session_id="sess_abc123",
        user_id="user_123",
        created_at=datetime.now(timezone.utc),
        last_active=datetime.now(timezone.utc),
        context={"conversation_history": []},
    )
    mock_redis.get.return_value = session_data.model_dump_json()

    session = await session_manager.get("sess_abc123")

    assert session is not None
    assert session.session_id == "sess_abc123"


@pytest.mark.asyncio
async def test_get_session_not_found(session_manager, mock_redis):
    mock_redis.get.return_value = None

    session = await session_manager.get("sess_nonexistent")

    assert session is None


@pytest.mark.asyncio
async def test_add_message(session_manager, mock_redis):
    session_data = SessionData(
        session_id="sess_abc123",
        user_id="user_123",
        created_at=datetime.now(timezone.utc),
        last_active=datetime.now(timezone.utc),
        context={"conversation_history": []},
    )
    mock_redis.get.return_value = session_data.model_dump_json()

    updated = await session_manager.add_message("sess_abc123", "user", "Hello")

    assert len(updated.context["conversation_history"]) == 1
    assert updated.context["conversation_history"][0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_delete_session(session_manager, mock_redis):
    result = await session_manager.delete("sess_abc123")

    assert result is True
    mock_redis.delete.assert_called_once()
```

- [ ] **Step 4: Run session tests**

Run: `cd services/orchestrator && uv run pytest tests/test_session.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Update main.py to include sessions router**

Modify: `services/orchestrator/app/main.py`
Add import and include_router:
```python
from app.api.routes import health, sessions
```
Add after health router:
```python
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
```

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator/app/core/session.py
git add services/orchestrator/app/api/routes/sessions.py
git add services/orchestrator/tests/test_session.py
git commit -m "feat: add session management

- SessionManager with Redis backend
- Create, get, delete session endpoints
- Add message to conversation history
- Session TTL (24 hours default)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 3: LLM Router

**Files:**
- Create: `services/orchestrator/app/core/router.py`
- Create: `services/orchestrator/tests/test_router.py`

- [ ] **Step 1: Create LLM router**

Create: `services/orchestrator/app/core/router.py`
```python
import json
from typing import Optional
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from app.config import get_settings


class RoutingDecision(BaseModel):
    agent_name: str
    task_description: str
    priority: str = "normal"
    reasoning: str


@dataclass
class AgentCapability:
    name: str
    description: str
    capabilities: list[str]


class LLMRouter:
    def __init__(self):
        self.settings = get_settings()
        self._agents: list[AgentCapability] = []

    def register_agent(self, agent: AgentCapability):
        self._agents.append(agent)

    def _build_routing_prompt(self, user_message: str, conversation_history: list[dict]) -> str:
        agent_descriptions = "\n".join(
            f"- {a.name}: {a.description} (capabilities: {', '.join(a.capabilities)})"
            for a in self._agents
        )

        history_text = ""
        if conversation_history:
            history_text = "\n\nConversation history:\n" + "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in conversation_history[-5:]
            )

        return f"""You are a task routing system. Given a user message, select the best agent to handle it.

Available agents:
{agent_descriptions}

{history_text}

User message: {user_message}

Respond with JSON containing:
- "agent_name": the name of the agent to handle this
- "task_description": a clear description of what to do
- "priority": "high", "normal", or "low"
- "reasoning": brief explanation of why this agent
"""

    async def route(self, user_message: str, conversation_history: Optional[list[dict]] = None) -> RoutingDecision:
        prompt = self._build_routing_prompt(user_message, conversation_history or [])

        async with httpx.AsyncClient(timeout=self.settings.llm_timeout) as client:
            response = await client.post(
                f"{self.settings.llm_api_base}/chat/completions",
                json={
                    "model": self.settings.llm_model,
                    "messages": [
                        {"role": "system", "content": "You are a JSON-only response system."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"} if self.settings.llm_api_key else {},
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            try:
                result = json.loads(content)
                return RoutingDecision(
                    agent_name=result["agent_name"],
                    task_description=result["task_description"],
                    priority=result.get("priority", "normal"),
                    reasoning=result.get("reasoning", ""),
                )
            except (json.JSONDecodeError, KeyError) as e:
                return RoutingDecision(
                    agent_name="file_agent",
                    task_description=user_message,
                    priority="normal",
                    reasoning=f"Fallback due to parse error: {e}",
                )
```

- [ ] **Step 2: Write router tests**

Create: `services/orchestrator/tests/test_router.py`
```python
import pytest
from unittest.mock import AsyncMock, patch
from app.core.router import LLMRouter, AgentCapability, RoutingDecision


@pytest.fixture
def router():
    return LLMRouter()


@pytest.fixture
def sample_agents():
    return [
        AgentCapability(
            name="file_agent",
            description="Handles file operations",
            capabilities=["file_read", "file_write"],
        ),
        AgentCapability(
            name="code_agent",
            description="Handles code execution",
            capabilities=["code_execute", "code_review"],
        ),
    ]


def test_register_agent(router, sample_agents):
    for agent in sample_agents:
        router.register_agent(agent)

    assert len(router._agents) == 2
    assert router._agents[0].name == "file_agent"


def test_build_routing_prompt(router, sample_agents):
    for agent in sample_agents:
        router.register_agent(agent)

    prompt = router._build_routing_prompt("Read my file", [])

    assert "file_agent" in prompt
    assert "code_agent" in prompt
    assert "Read my file" in prompt


@pytest.mark.asyncio
async def test_route_success(router, sample_agents):
    for agent in sample_agents:
        router.register_agent(agent)

    mock_response = {
        "choices": [
            {
                "message": {
                    "content": '{"agent_name": "file_agent", "task_description": "read file", "priority": "normal", "reasoning": "test"}'
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = AsyncMock()

        decision = await router.route("Read my file")

        assert isinstance(decision, RoutingDecision)
        assert decision.agent_name == "file_agent"
        assert decision.task_description == "read file"


@pytest.mark.asyncio
async def test_route_fallback_on_error(router, sample_agents):
    for agent in sample_agents:
        router.register_agent(agent)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.raise_for_status.side_effect = Exception("API Error")

        decision = await router.route("Read my file")

        assert decision.agent_name == "file_agent"
        assert "Fallback" in decision.reasoning
```

- [ ] **Step 3: Run router tests**

Run: `cd services/orchestrator && uv run pytest tests/test_router.py -v`
Expected: PASS (4 tests)

- [ ] **Step 4: Commit**

```bash
git add services/orchestrator/app/core/router.py services/orchestrator/tests/test_router.py
git commit -m "feat: add LLM-powered task router

- LLMRouter uses LLM to select best agent based on capabilities
- AgentCapability dataclass for registration
- Fallback to first registered agent on error
- Structured output with agent_name, task_description, priority

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 4: Task Dispatcher (Redis Streams)

**Files:**
- Create: `services/orchestrator/app/core/dispatcher.py`
- Create: `services/orchestrator/tests/test_dispatcher.py`

- [ ] **Step 1: Create task dispatcher**

Create: `services/orchestrator/app/core/dispatcher.py`
```python
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis


class TaskDispatcher:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def _stream_key(self, agent_name: str) -> str:
        return f"stream:agent:{agent_name}"

    async def dispatch(
        self,
        agent_name: str,
        user_id: str,
        session_id: str,
        prompt: str,
        context: Optional[dict] = None,
        priority: str = "normal",
    ) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        message = {
            "task_id": task_id,
            "agent_name": agent_name,
            "user_id": user_id,
            "session_id": session_id,
            "prompt": prompt,
            "context": json.dumps(context or {}),
            "priority": priority,
            "created_at": now,
        }

        stream_key = self._stream_key(agent_name)
        await self.redis.xadd(stream_key, message)

        return task_id

    async def get_result(self, task_id: str) -> Optional[dict]:
        response_key = f"response:{task_id}"
        data = await self.redis.get(response_key)
        if not data:
            return None
        return json.loads(data)

    async def wait_for_result(self, task_id: str, timeout_seconds: int = 30) -> Optional[dict]:
        import asyncio

        start = datetime.now(timezone.utc)
        while (datetime.now(timezone.utc) - start).total_seconds() < timeout_seconds:
            result = await self.get_result(task_id)
            if result:
                return result
            await asyncio.sleep(0.5)
        return None
```

- [ ] **Step 2: Write dispatcher tests**

Create: `services/orchestrator/tests/test_dispatcher.py`
```python
import pytest
from unittest.mock import AsyncMock
from app.core.dispatcher import TaskDispatcher


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.xadd = AsyncMock(return_value="msg_id_123")
    redis.get = AsyncMock()
    return redis


@pytest.fixture
def dispatcher(mock_redis):
    return TaskDispatcher(mock_redis)


@pytest.mark.asyncio
async def test_dispatch(dispatcher, mock_redis):
    task_id = await dispatcher.dispatch(
        agent_name="file_agent",
        user_id="user_123",
        session_id="sess_abc",
        prompt="Read the file",
    )

    assert task_id.startswith("task_")
    mock_redis.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_get_result_found(dispatcher, mock_redis):
    mock_redis.get.return_value = '{"status": "completed", "result": {"content": "ok"}}'

    result = await dispatcher.get_result("task_123")

    assert result["status"] == "completed"
    assert result["result"]["content"] == "ok"


@pytest.mark.asyncio
async def test_get_result_not_found(dispatcher, mock_redis):
    mock_redis.get.return_value = None

    result = await dispatcher.get_result("task_nonexistent")

    assert result is None
```

- [ ] **Step 3: Run dispatcher tests**

Run: `cd services/orchestrator && uv run pytest tests/test_dispatcher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add services/orchestrator/app/core/dispatcher.py services/orchestrator/tests/test_dispatcher.py
git commit -m "feat: add Redis Streams task dispatcher

- dispatch() sends tasks to agent-specific streams
- get_result() retrieves task results from Redis
- wait_for_result() polls until result available

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 5: Rate Limiter

**Files:**
- Create: `services/orchestrator/app/core/rate_limiter.py`
- Create: `services/orchestrator/tests/test_rate_limiter.py`

- [ ] **Step 1: Create rate limiter**

Create: `services/orchestrator/app/core/rate_limiter.py`
```python
import time
from typing import Optional

import redis.asyncio as redis


class RateLimiter:
    def __init__(
        self,
        redis_client: redis.Redis,
        per_user_limit: int = 60,
        per_endpoint_limit: int = 100,
        global_limit: int = 1000,
        window_seconds: int = 60,
    ):
        self.redis = redis_client
        self.per_user_limit = per_user_limit
        self.per_endpoint_limit = per_endpoint_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds

    def _user_key(self, user_id: str) -> str:
        return f"ratelimit:user:{user_id}"

    def _endpoint_key(self, endpoint: str) -> str:
        return f"ratelimit:endpoint:{endpoint}"

    def _global_key(self) -> str:
        return "ratelimit:global"

    async def check(self, user_id: str, endpoint: str) -> tuple[bool, Optional[int]]:
        now = time.time()
        window_start = now - self.window_seconds

        pipe = self.redis.pipeline()

        pipe.zremrangebyscore(self._user_key(user_id), 0, window_start)
        pipe.zcard(self._user_key(user_id))
        pipe.zremrangebyscore(self._endpoint_key(endpoint), 0, window_start)
        pipe.zcard(self._endpoint_key(endpoint))
        pipe.zremrangebyscore(self._global_key(), 0, window_start)
        pipe.zcard(self._global_key())

        results = await pipe.execute()
        user_count = results[1]
        endpoint_count = results[3]
        global_count = results[5]

        if user_count >= self.per_user_limit:
            return False, self.per_user_limit

        if endpoint_count >= self.per_endpoint_limit:
            return False, self.per_endpoint_limit

        if global_count >= self.global_limit:
            return False, self.global_limit

        pipe = self.redis.pipeline()
        pipe.zadd(self._user_key(user_id), {str(now): now})
        pipe.zadd(self._endpoint_key(endpoint), {str(now): now})
        pipe.zadd(self._global_key(), {str(now): now})

        pipe.expire(self._user_key(user_id), self.window_seconds)
        pipe.expire(self._endpoint_key(endpoint), self.window_seconds)
        pipe.expire(self._global_key(), self.window_seconds)

        await pipe.execute()

        return True, None
```

- [ ] **Step 2: Write rate limiter tests**

Create: `services/orchestrator/tests/test_rate_limiter.py`
```python
import pytest
from unittest.mock import AsyncMock
from app.core.rate_limiter import RateLimiter


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, 0, 0, 0, 0, 0])
    pipe.zadd = AsyncMock()
    pipe.expire = AsyncMock()
    redis.pipeline.return_value = pipe
    return redis


@pytest.fixture
def rate_limiter(mock_redis):
    return RateLimiter(mock_redis, per_user_limit=10, per_endpoint_limit=20, global_limit=100)


@pytest.mark.asyncio
async def test_check_allowed(rate_limiter, mock_redis):
    allowed, limit = await rate_limiter.check("user_123", "/api/v1/messages")

    assert allowed is True
    assert limit is None


@pytest.mark.asyncio
async def test_check_user_limit_exceeded(rate_limiter, mock_redis):
    pipe = mock_redis.pipeline.return_value
    pipe.execute = AsyncMock(return_value=[0, 10, 0, 0, 0, 0])

    allowed, limit = await rate_limiter.check("user_123", "/api/v1/messages")

    assert allowed is False
    assert limit == 10


@pytest.mark.asyncio
async def test_check_endpoint_limit_exceeded(rate_limiter, mock_redis):
    pipe = mock_redis.pipeline.return_value
    pipe.execute = AsyncMock(return_value=[0, 0, 0, 20, 0, 0])

    allowed, limit = await rate_limiter.check("user_123", "/api/v1/messages")

    assert allowed is False
    assert limit == 20
```

- [ ] **Step 3: Run rate limiter tests**

Run: `cd services/orchestrator && uv run pytest tests/test_rate_limiter.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add services/orchestrator/app/core/rate_limiter.py services/orchestrator/tests/test_rate_limiter.py
git commit -m "feat: add Redis-based rate limiter

- Sliding window algorithm for per-user, per-endpoint, global limits
- Returns (allowed, limit_exceeded) tuple
- Configurable limits via constructor

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### Task 6: Message Endpoint (Sync Response)

**Files:**
- Create: `services/orchestrator/app/api/routes/messages.py`
- Create: `services/orchestrator/tests/test_messages.py`
- Modify: `services/orchestrator/app/main.py:1-40`

- [ ] **Step 1: Create messages API routes**

Create: `services/orchestrator/app/api/routes/messages.py`
```python
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
import redis.asyncio as redis

from app.core.session import SessionManager
from app.core.router import LLMRouter, AgentCapability
from app.core.dispatcher import TaskDispatcher
from app.core.rate_limiter import RateLimiter
from app.config import get_settings

router = APIRouter()


def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}")


class SendMessageRequest(BaseModel):
    content: str
    attachments: list[str] = []


class MessageResponse(BaseModel):
    message_id: str
    agent_assigned: str
    status: str
    created_at: datetime


class MessageResultResponse(BaseModel):
    message_id: str
    status: str
    content: Optional[str] = None
    agent_name: Optional[str] = None
    tools_used: list[str] = []
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class MessageListResponse(BaseModel):
    messages: list[dict]


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    redis_client: redis.Redis = Depends(get_redis),
):
    session_manager = SessionManager(redis_client)
    session = await session_manager.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rate_limiter = RateLimiter(redis_client)
    allowed, limit = await rate_limiter.check(session.user_id, "/sessions/messages")
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {limit} per minute")

    router_instance = LLMRouter()
    router_instance.register_agent(AgentCapability(
        name="file_agent",
        description="Handles file operations",
        capabilities=["file_read", "file_write"],
    ))

    decision = await router_instance.route(
        request.content,
        session.context.get("conversation_history", []),
    )

    dispatcher = TaskDispatcher(redis_client)
    task_id = await dispatcher.dispatch(
        agent_name=decision.agent_name,
        user_id=session.user_id,
        session_id=session_id,
        prompt=decision.task_description,
        context={"conversation_history": session.context.get("conversation_history", [])},
        priority=decision.priority,
    )

    await session_manager.add_message(session_id, "user", request.content)

    return MessageResponse(
        message_id=task_id,
        agent_assigned=decision.agent_name,
        status="processing",
        created_at=datetime.now(timezone.utc),
    )


@router.get("/sessions/{session_id}/messages/{message_id}", response_model=MessageResultResponse)
async def get_message_result(
    session_id: str,
    message_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    session_manager = SessionManager(redis_client)
    session = await session_manager.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    dispatcher = TaskDispatcher(redis_client)
    result = await dispatcher.get_result(message_id)

    if not result:
        return MessageResultResponse(
            message_id=message_id,
            status="processing",
        )

    return MessageResultResponse(
        message_id=message_id,
        status=result.get("status", "completed"),
        content=result.get("result", {}).get("content") if result.get("result") else None,
        agent_name=result.get("agent_name"),
        tools_used=result.get("result", {}).get("tools_used", []) if result.get("result") else [],
        completed_at=datetime.now(timezone.utc),
        error=result.get("error"),
    )


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_conversation_history(
    session_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    session_manager = SessionManager(redis_client)
    session = await session_manager.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return MessageListResponse(
        messages=session.context.get("conversation_history", []),
    )
```

- [ ] **Step 2: Write messages tests**

Create: `services/orchestrator/tests/test_messages.py`
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.xadd = AsyncMock(return_value="msg_123")
    return redis


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.redis_host = "localhost"
    settings.redis_port = 6379
    settings.redis_db = 0
    settings.llm_api_base = "http://localhost:8001/v1"
    settings.llm_model = "test"
    settings.llm_api_key = ""
    settings.llm_timeout = 60
    return settings


@pytest.fixture
def mock_router():
    from app.core.router import RoutingDecision
    return RoutingDecision(
        agent_name="file_agent",
        task_description="test task",
        priority="normal",
        reasoning="test",
    )
```

- [ ] **Step 3: Commit Phase 2**

```bash
git add services/orchestrator/app/core/ services/orchestrator/app/api/routes/sessions.py services/orchestrator/app/api/routes/messages.py services/orchestrator/tests/
git commit -m "feat: complete core orchestration layer

- Session management with Redis backend
- LLM-powered task router with agent capability registration
- Redis Streams task dispatcher
- Redis sliding window rate limiter
- Message endpoint with async task dispatch
- All endpoints with tests

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Agent Workers

### Task 7: File Agent with Real Tool Integration

**Files:**
- Modify: `services/agents/file_agent/app/agent.py`

- [ ] **Step 1: Update file_agent to use actual tools**

Modify: `services/agents/file_agent/app/agent.py`
```python
import asyncio
import json
from agents import Agent, function_tool
from app.worker import AgentWorker
from app.config import get_settings


def create_file_tools():
    @function_tool
    def read_file(path: str, max_lines: int = 100) -> str:
        """Read contents of a file."""
        try:
            with open(path) as f:
                lines = f.readlines()[:max_lines]
            return "".join(lines)
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"

    @function_tool
    def list_directory(path: str = ".") -> str:
        """List contents of a directory."""
        import os
        try:
            entries = os.listdir(path)
            return "\n".join(sorted(entries))
        except FileNotFoundError:
            return f"Error: Directory not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"

    return [read_file, list_directory]


class FileAgent(AgentWorker):
    def __init__(self):
        super().__init__("file_agent")
        self.capabilities = ["file_read", "file_write", "directory_list"]
        self.settings = get_settings()

        file_tools = create_file_tools()
        self.agent = Agent(
            name="FileAgent",
            instructions="You are a file operations agent. Help users read and manage files.",
            tools=file_tools,
        )

    async def process_task(self, task: dict) -> dict:
        prompt = task.get("prompt", "")
        session_id = task.get("session_id", "")
        context = json.loads(task.get("context", "{}"))
        history = context.get("conversation_history", [])

        history_messages = []
        for msg in history:
            history_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        history_messages.append({"role": "user", "content": prompt})

        with self.tracer.start_as_current_span("file_agent_execution"):
            response = await self.agent.run("\n".join(history_messages))

            return {
                "session_id": session_id,
                "result": {
                    "content": response.content[-1].text if response.content else "No response",
                    "tools_used": [],
                },
            }


async def main():
    agent = FileAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Update file_agent pyproject.toml for agents SDK**

Modify: `services/agents/file_agent/pyproject.toml`
```toml
[project]
name = "file-agent"
version = "0.1.0"
description = "File operations agent"
requires-python = ">=3.13"
dependencies = [
    "agent-base @ file:///app/packages/agent-base",
    "openai-agents-sdk==0.7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Commit**

```bash
git add services/agents/file_agent/
git commit -m "feat: implement file agent with OpenAI Agents SDK

- Uses Agents SDK function_tool for file operations
- read_file and list_directory tools
- Traced execution with OpenTelemetry

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: MCP Gateway

### Task 8: MCP Gateway Tool Execution

**Files:**
- Modify: `services/mcp_gateway/app/server.py`
- Modify: `services/mcp_gateway/app/tool_registry.py`

- [ ] **Step 1: Update tool registry with execution method**

Modify: `services/mcp_gateway/app/tool_registry.py`
```python
from typing import TypedDict, Callable, Any


class ToolDefinition(TypedDict):
    name: str
    description: str
    input_schema: dict
    mcp_server: str


TOOL_REGISTRY: dict[str, ToolDefinition] = {}
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {}


def register_tool(tool: ToolDefinition, handler: Callable[..., Any] = None):
    TOOL_REGISTRY[tool["name"]] = tool
    if handler:
        TOOL_HANDLERS[tool["name"]] = handler


def get_tool(name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[ToolDefinition]:
    return list(TOOL_REGISTRY.values())


async def execute_tool(name: str, arguments: dict) -> Any:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"No handler for tool: {name}")
    return await handler(**arguments)


def register_file_tools():
    import os

    async def read_file_handler(path: str, max_lines: int = 100) -> str:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        with open(path) as f:
            lines = f.readlines()[:max_lines]
        return "".join(lines)

    async def list_directory_handler(path: str = ".") -> str:
        if not os.path.exists(path):
            return f"Error: Directory not found: {path}"
        entries = os.listdir(path)
        return "\n".join(sorted(entries))

    register_tool({
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer", "default": 100},
            },
            "required": ["path"],
        },
        "mcp_server": "file_tools",
    }, read_file_handler)

    register_tool({
        "name": "list_directory",
        "description": "List contents of a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
        "mcp_server": "file_tools",
    }, list_directory_handler)
```

- [ ] **Step 2: Update MCP gateway server with execution endpoint**

Modify: `services/mcp_gateway/app/server.py`
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from app.config import get_settings
from app.tool_registry import (
    list_tools,
    get_tool,
    register_file_tools,
    execute_tool,
)

settings = get_settings()

app = FastAPI(title="MCP Gateway")

register_file_tools()


class ToolExecutionRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


class ToolExecutionResponse(BaseModel):
    result: Any


@app.get("/tools")
async def get_tools():
    return {"tools": list_tools()}


@app.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    tool = get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"tool": tool}


@app.post("/tools/execute", response_model=ToolExecutionResponse)
async def execute_tool_endpoint(request: ToolExecutionRequest):
    try:
        result = await execute_tool(request.tool_name, request.arguments)
        return ToolExecutionResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.mcp_gateway_port)
```

- [ ] **Step 3: Commit Phase 4**

```bash
git add services/mcp_gateway/
git commit -m "feat: complete MCP gateway with tool execution

- Tool registry with handlers for execution
- POST /tools/execute endpoint
- File tools registered at startup

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Observability Dashboard

### Task 9: Metrics Exposition

**Files:**
- Create: `services/orchestrator/app/observability/metrics.py`

- [ ] **Step 1: Create metrics module**

Create: `services/orchestrator/app/observability/metrics.py`
```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response

REQUEST_COUNT = Counter(
    "orchestrator_requests_total",
    "Total requests by endpoint",
    ["endpoint", "method", "status"],
)

ACTIVE_REQUESTS = Gauge(
    "orchestrator_requests_active",
    "Currently processing requests",
)

AGENT_TASK_COUNT = Counter(
    "agent_tasks_total",
    "Tasks processed by agent",
    ["agent_name", "status"],
)

AGENT_TASK_DURATION = Histogram(
    "agent_tasks_duration_seconds",
    "Task processing time",
    ["agent_name"],
)

MCP_TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    "Tool invocations",
    ["tool_name", "status"],
)

MCP_TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    "Tool execution time",
    ["tool_name"],
)

ACTIVE_SESSIONS = Gauge(
    "session_active",
    "Active sessions count",
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/app/observability/metrics.py
git commit -m "feat: add Prometheus metrics for observability dashboard

- Request counts, active requests gauge
- Agent task counts and duration histograms
- MCP tool call counts and duration
- Active sessions gauge
- /metrics endpoint for Prometheus scraping

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Production Hardening

### Task 10: PostgreSQL Schema and Migrations

**Files:**
- Create: `services/orchestrator/app/db/models.py`
- Create: `services/orchestrator/app/db/repositories.py`
- Create: `services/orchestrator/alembic.ini`
- Create: `services/orchestrator/alembic/`

- [ ] **Step 1: Create database models**

Create: `services/orchestrator/app/db/models.py`
```python
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=AgentStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    default_agent: Mapped[str] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Create repositories**

Create: `services/orchestrator/app/db/repositories.py`
```python
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import get_settings
from app.db.models import Base, Agent, UserPreferences, Conversation, Message


engine = create_async_engine(get_settings().database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str, description: str, capabilities: list[str]) -> Agent:
        agent = Agent(name=name, description=description, capabilities=capabilities)
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def get_by_name(self, name: str) -> Optional[Agent]:
        result = await self.session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Agent]:
        result = await self.session.execute(
            select(Agent).where(Agent.status == "active")
        )
        return list(result.scalars().all())

    async def update_status(self, name: str, status: str) -> Optional[Agent]:
        agent = await self.get_by_name(name)
        if agent:
            agent.status = status
            agent.updated_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(agent)
        return agent


class UserPreferencesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: str) -> UserPreferences:
        result = await self.session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = UserPreferences(user_id=user_id)
            self.session.add(prefs)
            await self.session.commit()
            await self.session.refresh(prefs)

        return prefs

    async def update(self, user_id: str, **kwargs) -> Optional[UserPreferences]:
        prefs = await self.get_or_create(user_id)
        for key, value in kwargs.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        prefs.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(prefs)
        return prefs
```

- [ ] **Step 3: Commit Phase 6**

```bash
git add services/orchestrator/app/db/
git commit -m "feat: add PostgreSQL models and repositories

- SQLAlchemy async models for conversations, messages, agents, preferences
- Async session factory
- AgentRepository and UserPreferencesRepository
- Alembic ready structure

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Implementation Complete

### Summary

| Phase | Tasks | Status |
|-------|-------|--------|
| 1: Foundation | 1-25 | Scaffold, Docker, observability |
| 2: Core Orchestration | 2.1-2.6 | Session, router, dispatcher, rate limiter, messages |
| 3: Agent Workers | 3.1 | File agent with Agents SDK |
| 4: MCP Gateway | 4.1-4.2 | Tool registry, execution endpoint |
| 5: Observability | 5.1 | Prometheus metrics |
| 6: Production | 6.1 | PostgreSQL models and repositories |

### Run All Tests

```bash
cd services/orchestrator && uv run pytest tests/ -v --tb=short
cd services/agents/base && uv run pytest tests/ -v --tb=short
```

### Build and Run

```bash
docker compose build
docker compose up -d
```

### Verify Health

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
curl http://localhost:8002/tools
```

---

*Plan created: 2026-04-22*
*Based on design: docs/superpowers/specs/2026-04-22-multi-agent-system-design-v1.1.md*
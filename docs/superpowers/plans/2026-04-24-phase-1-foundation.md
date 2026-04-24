# Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the shared foundations every later phase depends on — UV workspace, local infra stack (Postgres/Redis/Meilisearch/Jaeger/Prometheus/Grafana), the `openagent-common` Python package with core Pydantic schemas and Protocols, OTEL tracing, structlog logging, and Alembic-managed Postgres schema (initial `agents` table). No application code yet.

**Architecture:** Monorepo with UV workspace rooted at the repo root; each service is a workspace member under `services/`. `services/common` is the first member and holds cross-service primitives (schemas, Protocols, telemetry, logging, shared DB models). Infra runs locally via Docker Compose; Python code runs on the host for fast iteration. Observability is OTEL-first — structlog correlates log records to the active OTEL span.

**Tech Stack:**
- Python 3.13, UV package manager
- Pydantic 2.x, structlog, OpenTelemetry SDK (OTLP/gRPC exporter to Jaeger)
- SQLAlchemy 2.x (async) + asyncpg, Alembic
- Postgres 16-alpine, Redis 7-alpine, Meilisearch v1.6, Jaeger all-in-one, Prometheus, Grafana
- pytest + pytest-asyncio + pytest-cov
- ruff (lint + format), mypy (type check)

---

## File Structure

Files created in this phase, grouped by purpose:

**Repo root (new files):**
- `.python-version` — pins CPython 3.13
- `.gitignore` — Python/UV/IDE/env patterns
- `.env.example` — env var template
- `pyproject.toml` — UV workspace root + dev tool config (ruff, pytest, mypy)
- `README.md` — **modify** (exists); add developer runbook section
- `docker-compose.yml` — infra services (Postgres, Redis, Meili, Jaeger, Prometheus, Grafana)
- `ops/prometheus/prometheus.yml` — scrape config
- `ops/grafana/provisioning/datasources/datasources.yaml` — Prometheus + Jaeger datasources
- `ops/grafana/provisioning/dashboards/dashboards.yaml` — placeholder provider (real dashboards land in Phase 5)

**`services/common` (new package — src-layout):**
- `services/common/pyproject.toml` — package metadata + deps
- `services/common/src/openagent_common/__init__.py` — package marker
- `services/common/src/openagent_common/schemas.py` — `Task`, `Result`, `AgentEvent`, `ToolCall`, `GuardrailDecision`
- `services/common/src/openagent_common/interfaces.py` — `BaseAgent`, `Guardrail`, `LLMClient`, `MCPClient`, `SessionStore` Protocols
- `services/common/src/openagent_common/telemetry.py` — `configure_tracing(service_name)` + tracer helpers
- `services/common/src/openagent_common/logging.py` — `configure_logging()` + OTEL-aware structlog processor
- `services/common/src/openagent_common/db/__init__.py`
- `services/common/src/openagent_common/db/models.py` — SQLAlchemy `Base` + `Agent` model
- `services/common/alembic.ini` — Alembic config
- `services/common/alembic/env.py` — Alembic runtime
- `services/common/alembic/script.py.mako` — migration template
- `services/common/alembic/versions/0001_initial.py` — creates `agents`
- `services/common/tests/__init__.py`
- `services/common/tests/conftest.py` — fixtures (in-memory OTEL exporter, async DB session)
- `services/common/tests/test_schemas.py`
- `services/common/tests/test_interfaces.py`
- `services/common/tests/test_telemetry.py`
- `services/common/tests/test_logging.py`
- `services/common/tests/test_models.py`
- `services/common/tests/integration/test_alembic.py` — real-Postgres migration test

**Smoke-test suite (new):**
- `tests/smoke/__init__.py`
- `tests/smoke/test_infra.py` — compose-stack reachability checks

**Scope boundary notes:**
- `services/orchestrator`, `services/agents/*`, `services/mcp_gateway` are **not** touched in Phase 1. They get their own packages in Phase 2+.
- Only the `agents` table is created in Phase 1. Other tables (`messages`, `agent_runs`, `agent_run_events`, `audit_*`, `api_keys`) are created in the phase that introduces their owning code.
- No Grafana dashboards imported. Phase 5 owns dashboards.

---

## Pre-flight — Open a Real Terminal Once

Before you start, confirm you have these CLIs on PATH. On Windows use PowerShell; on macOS/Linux use bash. Commands in this plan use forward slashes and POSIX-style invocations; translate trivially if needed.

```
uv --version        # expect: uv 0.4+ (any 0.4.x or newer)
docker --version    # expect: Docker 24+
docker compose version  # expect: v2.x
python --version    # not strictly required — uv will manage 3.13
```

If any is missing, install before proceeding.

---

## Task 1 — Repo Scaffold and Toolchain

**Files:**
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `pyproject.toml`

- [ ] **Step 1: Write `.python-version`**

Create `.python-version` with content:

```
3.13
```

- [ ] **Step 2: Write `.gitignore`**

Create `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/
.mypy_cache/
.ruff_cache/

# UV
.venv/
*.pyc

# Env
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Alembic local override (we commit versions/)
# (nothing to ignore here right now)

# Docker volumes (only applies if local mounts are made by dev)
/tmp/
```

- [ ] **Step 3: Write `.env.example`**

Create `.env.example`:

```
# Postgres
POSTGRES_USER=openagent
POSTGRES_PASSWORD=openagent
POSTGRES_DB=openagent
DATABASE_URL=postgresql+asyncpg://openagent:openagent@localhost:5432/openagent

# Redis
REDIS_URL=redis://localhost:6379/0

# Meilisearch
MEILI_MASTER_KEY=masterKey
MEILI_URL=http://localhost:7700

# OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAMESPACE=openagent

# Logging
LOG_LEVEL=INFO
```

- [ ] **Step 4: Write root `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "openagent-workspace"
version = "0.0.0"
description = "OpenAgent monorepo root (UV workspace)"
requires-python = ">=3.13"

[tool.uv.workspace]
members = ["services/common"]

[tool.uv]
dev-dependencies = [
  "pytest>=8.1",
  "pytest-asyncio>=0.23",
  "pytest-cov>=4.1",
  "ruff>=0.4",
  "mypy>=1.10",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N"]
ignore = ["E501"]  # line length handled by formatter

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["services/common/tests", "tests"]
markers = [
  "integration: requires docker-compose stack (opt in with -m integration)",
]
addopts = "-ra --strict-markers"

[tool.mypy]
python_version = "3.13"
strict = true
ignore_missing_imports = true
```

- [ ] **Step 5: Verify `uv sync`**

Run:
```
uv sync
```

Expected: creates `.venv/`, installs dev deps, no errors. `uv.lock` file is written.

- [ ] **Step 6: Commit**

```
git add .python-version .gitignore .env.example pyproject.toml uv.lock
git commit -m "chore: initialize UV workspace and dev toolchain (ruff, pytest, mypy)"
```

---

## Task 2 — `services/common` Package Scaffold

**Files:**
- Create: `services/common/pyproject.toml`
- Create: `services/common/src/openagent_common/__init__.py`
- Create: `services/common/src/openagent_common/py.typed`
- Create: `services/common/tests/__init__.py`
- Create: `services/common/tests/conftest.py`

- [ ] **Step 1: Create directory tree**

Run:
```
mkdir -p services/common/src/openagent_common
mkdir -p services/common/tests
```

- [ ] **Step 2: Write `services/common/pyproject.toml`**

Create `services/common/pyproject.toml`:

```toml
[project]
name = "openagent-common"
version = "0.1.0"
description = "Shared primitives (schemas, Protocols, telemetry, logging, DB models) for OpenAgent services"
requires-python = ">=3.13"
dependencies = [
  "pydantic>=2.7",
  "structlog>=24.1",
  "opentelemetry-api>=1.25",
  "opentelemetry-sdk>=1.25",
  "opentelemetry-exporter-otlp-proto-grpc>=1.25",
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "alembic>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/openagent_common"]
```

- [ ] **Step 3: Write package marker files**

Create `services/common/src/openagent_common/__init__.py`:

```python
"""OpenAgent shared primitives."""

__version__ = "0.1.0"
```

Create empty `services/common/src/openagent_common/py.typed`:

```
```

Create empty `services/common/tests/__init__.py`:

```
```

- [ ] **Step 4: Write `services/common/tests/conftest.py`**

Create `services/common/tests/conftest.py`:

```python
"""Shared test fixtures for openagent-common."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
    """Fresh in-memory OTEL exporter bound to a fresh TracerProvider.

    Resets the global tracer provider for the test, so tests that assert
    on emitted spans are isolated.
    """
    exporter = InMemorySpanExporter()
    resource = Resource.create(
        {"service.name": "test", "service.namespace": "openagent"}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter
```

- [ ] **Step 5: Update root workspace and sync**

The root `pyproject.toml` already lists `services/common` in `[tool.uv.workspace]`. Run:

```
uv sync
```

Expected: `openagent-common` resolves, `.venv/` now contains its deps (pydantic, structlog, otel, sqlalchemy, asyncpg, alembic).

- [ ] **Step 6: Commit**

```
git add services/common uv.lock
git commit -m "feat(common): scaffold openagent-common workspace package"
```

---

## Task 3 — `schemas.py` Pydantic Core Models (TDD)

**Files:**
- Create: `services/common/src/openagent_common/schemas.py`
- Test: `services/common/tests/test_schemas.py`

These are the cross-service value types the umbrella spec §5 defines. Everything else builds on them.

- [ ] **Step 1: Write the failing tests**

Create `services/common/tests/test_schemas.py`:

```python
"""Tests for openagent_common.schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from openagent_common.schemas import (
    AgentEvent,
    GuardrailDecision,
    Result,
    Task,
    ToolCall,
)


class TestTask:
    def test_minimal_fields(self) -> None:
        t = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
        assert t.task_id == "t1"
        assert t.session_id == "s1"
        assert t.user_id == "u1"
        assert t.prompt == "hi"
        assert t.context == {}
        assert t.metadata == {}

    def test_round_trip(self) -> None:
        t = Task(
            task_id="t1",
            session_id="s1",
            user_id="u1",
            prompt="hi",
            context={"history": [1, 2, 3]},
            metadata={"priority": "high"},
        )
        restored = Task.model_validate(t.model_dump())
        assert restored == t

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            Task(session_id="s1", user_id="u1", prompt="hi")  # type: ignore[call-arg]


class TestToolCall:
    def test_result_and_error_nullable(self) -> None:
        tc = ToolCall(name="read_file", arguments={"path": "/tmp/a"})
        assert tc.result is None
        assert tc.error is None

    def test_with_result(self) -> None:
        tc = ToolCall(
            name="read_file",
            arguments={"path": "/tmp/a"},
            result={"bytes": 42},
        )
        assert tc.result == {"bytes": 42}


class TestAgentEvent:
    @pytest.mark.parametrize(
        "kind",
        [
            "thinking",
            "tool_call",
            "tool_result",
            "partial_content",
            "dispatched",
            "done",
            "error",
        ],
    )
    def test_accepts_known_kinds(self, kind: str) -> None:
        e = AgentEvent(kind=kind)
        assert e.kind == kind
        assert e.data == {}

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            AgentEvent(kind="totally_made_up")  # type: ignore[arg-type]


class TestResult:
    def test_completed_result(self) -> None:
        r = Result(task_id="t1", status="completed", content="final answer")
        assert r.status == "completed"
        assert r.tool_calls == []
        assert r.tokens == {}
        assert r.error is None

    def test_failed_result_with_error(self) -> None:
        r = Result(task_id="t1", status="failed", error="boom")
        assert r.status == "failed"
        assert r.content is None

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            Result(task_id="t1", status="maybe")  # type: ignore[arg-type]


class TestGuardrailDecision:
    @pytest.mark.parametrize("verdict", ["allowed", "flagged", "blocked"])
    def test_accepts_known_verdicts(self, verdict: str) -> None:
        d = GuardrailDecision(verdict=verdict)
        assert d.verdict == verdict

    def test_rejects_unknown_verdict(self) -> None:
        with pytest.raises(ValidationError):
            GuardrailDecision(verdict="yes")  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        d = GuardrailDecision(verdict="allowed")
        assert d.reason == ""
        assert d.name == ""
        assert d.metadata == {}
```

- [ ] **Step 2: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/test_schemas.py -v
```

Expected: `ImportError` / collection error because `openagent_common.schemas` does not exist yet.

- [ ] **Step 3: Implement `schemas.py`**

Create `services/common/src/openagent_common/schemas.py`:

```python
"""Core Pydantic models shared across OpenAgent services.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §5.1
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentEventKind = Literal[
    "thinking",
    "tool_call",
    "tool_result",
    "partial_content",
    "dispatched",
    "done",
    "error",
]

ResultStatus = Literal["completed", "failed"]

GuardrailVerdict = Literal["allowed", "flagged", "blocked"]


class Task(BaseModel):
    """A unit of work dispatched to an agent."""

    task_id: str
    session_id: str
    user_id: str
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A single tool invocation within an agent run."""

    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentEvent(BaseModel):
    """One event emitted by an agent during streaming execution."""

    kind: AgentEventKind
    data: dict[str, Any] = Field(default_factory=dict)


class Result(BaseModel):
    """The terminal output of an agent run."""

    task_id: str
    status: ResultStatus
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error: str | None = None
    tokens: dict[str, int] = Field(default_factory=dict)


class GuardrailDecision(BaseModel):
    """Decision emitted by a Guardrail.check() call."""

    verdict: GuardrailVerdict
    reason: str = ""
    name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
uv run pytest services/common/tests/test_schemas.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add services/common/src/openagent_common/schemas.py services/common/tests/test_schemas.py
git commit -m "feat(common): add core Pydantic schemas (Task, Result, AgentEvent, ToolCall, GuardrailDecision)"
```

---

## Task 4 — `interfaces.py` Protocols (TDD)

**Files:**
- Create: `services/common/src/openagent_common/interfaces.py`
- Test: `services/common/tests/test_interfaces.py`

These Protocols are the seams every agent, guardrail, and client implementation conforms to. Umbrella §5.1 defines `BaseAgent`; the rest are inferred from the dependency list in §5.2.

- [ ] **Step 1: Write the failing tests**

Create `services/common/tests/test_interfaces.py`:

```python
"""Tests for openagent_common.interfaces Protocols.

Protocols can't be "unit tested" directly. Instead we verify each Protocol
can be satisfied by a minimal fake at runtime via @runtime_checkable.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from openagent_common.interfaces import (
    BaseAgent,
    Guardrail,
    LLMClient,
    MCPClient,
    SessionStore,
)
from openagent_common.schemas import (
    AgentEvent,
    GuardrailDecision,
    Result,
    Task,
)


class FakeAgent:
    name = "fake"

    async def run(self, task: Task) -> Result:
        return Result(task_id=task.task_id, status="completed", content="ok")

    async def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(kind="done")


class FakeGuardrail:
    name = "fake_input"
    kind = "input"

    async def check(self, payload: dict) -> GuardrailDecision:
        return GuardrailDecision(verdict="allowed", name=self.name)


class FakeLLMClient:
    model_name = "fake-model"

    async def chat_completion(
        self, messages: list[dict], **kwargs: object
    ) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}


class FakeMCPClient:
    async def call_tool(self, name: str, arguments: dict) -> dict:
        return {"ok": True}

    async def list_tools(self) -> list[dict]:
        return []


class FakeSessionStore:
    async def load(self, session_id: str) -> dict | None:
        return None

    async def save(
        self, session_id: str, data: dict, ttl_seconds: int = 86400
    ) -> None:
        return None

    async def delete(self, session_id: str) -> None:
        return None


def test_fake_agent_conforms_to_baseagent() -> None:
    assert isinstance(FakeAgent(), BaseAgent)


def test_fake_guardrail_conforms_to_guardrail() -> None:
    assert isinstance(FakeGuardrail(), Guardrail)


def test_fake_llm_client_conforms() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)


def test_fake_mcp_client_conforms() -> None:
    assert isinstance(FakeMCPClient(), MCPClient)


def test_fake_session_store_conforms() -> None:
    assert isinstance(FakeSessionStore(), SessionStore)


@pytest.mark.asyncio
async def test_fake_agent_run_returns_result() -> None:
    agent = FakeAgent()
    task = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
    result = await agent.run(task)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_fake_agent_run_streamed_yields_events() -> None:
    agent = FakeAgent()
    task = Task(task_id="t1", session_id="s1", user_id="u1", prompt="hi")
    events = [e async for e in agent.run_streamed(task)]
    assert len(events) == 1
    assert events[0].kind == "done"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/test_interfaces.py -v
```

Expected: `ImportError` (`openagent_common.interfaces` missing).

- [ ] **Step 3: Implement `interfaces.py`**

Create `services/common/src/openagent_common/interfaces.py`:

```python
"""Protocol definitions for OpenAgent dependencies.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §5
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from .schemas import AgentEvent, GuardrailDecision, Result, Task


@runtime_checkable
class BaseAgent(Protocol):
    """The universal agent interface. Every production and testbed agent
    implementation satisfies this Protocol."""

    name: str

    async def run(self, task: Task) -> Result:
        ...

    def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]:
        ...


@runtime_checkable
class Guardrail(Protocol):
    """A pluggable check that runs at one of the orchestrator/agent/gateway
    lifecycle points. See 2026-04-23-guardrails.md for scope."""

    name: str
    kind: str  # "input" | "tool" | "output"

    async def check(self, payload: dict) -> GuardrailDecision:
        ...


@runtime_checkable
class LLMClient(Protocol):
    """OpenAI-compatible chat completion client (points at vLLM in prod)."""

    model_name: str

    async def chat_completion(
        self, messages: list[dict], **kwargs: Any
    ) -> dict:
        ...


@runtime_checkable
class MCPClient(Protocol):
    """Client for the central MCP Gateway."""

    async def call_tool(self, name: str, arguments: dict) -> dict:
        ...

    async def list_tools(self) -> list[dict]:
        ...


@runtime_checkable
class SessionStore(Protocol):
    """Redis-backed session persistence interface."""

    async def load(self, session_id: str) -> dict | None:
        ...

    async def save(
        self, session_id: str, data: dict, ttl_seconds: int = 86400
    ) -> None:
        ...

    async def delete(self, session_id: str) -> None:
        ...
```

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
uv run pytest services/common/tests/test_interfaces.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add services/common/src/openagent_common/interfaces.py services/common/tests/test_interfaces.py
git commit -m "feat(common): add BaseAgent, Guardrail, LLMClient, MCPClient, SessionStore Protocols"
```

---

## Task 5 — `telemetry.py` OTEL Bootstrap (TDD)

**Files:**
- Create: `services/common/src/openagent_common/telemetry.py`
- Test: `services/common/tests/test_telemetry.py`

Umbrella §11 mandates OTEL-first observability with spans carrying `service.name` / `service.namespace`. `configure_tracing(name)` is the single entry point every service calls at startup.

- [ ] **Step 1: Write the failing tests**

Create `services/common/tests/test_telemetry.py`:

```python
"""Tests for openagent_common.telemetry."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from openagent_common.telemetry import build_tracer_provider, configure_tracing


def test_build_tracer_provider_sets_resource_attributes() -> None:
    provider = build_tracer_provider("orchestrator")
    assert isinstance(provider, TracerProvider)
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "orchestrator"
    assert attrs["service.namespace"] == "openagent"


def test_build_tracer_provider_honors_custom_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAMESPACE", "openagent-test")
    provider = build_tracer_provider("file_agent")
    assert provider.resource.attributes["service.namespace"] == "openagent-test"


def test_configure_tracing_installs_global_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point at localhost; exporter is lazy, doesn't try to connect at init.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    tracer = configure_tracing("mcp_gateway")
    assert tracer is not None
    provider = trace.get_tracer_provider()
    # The installed provider should carry our service.name
    assert provider.resource.attributes["service.name"] == "mcp_gateway"  # type: ignore[attr-defined]


def test_span_emission_with_in_memory_exporter(otel_exporter) -> None:
    # otel_exporter fixture already installs a provider with service.name=test
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("my-span") as span:
        span.set_attribute("foo", "bar")

    spans = otel_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "my-span"
    assert spans[0].attributes["foo"] == "bar"
    assert spans[0].resource.attributes["service.name"] == "test"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/test_telemetry.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `telemetry.py`**

Create `services/common/src/openagent_common/telemetry.py`:

```python
"""OTEL bootstrap for OpenAgent services.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §11

Usage (at service startup):

    from openagent_common.telemetry import configure_tracing
    tracer = configure_tracing("orchestrator")

The exporter is OTLP/gRPC pointed at the endpoint in
OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4317). Jaeger's
all-in-one image accepts OTLP on that port when COLLECTOR_OTLP_ENABLED=true.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

_DEFAULT_ENDPOINT = "http://localhost:4317"


def build_tracer_provider(
    service_name: str,
    *,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Construct (but do NOT install) a TracerProvider for `service_name`.

    Separated from `configure_tracing` so tests can inspect / inject an
    exporter without mutating the global tracer provider.
    """
    namespace = os.environ.get("OTEL_SERVICE_NAMESPACE", "openagent")
    resource = Resource.create(
        {"service.name": service_name, "service.namespace": namespace}
    )
    provider = TracerProvider(resource=resource)
    if exporter is None:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT
        )
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def configure_tracing(service_name: str) -> trace.Tracer:
    """Install a global TracerProvider for `service_name` and return a
    tracer named after the service. Call once at service startup."""
    provider = build_tracer_provider(service_name)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
```

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
uv run pytest services/common/tests/test_telemetry.py -v
```

Expected: all 4 tests pass. `test_configure_tracing_installs_global_provider` uses the real OTLP exporter but does not flush during the test, so no network call is attempted.

- [ ] **Step 5: Commit**

```
git add services/common/src/openagent_common/telemetry.py services/common/tests/test_telemetry.py
git commit -m "feat(common): add configure_tracing OTEL bootstrap"
```

---

## Task 6 — `logging.py` structlog + OTEL Correlation (TDD)

**Files:**
- Create: `services/common/src/openagent_common/logging.py`
- Test: `services/common/tests/test_logging.py`

Umbrella §11.4: every log line carries `trace_id`, `session_id`, `user_id`. We handle `trace_id` automatically via an OTEL-aware processor. `session_id` / `user_id` come from context vars that callers bind.

- [ ] **Step 1: Write the failing tests**

Create `services/common/tests/test_logging.py`:

```python
"""Tests for openagent_common.logging."""

from __future__ import annotations

import json

import pytest
import structlog
from opentelemetry import trace

from openagent_common.logging import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    """Ensure each test starts from a clean structlog config."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def test_json_output_has_core_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", user_id="u1")

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["event"] == "hello"
    assert record["user_id"] == "u1"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_contextvars_bind_persists(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(session_id="sess_1", user_id="u1")
    log = structlog.get_logger("test")
    log.info("hi")

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert record["session_id"] == "sess_1"
    assert record["user_id"] == "u1"
    structlog.contextvars.clear_contextvars()


def test_trace_id_injected_when_inside_span(
    capsys: pytest.CaptureFixture[str],
    otel_exporter,
) -> None:
    configure_logging(level="INFO")
    tracer = trace.get_tracer("test")
    log = structlog.get_logger("test")

    with tracer.start_as_current_span("outer"):
        log.info("in-span")

    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert "trace_id" in record
    assert "span_id" in record
    assert len(record["trace_id"]) == 32
    assert len(record["span_id"]) == 16


def test_trace_id_absent_outside_span(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No otel fixture — no active span.
    configure_logging(level="INFO")
    log = structlog.get_logger("test")
    log.info("no-span")
    captured = capsys.readouterr()
    record = json.loads(captured.out.strip().splitlines()[-1])
    assert "trace_id" not in record
```

- [ ] **Step 2: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/test_logging.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `logging.py`**

Create `services/common/src/openagent_common/logging.py`:

```python
"""structlog configuration with OTEL trace-id correlation.

Reference: docs/superpowers/specs/2026-04-23-multi-agent-system-design-v1.2.md §11.4

Usage (at service startup, AFTER configure_tracing):

    from openagent_common.logging import configure_logging
    configure_logging(level="INFO")
    log = structlog.get_logger("orchestrator")
    log.info("service_started")

Bind contextvars at per-request scope:

    structlog.contextvars.bind_contextvars(session_id=..., user_id=...)
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from opentelemetry import trace


def _add_otel_context(
    logger: object, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor that copies the active OTEL span's IDs into the
    event dict. If no span is active, adds nothing."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    # INVALID_SPAN has trace_id=0 / span_id=0
    if ctx.trace_id != 0:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Install a JSON-emitting structlog config that correlates log records
    to the active OTEL span.

    Safe to call more than once (structlog caches on first use; later calls
    still apply to newly-created loggers)."""
    level_int = getattr(logging, level.upper(), logging.INFO)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_otel_context,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
```

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
uv run pytest services/common/tests/test_logging.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```
git add services/common/src/openagent_common/logging.py services/common/tests/test_logging.py
git commit -m "feat(common): add structlog config with OTEL trace-id correlation"
```

---

## Task 7 — Docker Compose Infra Stack

**Files:**
- Create: `docker-compose.yml`
- Create: `ops/prometheus/prometheus.yml`
- Create: `ops/grafana/provisioning/datasources/datasources.yaml`
- Create: `ops/grafana/provisioning/dashboards/dashboards.yaml`
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/test_infra.py`

- [ ] **Step 1: Write the failing smoke tests**

Create `tests/smoke/__init__.py`:

```
```

Create `tests/smoke/test_infra.py`:

```python
"""Smoke tests: infra stack reachability.

Run: `docker compose up -d` first, then:
    uv run pytest tests/smoke -v -m integration
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def test_postgres_port_open() -> None:
    assert _tcp_reachable("localhost", 5432)


def test_redis_port_open() -> None:
    assert _tcp_reachable("localhost", 6379)


def test_meilisearch_health() -> None:
    assert _http_ok("http://localhost:7700/health")


def test_jaeger_ui() -> None:
    assert _http_ok("http://localhost:16686/")


def test_jaeger_otlp_grpc_port_open() -> None:
    assert _tcp_reachable("localhost", 4317)


def test_prometheus_ready() -> None:
    assert _http_ok("http://localhost:9090/-/ready")


def test_grafana_health() -> None:
    assert _http_ok("http://localhost:3000/api/health")
```

- [ ] **Step 2: Run smoke tests — expect FAIL (no compose yet)**

Run:
```
uv run pytest tests/smoke -v -m integration
```

Expected: all 7 tests fail (assertions fail because nothing is listening).

- [ ] **Step 3: Write `docker-compose.yml`**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: openagent-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: openagent
      POSTGRES_PASSWORD: openagent
      POSTGRES_DB: openagent
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U openagent -d openagent"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: openagent-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  meilisearch:
    image: getmeili/meilisearch:v1.6
    container_name: openagent-meilisearch
    ports:
      - "7700:7700"
    environment:
      MEILI_MASTER_KEY: masterKey
      MEILI_ENV: development
    volumes:
      - meilisearch_data:/meili_data
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:7700/health"]
      interval: 5s
      timeout: 3s
      retries: 10

  jaeger:
    image: jaegertracing/all-in-one:1.55
    container_name: openagent-jaeger
    ports:
      - "16686:16686"  # Web UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: openagent-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./ops/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--web.enable-lifecycle"

  grafana:
    image: grafana/grafana:10.4.0
    container_name: openagent-grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
    volumes:
      - ./ops/grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
      - jaeger

volumes:
  postgres_data:
  redis_data:
  meilisearch_data:
  prometheus_data:
  grafana_data:
```

- [ ] **Step 4: Write `ops/prometheus/prometheus.yml`**

Create `ops/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
```

(Application scrape targets are added in Phase 5 when services expose metrics.)

- [ ] **Step 5: Write Grafana datasource provisioning**

Create `ops/grafana/provisioning/datasources/datasources.yaml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
    editable: false
```

Create `ops/grafana/provisioning/dashboards/dashboards.yaml`:

```yaml
apiVersion: 1
providers:
  - name: openagent
    orgId: 1
    folder: OpenAgent
    type: file
    disableDeletion: false
    allowUiUpdates: false
    options:
      path: /etc/grafana/provisioning/dashboards
```

(Empty directory for now; Phase 5 adds actual dashboard JSON files here.)

- [ ] **Step 6: Bring up the stack**

Run:
```
docker compose up -d
```

Then wait for all services to become healthy:
```
docker compose ps
```

Expected: `postgres`, `redis`, `meilisearch` show `healthy`; `jaeger`, `prometheus`, `grafana` show `running` (they don't define healthchecks but are up).

If anything fails, run `docker compose logs <service>` and fix before proceeding.

- [ ] **Step 7: Run smoke tests — expect PASS**

Run:
```
uv run pytest tests/smoke -v -m integration
```

Expected: all 7 tests pass.

- [ ] **Step 8: Commit**

```
git add docker-compose.yml ops tests/smoke
git commit -m "feat: add Docker Compose infra stack (Postgres, Redis, Meili, Jaeger, Prometheus, Grafana) with smoke tests"
```

---

## Task 8 — SQLAlchemy `Agent` Model (TDD)

**Files:**
- Create: `services/common/src/openagent_common/db/__init__.py`
- Create: `services/common/src/openagent_common/db/models.py`
- Test: `services/common/tests/test_models.py`

Umbrella §9.1 defines the `agents` table. We put the shared schema in `openagent_common.db.models` — see rationale note at the end of this task.

- [ ] **Step 1: Write the failing tests**

Create `services/common/tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/test_models.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement models**

Create `services/common/src/openagent_common/db/__init__.py`:

```python
"""Shared DB schema and Base for OpenAgent services."""

from .models import Agent, Base

__all__ = ["Agent", "Base"]
```

Create `services/common/src/openagent_common/db/models.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
uv run pytest services/common/tests/test_models.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```
git add services/common/src/openagent_common/db services/common/tests/test_models.py
git commit -m "feat(common): add SQLAlchemy Base and Agent model"
```

---

## Task 9 — Alembic Setup + Migration 0001 (TDD with real Postgres)

**Files:**
- Create: `services/common/alembic.ini`
- Create: `services/common/alembic/env.py`
- Create: `services/common/alembic/script.py.mako`
- Create: `services/common/alembic/versions/0001_initial.py`
- Create: `services/common/tests/integration/__init__.py`
- Create: `services/common/tests/integration/test_alembic.py`

**Prerequisite:** Docker Compose stack from Task 7 is running (`docker compose ps` shows Postgres healthy). The integration test connects to real Postgres at `localhost:5432`.

- [ ] **Step 1: Write the failing integration test**

Create `services/common/tests/integration/__init__.py`:

```
```

Create `services/common/tests/integration/test_alembic.py`:

```python
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
```

- [ ] **Step 2: Add `psycopg` to dev deps**

The integration test imports `psycopg` (v3, pure Python). Add to the root `pyproject.toml` `[tool.uv] dev-dependencies` list:

```toml
[tool.uv]
dev-dependencies = [
  "pytest>=8.1",
  "pytest-asyncio>=0.23",
  "pytest-cov>=4.1",
  "ruff>=0.4",
  "mypy>=1.10",
  "psycopg[binary]>=3.1",
]
```

Run:
```
uv sync
```

- [ ] **Step 3: Run tests — expect FAIL**

Run:
```
uv run pytest services/common/tests/integration -v -m integration
```

Expected: collection fails or tests fail — no `alembic.ini` yet.

- [ ] **Step 4: Write `services/common/alembic.ini`**

Create `services/common/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Write `services/common/alembic/env.py`**

Create `services/common/alembic/env.py`:

```python
"""Alembic runtime.

DATABASE_URL is read from env. Accepts both sync and async SQLAlchemy URLs;
we normalize to sync for Alembic operations (Alembic uses sync internally).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from openagent_common.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL env var is required for Alembic")
    # Alembic uses sync drivers; strip asyncpg.
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Note: we depend on `psycopg` (already in dev deps) as the sync driver for Alembic. The normalized URL uses `postgresql+psycopg://`.

- [ ] **Step 6: Write `services/common/alembic/script.py.mako`**

Create `services/common/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Write migration 0001**

Create `services/common/alembic/versions/0001_initial.py`:

```python
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
```

- [ ] **Step 8: Apply and test**

Confirm compose stack is up (from Task 7). Then run:

```
uv run pytest services/common/tests/integration -v -m integration
```

Expected: 3 tests pass (`test_upgrade_creates_agents_table`, `test_downgrade_drops_agents_table`, `test_upgrade_is_idempotent`).

If Alembic can't find `openagent_common` on import, verify `services/common` is in the workspace and `uv sync` has been run since Task 2.

- [ ] **Step 9: Apply migration to the real (non-test) database**

So the dev DB is in the same shape:

```
cd services/common
DATABASE_URL=postgresql+asyncpg://openagent:openagent@localhost:5432/openagent uv run alembic upgrade head
cd ../..
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial: agents table`.

- [ ] **Step 10: Commit**

```
git add services/common/alembic services/common/alembic.ini services/common/tests/integration pyproject.toml uv.lock
git commit -m "feat(common): add Alembic and migration 0001 (agents table)"
```

---

## Task 10 — Update Root `README.md` With Dev Runbook

**Files:**
- Modify: `README.md` (exists at repo root)

- [ ] **Step 1: Read existing README**

Run:
```
cat README.md
```

Note what's there.

- [ ] **Step 2: Replace or append the developer runbook**

Edit `README.md` so it contains (add to it rather than wholesale replacing any existing project description):

```markdown
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
```

- [ ] **Step 3: Commit**

```
git add README.md
git commit -m "docs: add developer quickstart runbook to root README"
```

---

## Task 11 — End-to-End Verification (No New Code)

This task exists to prove Phase 1 works end-to-end before closing the phase.

- [ ] **Step 1: Tear down and rebuild the stack from scratch**

```
docker compose down -v
docker compose up -d
```

Wait ~30 seconds for healthchecks to settle.

- [ ] **Step 2: Run the full test suite**

```
uv run pytest -v
```

Expected: all **unit** tests pass (schemas, interfaces, telemetry, logging, models).

```
uv run pytest -v -m integration
```

Expected: all **integration + smoke** tests pass (Alembic migration, infra reachability — 10 tests total: 3 Alembic + 7 smoke).

- [ ] **Step 3: Manually verify Jaeger receives traces**

Create a tiny one-off script (do **not** commit):

```bash
uv run python -c "
from openagent_common.telemetry import configure_tracing
from openagent_common.logging import configure_logging
import structlog

tracer = configure_tracing('phase1-verify')
configure_logging()
log = structlog.get_logger('verify')

with tracer.start_as_current_span('hello-phase1'):
    log.info('trace emitted', check='ok')

# Force flush
from opentelemetry import trace
trace.get_tracer_provider().shutdown()
print('done')
"
```

Then open `http://localhost:16686`, select service **phase1-verify** in the left dropdown, click **Find Traces**. Expect one trace named `hello-phase1`.

Console output should contain a JSON log line with `trace_id` populated.

- [ ] **Step 4: Apply migrations to the dev DB (if not already)**

```
cd services/common
DATABASE_URL=postgresql+asyncpg://openagent:openagent@localhost:5432/openagent \
  uv run alembic upgrade head
cd ../..
```

Then verify:

```
docker compose exec postgres psql -U openagent -d openagent -c '\dt'
```

Expected: shows `agents` and `alembic_version` tables.

- [ ] **Step 5: Phase-1 close-out commit (optional)**

If anything was tweaked during verification, commit. If not, skip this step.

```
git status
# if clean: nothing to do
# if not:
git commit -am "chore: phase-1 verification tweaks"
```

---

## Phase 1 Done Criteria

All of these must be true before starting Phase 2:

1. `docker compose up -d` brings the full stack healthy on a clean machine.
2. `uv sync` from repo root installs all deps including `openagent-common`.
3. `uv run pytest -v` passes (unit tests — schemas, interfaces, telemetry, logging, models).
4. `uv run pytest -v -m integration` passes (Alembic + infra smoke).
5. A manually emitted span appears in Jaeger UI.
6. A structlog line emitted inside a span carries a non-empty `trace_id`.
7. `agents` and `alembic_version` tables exist in the `openagent` database.
8. `README.md` describes the runbook and someone who has never seen this repo can follow it to a working dev environment.

---

## Self-Review Notes

Before considering this plan final, the author verified:

- **Spec coverage.** Every item in umbrella §18 Phase 1 checklist maps to a task:
  - UV workspace + Docker Compose → Tasks 1, 2, 7
  - `services/common` → Tasks 2, 3, 4
  - OTEL tracing + structlog → Tasks 5, 6
  - Postgres schema + Alembic → Tasks 8, 9
- **Type consistency.** `Task`, `Result`, `AgentEvent`, `ToolCall`, `GuardrailDecision` definitions in Task 3 exactly match the Protocols in Task 4 (which import them). The `Agent` SQLAlchemy model in Task 8 matches the schema in Task 9 migration and the umbrella §9.1 spec table.
- **No placeholders.** No "TBD", "implement later", "add error handling" steps. Every code step contains full code.
- **TDD discipline.** Every code task: write test → run fail → implement → run pass → commit. No "batch tests later."
- **Scope boundary.** No orchestrator, MCP gateway, agent core, auth, rate limiting, Meilisearch indexing, or Grafana dashboards. All of those are other phases.

---

## Next Phase Notes (for the reader, not in this plan)

- **Phase 2** will add `services/mcp_gateway` + the first MCP server (`file_tools`). It depends on `openagent_common.interfaces.MCPClient` shape being stable — which Task 4 locks in.
- **Phase 3** will add `services/agents/base/agent_core_manual.py` (production) and optionally `agent_core_sdk.py` (testbed). The umbrella spec is clear that **production uses the manual core**. The user noted they'll actually *spin up the SDK testbed first* during implementation to explore agent behaviors — that's fine; both variants will exist. The Phase 3 plan will be written against the manual core (the production target) and treat the SDK variant as an opt-in parallel task.
- **Phase 4.5** (Durable Agent Runs) depends on `agent_runs` and `agent_run_events` tables — those are added by Phase 4.5's own migration, not here.

---

*End of Plan*

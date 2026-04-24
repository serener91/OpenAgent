# Multi-Agent Orchestration System Design

**Document Version:** 1.2
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Supersedes:** v1.1 (2026-04-22)

> **⚠️ Version Check Required:** Before implementation, verify the following package versions against their official sources (PyPI, GitHub releases). The versions below were current as of the document date but may have updated since.
>
> | Package | Documented Version | Check At |
> |---------|-------------------|----------|
> | Python | 3.13 | python.org/downloads |
> | openai (Python SDK) | ≥1.50 | pypi.org/project/openai |
> | FastMCP | v3.2.4 | github.com/prefecthq/fastmcp/releases |
> | FastAPI | ≥0.136.0 | pypi.org/project/fastapi |
> | DeepEval | latest | pypi.org/project/deepeval |
> | tenacity | latest | pypi.org/project/tenacity |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Stack](#2-technical-stack)
3. [Architecture Overview](#3-architecture-overview)
4. [Component Responsibilities](#4-component-responsibilities)
5. [The `BaseAgent` Protocol](#5-the-baseagent-protocol)
6. [Orchestrator Design](#6-orchestrator-design)
7. [Sub-agent Dispatch Protocol](#7-sub-agent-dispatch-protocol)
8. [Session Management](#8-session-management)
9. [Agent Registry](#9-agent-registry)
10. [API Design](#10-api-design)
11. [Observability](#11-observability)
12. [Guardrails Overview](#12-guardrails-overview)
13. [Security Overview](#13-security-overview)
14. [Evaluation Overview](#14-evaluation-overview)
15. [Dashboard Overview](#15-dashboard-overview)
16. [Deferred Work (Stubs)](#16-deferred-work-stubs)
17. [Project Structure](#17-project-structure)
18. [Implementation Phases](#18-implementation-phases)
19. [Design Decisions Summary](#19-design-decisions-summary)
20. [Durable Agent Runs Overview](#20-durable-agent-runs-overview)
21. [Changelog](#21-changelog)

---

## 1. Project Overview

### 1.1 Purpose

A standalone multi-agent orchestration system that serves as a workplace AI assistant platform. Users interact with a conversational **orchestrator agent** that delegates work to specialized sub-agents, each equipped with tools via MCP (Model Context Protocol).

### 1.2 Interaction Model

**Claude-Code-style topology.** The user talks to the orchestrator as they would a single conversational assistant. The orchestrator decides when to invoke sub-agents, calls them as tools, and composes the final response. Sub-agents do not talk to each other directly — the orchestrator is the conductor.

### 1.3 Target Users

- Enterprise employees requiring AI assistance for workplace tasks
- External systems (Slack, Teams, internal portals) integrating via REST API
- Frontend developers building chat interfaces on top of the API

### 1.4 Target Scale

| Metric | Value |
|--------|-------|
| Concurrent users | 100+ |
| Concurrent active agents | 20+ |
| Target deployment | On-premise private server, Kubernetes migration path |
| LLM backend | vLLM (OpenAI-compatible, self-hosted) |

---

## 2. Technical Stack

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| Language | Python | 3.13 | Proven; async-first; 3.14 upgrade deferred until there's a reason |
| Package Manager | UV | latest | Fast Rust-based Python package manager |
| LLM Client | `openai` (Python SDK) | ≥1.50 | Direct vLLM API access; no framework lock-in |
| MCP Framework | FastMCP | v3.2.4 | Server + client; centralized tool access |
| LLM Backend | vLLM | — | Self-hosted, OpenAI-compatible |
| Cache / Sessions | Redis | 7-alpine | Stateless sessions, rate limiting, streams, pub/sub |
| Persistent Memory | PostgreSQL | 16-alpine | Agent registry, conversation history, audit log, API keys |
| Semantic Search | Meilisearch | v1.6 | Agent capability discovery, document retrieval |
| API Framework | FastAPI | ≥0.136.0 | Async, OpenAPI generation, SSE support |
| Retries | tenacity | latest | Backoff, jitter, circuit-breaker primitives |
| Evals | DeepEval | latest | Pytest-native LLM evaluation |
| Observability | OpenTelemetry | — | Vendor-neutral distributed tracing |
| Dashboard | Grafana + Prometheus + Jaeger | — | Metrics, alerts, trace drill-down |
| Packaging | Docker Compose → Kubernetes | — | Containerized from day one |

> **Note on framework choice:** We explicitly do **not** use the OpenAI Agents SDK as a runtime dependency for the production path. Rationale: our architecture (multi-process agents, Redis Streams composition, central MCP Gateway) bypasses most of the SDK's value (in-process handoffs, in-process sessions). Rolling our own agent loop (~400 LOC) avoids framework lock-in and matches the grain of our topology. See `2026-04-23-agent-core-manual.md` for the production agent-core design.
>
> A parallel **testbed** variant using OpenAI Agents SDK 0.14 is documented in `2026-04-23-agent-core-sdk.md` for rapid prototyping of agent behaviors, with the understanding that behaviors validated there get re-implemented against the manual loop for production.

---

## 3. Architecture Overview

### 3.1 High-Level Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           External Clients                               │
│        (REST API / Slack / Teams / Web Chat / Custom Frontends)         │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTP/REST + SSE
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             Orchestrator Service (N replicas, stateless)                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │            Orchestrator Agent (runs its own LLM loop)              │ │
│  │                                                                    │ │
│  │   Tools available to orchestrator:                                 │ │
│  │     • discover_agents(intent)  ──► Meilisearch                     │ │
│  │     • dispatch_to_<name>(task, ctx)  ──► Redis Streams             │ │
│  │     • direct tools (memory lookup, user prefs, etc.)  ──► MCP      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Session Manager │ Rate Limiter │ Guardrails (input) │ SSE Streamer     │
└────────┬───────────────────────────┬─────────────────────────────┬──────┘
         │                           │                             │
         ▼                           ▼                             ▼
┌────────────────┐        ┌────────────────────┐       ┌────────────────┐
│     Redis      │        │     PostgreSQL      │       │   Meilisearch  │
│  sessions +    │        │  agent registry +   │       │  agent caps +  │
│  streams +     │        │  conversations +    │       │  documents     │
│  pub/sub       │        │  audit log + keys   │       │                │
└────────┬───────┘        └─────────────────────┘       └────────────────┘
         │
         │ Redis Streams (consumer groups)
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Sub-agent Workers (N)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │  file_agent  │  │ search_agent │  │ <other>_agent│                   │
│  │  (BaseAgent) │  │  (BaseAgent) │  │  (BaseAgent) │                   │
│  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘                   │
└──────────┼─────────────────┼─────────────────┼──────────────────────────┘
           │                 │                 │
           └─────────────────┼─────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │      Central MCP Gateway     │
              │  (tool registry + proxy +    │
              │   per-tool guardrails)       │
              └──────────────┬───────────────┘
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
┌────────────┐        ┌────────────┐         ┌────────────┐
│ FastMCP    │        │ FastMCP    │         │ FastMCP    │
│ file_tools │        │ web_search │         │ <other>    │
└────────────┘        └────────────┘         └────────────┘
```

### 3.2 Request Flow (Happy Path)

1. Client sends `POST /api/v1/sessions/{sid}/messages` with user content
2. Orchestrator input guardrails run (prompt injection, PII, rate limit check)
3. Orchestrator agent loop starts, streams events over SSE to client
4. Agent calls `discover_agents(intent)` → Meilisearch returns top-K candidate sub-agents
5. Agent calls `dispatch_to_file_agent(task, ctx)` → task enqueued on Redis Stream
6. File-agent worker consumes task, runs its own loop, calls MCP tools via Gateway, writes result to response stream
7. Orchestrator's `dispatch_to_*` tool returns the result; agent loop continues
8. Agent emits final response; SSE `done` event closes the stream

### 3.3 Why This Differs From v1.1

| v1.1 design | v1.2 change | Why |
|---|---|---|
| Separate Router + Dispatcher + Aggregator components | Collapsed into the orchestrator agent's tool-calling loop | Simpler; no separate LLM "router" round-trip; matches conversational UX |
| Agents dispatched via explicit routing decision | Agents invoked as tools by the orchestrator agent | User interacts with a single conversational surface |
| Poll `GET /messages/{id}` for results | SSE streaming + polling fallback | 100+ concurrent waiters on polling is wasteful |
| OpenAI Agents SDK as runtime dep | Manual agent loop (production) + SDK variant (testbed) | Avoid framework lock-in; architecture is multi-process, SDK is single-process-native |
| Agent registry split between Postgres and Gateway | Postgres canonical, Redis pub/sub for change notifications | Single source of truth, restart-resilient |
| Orchestrator replication unspecified | Explicitly stateless, N replicas with HPA | 100-user target needs horizontal scale from day one |

---

## 4. Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Orchestrator Service** | Hosts the orchestrator agent. Receives user requests, runs LLM loop, dispatches to sub-agents via Redis Streams, streams results over SSE. Stateless; N replicas. |
| **Orchestrator Agent** | LLM-driven conductor. Uses `discover_agents` + `dispatch_to_*` tools to compose work across sub-agents. Implements `BaseAgent`. |
| **Sub-agent Workers** | One process per agent type. Consume tasks from their Redis Stream consumer group. Execute using `BaseAgent` implementation. Emit results to response stream. |
| **MCP Gateway** | Central proxy for tool access. Tool registry, per-user/per-agent tool access policy, rate limiting, egress control, audit logging. |
| **Redis** | Sessions, rate-limit counters, task streams, agent-registry change pub/sub, guardrail audit stream. |
| **PostgreSQL** | Agent registry (canonical), conversation history, audit log, API keys (hashed), user preferences. |
| **Meilisearch** | Agent capability search (`discover_agents`), document/knowledge-base semantic search for agents. |

---

## 5. The `BaseAgent` Protocol

The system's framework-independence hinges on this protocol. Both the SDK and manual variants implement it; all other code depends only on this interface.

### 5.1 Interface

```python
# services/common/interfaces.py
from typing import Protocol, AsyncIterator
from pydantic import BaseModel

class Task(BaseModel):
    task_id: str
    session_id: str
    user_id: str
    prompt: str
    context: dict                  # conversation history, attachments
    metadata: dict = {}

class ToolCall(BaseModel):
    name: str
    arguments: dict
    result: dict | None = None
    error: str | None = None

class AgentEvent(BaseModel):
    kind: str                      # "thinking" | "tool_call" | "tool_result"
                                   # | "partial_content" | "dispatched" | "done" | "error"
    data: dict

class Result(BaseModel):
    task_id: str
    status: str                    # "completed" | "failed"
    content: str | None
    tool_calls: list[ToolCall] = []
    error: str | None = None
    tokens: dict = {}              # {"prompt": ..., "completion": ...}

class BaseAgent(Protocol):
    name: str
    async def run(self, task: Task) -> Result: ...
    # `run_streamed` is declared plain `def` (not `async def`) so that an
    # async-generator body — `async def run_streamed(...): ... yield ...` —
    # cleanly satisfies the Protocol. Called without `await`; iterated with
    # `async for`. See concrete forms in agent-core-{sdk,manual}.md.
    def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]: ...
```

### 5.2 Dependencies an Agent Receives

```python
class AgentDependencies(BaseModel):
    llm_client: LLMClient                   # OpenAI-compatible client → vLLM
    mcp_client: MCPClient                   # FastMCP client → MCP Gateway
    session_store: SessionStore             # Redis-backed
    guardrails: GuardrailRegistry           # input / tool / output
    tracer: Tracer                          # OTEL
```

Agents receive dependencies via constructor injection. Tests inject fakes. Production wires real clients.

---

## 6. Orchestrator Design

### 6.1 The Orchestrator *is* an Agent

The orchestrator service hosts an `OrchestratorAgent` that implements `BaseAgent`. It differs from sub-agents only in:

- **System prompt** — "You are the conductor. Use `discover_agents` then `dispatch_to_*` to delegate. Compose results for the user."
- **Toolset** — `discover_agents`, `dispatch_to_<name>` (one per registered agent), plus a small set of direct tools (memory lookup, user preferences)
- **Runtime location** — inside the FastAPI process rather than a separate worker

### 6.2 `discover_agents(intent: str) -> list[AgentCandidate]`

- Intent is the user's current sub-goal, extracted by the orchestrator LLM
- Query Meilisearch index `agent_capabilities` for top-K (default K=5) matches
- Returns `[{name, description, score, capabilities}]`
- Keeps the orchestrator system prompt short (no need to inline 20+ agent descriptions)

### 6.3 `dispatch_to_<name>(task, ctx) -> Result`

One tool per registered agent (generated from the Postgres registry on orchestrator startup, refreshed on Redis pub/sub events). Each tool:

1. Generates a `task_id` (UUID)
2. Publishes a message to `stream:agent:<name>` via `XADD`
3. Awaits the response on `stream:agent:<name>:results` filtered by `task_id` (using `XREAD` with `BLOCK` and a timeout)
4. Returns the `Result` (or surfaces timeout/error so the orchestrator LLM can react)

Timeouts are per-dispatch (default 120s, overridable per agent). On timeout, the tool returns an error result — the orchestrator LLM decides whether to retry, fall back, or surface the failure to the user.

### 6.4 SSE Streaming

The orchestrator's `run_streamed` yields `AgentEvent` instances. The HTTP layer serializes each event as an SSE `data:` frame with the event's `kind` as the SSE event name. Clients see:

```
event: thinking
data: {}

event: tool_call
data: {"name": "discover_agents", "arguments": {"intent": "analyze sales report"}}

event: tool_result
data: {"candidates": [{"name": "file_agent", ...}]}

event: dispatched
data: {"agent": "file_agent", "task_id": "..."}

event: partial_content
data: {"delta": "Here's what I found..."}

event: done
data: {"tokens": {"prompt": 1234, "completion": 567}}
```

### 6.5 Replication

- Orchestrator is fully stateless. All per-session state lives in Redis; all persistent state in Postgres.
- Run N replicas behind a load balancer. No session affinity required.
- Kubernetes `Deployment` with `HorizontalPodAutoscaler` keyed on CPU + custom metric `orchestrator_active_sse_streams`.
- Per-replica concurrent-stream cap (default 200); excess requests return `503 Retry-After`.

---

## 7. Sub-agent Dispatch Protocol

### 7.1 Redis Streams Layout

| Stream | Purpose | Consumer |
|---|---|---|
| `stream:agent:<name>` | Incoming tasks for agent `<name>` | Agent worker consumer group `<name>-workers` |
| `stream:agent:<name>:results` | Results for agent `<name>` | Orchestrator replicas (filtered by `task_id`) |
| `stream:agent:<name>:dlq` | Dead-letter: tasks that failed `max_retries` or exceeded `max_processing_time` | Operator-only; alerts fire on non-empty DLQ |

### 7.2 Consumer Groups

- Each agent type runs as N worker replicas. All share the consumer group `<name>-workers`.
- `XREADGROUP` with `BLOCK` + `COUNT 1` for fair dispatch
- `XACK` on success
- `XPENDING` monitored by an orchestrator-side janitor (see §7.4)

### 7.3 Task Message Schema

```json
{
  "task_id": "uuid",
  "session_id": "sess_...",
  "user_id": "user_...",
  "prompt": "string",
  "context": { "history": [...], "attachments": [] },
  "metadata": { "priority": "normal", "trace_id": "..." },
  "enqueued_at": "ISO8601",
  "timeout_s": 120
}
```

### 7.4 Failure Handling (v1.2 baseline)

- **Worker crash mid-task:** message remains in `XPENDING` for its consumer. A janitor running on one orchestrator replica (elected via Redis lock) runs `XAUTOCLAIM` every 30s for messages idle > 60s, resurrecting them to other workers.
- **Retry budget:** task metadata tracks `attempt_count`; after `max_retries` (default 3), janitor moves the message to `stream:agent:<name>:dlq` and publishes a failure result so the orchestrator's awaiting dispatch-tool returns an error.
- **Full DLQ playbook, circuit breakers, per-agent bulkheads** → full treatment deferred to the **Reliability** spec (v1.3). The baseline above is enough to survive normal failures.

### 7.5 Ordering

No cross-session ordering guarantee. Within a session, the orchestrator calls sub-agents sequentially from its agent loop, so ordering emerges from the caller. If later work needs parallel fan-out within a session, the orchestrator's loop can call multiple `dispatch_to_*` tools concurrently (LLM tool-calling supports parallel calls).

---

## 8. Session Management

### 8.1 Storage

- Sessions live entirely in Redis; orchestrator is stateless
- Key: `session:{session_id}` → JSON blob
- TTL: 24h sliding (refreshed on each access)

### 8.2 Schema

```json
{
  "session_id": "sess_...",
  "user_id": "user_...",
  "created_at": "ISO8601",
  "last_active": "ISO8601",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]}
  ],
  "metadata": {"language": "en"}
}
```

### 8.3 Authentication

- Session identifier passed via `Authorization: Bearer <session_token>` — **never in the URL path**
- Session token is a short-lived random string bound to `session_id` server-side (Redis key `session_token:{token}` → `session_id`, TTL matches session)
- The `session_id` appears in URL for convenience (`/sessions/{session_id}/messages`) but access is authorized by the bearer token, not by path knowledge

### 8.4 Conversation Persistence

Session history is **ephemeral** (Redis, 24h). For durable history we use **async-non-blocking per-turn writes** to Postgres — never batch-nightly, never synchronous on the SSE path.

**Model.** Per turn (user message + final assistant response + tool-call summary):

1. SSE stream completes the `done` event to the client first.
2. A record is enqueued to an in-process `asyncio.Queue` (the "persist queue").
3. A dedicated persistence worker task (one per orchestrator replica) consumes the queue and writes to Postgres `messages` with `tenacity`-wrapped retries (exponential backoff, max 3 attempts).
4. On retry exhaustion, the record is pushed to a Redis-backed DLQ (`stream:persist:dlq`) for operator inspection and later replay.

**Why not nightly batch.** Batch windows create a gap where a crash loses every turn in-flight. Conversations double as the audit trail for guardrail blocks and user actions; losing them is a compliance and debugging problem. Per-turn write cost at projected scale (~1–2 inserts/sec) is well within Postgres headroom.

**Why not Celery/arq/dramatiq for this.** It's in-process fire-and-forget work. A task queue adds infra (separate worker processes, broker operations, result backend) without solving anything the asyncio queue doesn't already handle. See §20 for the workload that *does* justify durable execution infrastructure.

**Backpressure.** The persist queue has a bounded `maxsize` (default 10,000). If full, `put_nowait` raises — the orchestrator logs a `persist_queue_full` metric, exports an alerting span, and falls through to a synchronous write for that turn. Hitting this cap indicates Postgres is unhealthy; alerts should fire before the queue saturates.

**Graceful shutdown.** On SIGTERM, the orchestrator stops accepting new requests, drains the persist queue (up to a configurable deadline, default 30s), then exits. Anything still in-queue at deadline is pushed to the Redis DLQ before exit.

**Reconstruction.** On session expiry or cold-start after Redis eviction, the orchestrator lazy-loads the last N turns from Postgres `messages` into a fresh Redis session.

**Reference implementation** lives in `services/orchestrator/core/persistence.py`. Corresponding metrics and DLQ operator playbook are defined in the Dashboard sub-spec.

---

## 9. Agent Registry

### 9.1 Canonical Source: PostgreSQL

```sql
CREATE TABLE agents (
    name             VARCHAR(255) PRIMARY KEY,
    description      TEXT NOT NULL,
    capabilities     JSONB NOT NULL,          -- structured capability list
    tool_allowlist   JSONB NOT NULL DEFAULT '[]',
    status           VARCHAR(32) NOT NULL DEFAULT 'active',  -- active | draining | disabled
    version          VARCHAR(64) NOT NULL,
    registered_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat   TIMESTAMPTZ,
    metadata         JSONB DEFAULT '{}'
);
```

### 9.2 Registration Lifecycle

1. Agent worker starts → reads its own static manifest → upserts row in `agents`
2. Worker publishes a Redis pub/sub event on channel `agent:registry:changed`
3. Every orchestrator replica subscribes; on event, refreshes its in-memory tool list (regenerates `dispatch_to_<name>` tools)
4. MCP Gateway also subscribes; refreshes its per-agent tool-allowlist policy
5. Worker heartbeats every 30s by updating `last_heartbeat`. Missing heartbeats > 120s → orchestrator removes the dispatch tool until the agent recovers

### 9.3 Capability Indexing to Meilisearch

- On every registry change, an index-sync worker updates the `agent_capabilities` Meilisearch index
- Indexed fields: `name`, `description`, `capabilities[]`, with `description` and `capabilities` set searchable
- `discover_agents(intent)` does a simple text search; semantic embeddings deferred until quality demands it

---

## 10. API Design

### 10.1 Endpoints

All under `/api/v1`. Admin endpoints under `/admin/v1` (see Dashboard spec).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions` | Create a session; returns `session_id` + bearer `session_token` |
| `GET` | `/sessions/{session_id}` | Session metadata |
| `DELETE` | `/sessions/{session_id}` | End session |
| `POST` | `/sessions/{session_id}/messages` | Submit a user message; returns `202 Accepted` + `message_id` + `stream_url` |
| `GET` | `/sessions/{session_id}/messages/{message_id}` | **Polling** fallback: snapshot of message state |
| `GET` | `/sessions/{session_id}/messages/{message_id}/stream` | **SSE** live event stream |
| `GET` | `/sessions/{session_id}/messages` | Conversation history |
| `GET` | `/agents` | List active agents (public-safe summary) |
| `GET` | `/agents/{name}` | Agent capabilities |
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness (Redis + Postgres + at least one agent alive) |

### 10.2 `POST /messages` Response

```json
{
  "message_id": "msg_...",
  "status": "accepted",
  "stream_url": "/api/v1/sessions/sess_.../messages/msg_.../stream",
  "poll_url":   "/api/v1/sessions/sess_.../messages/msg_..."
}
```

### 10.3 SSE Event Taxonomy

See §6.4. Events are additive; clients should ignore unknown `kind` values.

### 10.4 Reconnection

If an SSE connection drops, clients reconnect with `Last-Event-ID` header. Orchestrator replays events from Redis (events persisted to `stream:message:{message_id}:events` with 10-minute TTL). Detailed SSE event schema and reconnect semantics are expanded in the umbrella; a full protocol doc is deferred until we see real client behavior.

---

## 11. Observability

### 11.1 OpenTelemetry

Every request produces a single trace. Span taxonomy:

```
HTTP POST /messages
└── orchestrator.handle_message
    ├── guardrails.input.prompt_injection
    ├── guardrails.input.pii
    ├── session.load
    └── agent.run (name="orchestrator")
        ├── llm.chat.completion (iteration 0)
        ├── tool.discover_agents
        ├── tool.dispatch_to_file_agent
        │   └── redis.stream.publish
        │       └── [trace continues in file_agent process via propagated context]
        │           ├── agent.run (name="file_agent")
        │           │   ├── llm.chat.completion
        │           │   └── tool.read_file
        │           │       └── mcp.gateway.execute_tool
        │           │           └── mcp.server.file_tools.read_file
        │           └── redis.stream.ack
        ├── llm.chat.completion (iteration 1)
        └── sse.stream.done
```

### 11.2 Span Attributes (Standard)

| Attribute | Notes |
|---|---|
| `session.id` | Present on all spans |
| `user.id` | Present on all spans |
| `agent.name` | Present on `agent.run` and descendants |
| `tool.name` | Present on `tool.*` spans |
| `llm.model` / `llm.prompt_tokens` / `llm.completion_tokens` | Present on `llm.*` spans |
| `guardrail.decision` | `allowed` \| `blocked` \| `flagged` |
| `guardrail.name` | e.g., `prompt_injection_v1` |

Full attribute taxonomy is finalized in the Dashboard sub-spec.

### 11.3 Metrics

Prometheus metric naming finalized in Dashboard sub-spec. High-level groups: `orchestrator_*`, `agent_*`, `mcp_tool_*`, `redis_stream_*`, `guardrail_*`, `session_*`.

### 11.4 Logging

- `structlog` with JSON output
- Correlation: every log line carries `trace_id`, `session_id`, `user_id`
- **PII redaction:** middleware scrubs known sensitive fields before emission (extended in Security sub-spec)

### 11.5 Sampling

- Head-based sampling configurable via env. Defaults:
  - Production: 10% of traces sampled at full detail; 100% of traces carrying a `guardrail.decision=blocked` span forced-sampled
  - Development: 100%

### 11.6 Langfuse (Testbed Only)

For the SDK variant of the agent core (`2026-04-23-agent-core-sdk.md`) we additionally enable **Langfuse** as an LLM-specific observability layer. Langfuse captures prompt/completion pairs, tool-call traces, and session-level quality signals in a form optimized for LLM debugging and prompt iteration.

- **Scope:** testbed only. Production (manual agent core) stays on OTEL + Prometheus + Jaeger.
- **Why not replace OTEL:** Langfuse is LLM-specific; OTEL is our system-wide tracing backbone. They complement — we do not depend on Langfuse for any production path.
- **Wiring:** see `2026-04-23-agent-core-sdk.md` §9.
- **No production coupling:** the manual agent core has zero Langfuse code paths. Removing the SDK variant deletes all Langfuse integration cleanly.

---

## 12. Guardrails Overview

Full design in `2026-04-23-guardrails.md`. Summary for context:

- **Scope v1.2:** Input + Tool + Jailbreak. Output guardrails deferred to v1.3.
- **Execution:** Orchestrator runs input guardrails. Agents run tool-call guardrails. MCP Gateway enforces per-user tool access policy + egress controls.
- **Interface:** single `Guardrail` protocol; multiple implementations pluggable via config.
- **Audit:** every decision emits an OTEL span and a Redis-stream audit event.

---

## 13. Security Overview

Full design in `2026-04-23-security.md`. Summary:

- **Auth:** bearer API keys (`oa_live_*`), argon2-hashed in Postgres, scoped via JSONB
- **Rate limits:** per-user, per-endpoint, global; Redis sliding window with Lua atomicity
- **Secrets:** `.env` for Docker Compose era; Sealed Secrets on k8s migration
- **Audit:** tool calls + admin actions + guardrail decisions all logged
- **Code executor sandbox:** explicitly out of scope for v1.2; file/search/document agents ship first

---

## 14. Evaluation Overview

Full design in `2026-04-23-agent-evaluation-and-testing.md`. Summary:

- **Layer 1 (plumbing):** pytest + fake `LLMClient`/`MCPClient` fixtures. Runs on every commit. Tests agent-loop correctness, dispatch semantics, guardrail wiring.
- **Layer 2 (quality):** DeepEval with curated golden datasets per agent. Nightly + pre-release. Tests real LLM behavior.
- **Router regression suite:** catches orchestrator mis-routing when models or prompts change.

---

## 15. Dashboard Overview

Full design in `2026-04-23-dashboard-and-ops-ui.md`. Summary:

- **v1.2 scope:** admin REST API + Prometheus metric conventions + OTEL attribute conventions + canonical Grafana dashboard JSON + CLI wrappers. **No custom frontend.**
- **Admin API namespace:** `/admin/v1/*`, separate auth (`X-Admin-Key`)
- **Ops via Grafana + Jaeger + CLI.** Custom UI is a v1.3 consumer of the same admin API.

---

## 16. Deferred Work (Stubs)

The following areas are acknowledged here but their detailed specs are deferred. Each is a candidate for a dedicated doc in v1.3.

### 16.1 Reliability & Failure Modes (stub)

What's in v1.2: Redis Streams consumer groups, XAUTOCLAIM-based janitor, DLQ per agent, dispatch timeouts.

What's deferred: circuit breakers on MCP tool calls, per-agent bulkheads (connection pool isolation), formal failure-mode matrix ("what happens when X dies" for X ∈ {Redis, Postgres, vLLM, single MCP server, orchestrator replica, sub-agent replica, Meilisearch}), chaos testing.

Implication for v1.2: the system will survive normal failures but will not gracefully degrade under partial infra outages. Acceptable for a scaffold and early users; non-negotiable before scale milestones.

### 16.2 Multi-tenancy & Data Isolation (stub)

**v1.2 is single-tenant by design.** The intended deployment shape is one on-prem install per organization, serving many concurrent users within that organization. "Many concurrent users" is a *scale* concern (addressed by stateless orchestrator replicas, Redis Streams fan-out, horizontal scaling) — not a *multi-tenancy* concern. The two are distinct and the spec treats them as such.

What's in v1.2:
- Single shared Postgres DB, single Meilisearch index, single Redis namespace
- API keys scoped to a **user** (not to a tenant)
- No tenant concept exists in any data model, no `tenant_id` column, no tenant-aware auth

What's deferred (explicitly v2, not v1.3):
- Postgres Row-Level Security for per-tenant data isolation
- Meilisearch index-per-tenant or attribute filtering
- Tenant-scoped session namespaces
- Tenant admin APIs
- Tenant-level rate limits and billing
- Cross-tenant data-leak test harness

**Non-goal for v1.2:** Do not attempt to retrofit tenant isolation on top of v1.2. Multi-tenancy changes data-model assumptions across every storage layer; that's a v2 redesign, not an increment. If multi-tenant deployment becomes a real requirement, it gets a dedicated design pass.

### 16.3 Deployment & Ops (stub)

What's in v1.2: Docker Compose for local/staging, documented k8s migration patterns, Sealed Secrets as the secrets-at-scale path, Alembic for Postgres migrations, Prometheus scrape configs.

What's deferred: production Helm charts, HPA/PDB/NetworkPolicy manifests, blue/green deployment procedure, formal SLOs + error budgets + paging runbooks, trace-sampling policy tuned to observed costs, backup/restore procedures.

### 16.4 Detailed SSE Protocol (folded in, not deferred)

SSE event schema and reconnect semantics are in §6.4 and §10.4 at the detail needed for v1.2. A dedicated protocol doc may be extracted later if external clients need a formal contract.

---

## 17. Project Structure

```
openagent/
├── services/
│   ├── common/
│   │   ├── interfaces.py              # BaseAgent, Guardrail, SessionStore, LLMClient, MCPClient
│   │   ├── schemas.py                 # Task, Result, AgentEvent, ToolCall
│   │   └── telemetry.py               # OTEL setup
│   │
│   ├── orchestrator/
│   │   ├── app/
│   │   │   ├── main.py                # FastAPI app
│   │   │   ├── config.py
│   │   │   ├── api/
│   │   │   │   ├── routes/
│   │   │   │   │   ├── sessions.py
│   │   │   │   │   ├── messages.py    # incl. SSE streaming
│   │   │   │   │   ├── agents.py
│   │   │   │   │   └── admin.py       # /admin/v1/*
│   │   │   ├── core/
│   │   │   │   ├── orchestrator_agent.py   # The conductor agent
│   │   │   │   ├── dispatch_tools.py       # dispatch_to_<name> tool factory
│   │   │   │   ├── discover_tool.py        # discover_agents(intent)
│   │   │   │   ├── session_store.py        # Redis-backed
│   │   │   │   ├── rate_limiter.py
│   │   │   │   └── janitor.py              # XAUTOCLAIM for stuck messages
│   │   │   ├── guardrails/            # input guardrails
│   │   │   └── db/                    # Postgres models + repos + Alembic
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── agents/
│   │   ├── base/
│   │   │   ├── agent_core_manual.py   # production BaseAgent impl
│   │   │   ├── agent_core_sdk.py      # testbed BaseAgent impl (optional dep)
│   │   │   ├── worker.py              # Redis Streams consumer loop
│   │   │   └── config.py
│   │   ├── file_agent/
│   │   │   ├── agent.py               # wires BaseAgent impl + file-specific system prompt + tools
│   │   │   ├── tools.py
│   │   │   └── Dockerfile
│   │   └── ...
│   │
│   └── mcp_gateway/
│       ├── app/
│       │   ├── main.py
│       │   ├── tool_registry.py
│       │   ├── policy.py              # per-user/per-agent tool allowlist
│       │   ├── egress.py              # egress controls
│       │   └── audit.py
│       ├── mcp_servers/
│       │   ├── file_tools/
│       │   ├── web_search/
│       │   └── ...
│       ├── Dockerfile
│       └── pyproject.toml
│
├── evals/
│   ├── plumbing/                      # Layer 1 (pytest; runs on every commit)
│   └── quality/                       # Layer 2 (DeepEval; nightly)
│       ├── datasets/
│       └── suites/
│
├── ops/
│   ├── grafana/                       # canonical dashboard JSON
│   └── cli/                           # oactl admin CLI
│
├── docker-compose.yml
├── pyproject.toml                     # UV workspace
└── README.md
```

---

## 18. Implementation Phases

Revised sequencing: MCP Gateway before agents (agents depend on it); evaluation harness introduced early so agent work is testable from day one.

### Phase 1 — Foundation
- [ ] UV workspace + Docker Compose (Redis, Postgres, Meilisearch, Jaeger, Prometheus, Grafana)
- [ ] `services/common` — `BaseAgent`, `Task`, `Result`, `Guardrail` protocols
- [ ] OTEL tracing + structlog setup
- [ ] Postgres schema + Alembic

### Phase 2 — MCP Gateway
- [ ] FastMCP-based gateway with tool registry
- [ ] First MCP server: `file_tools`
- [ ] Per-agent tool allowlist policy
- [ ] Egress control skeleton
- [ ] Tool call audit log

### Phase 3 — Agent Core (Production Path)
- [ ] `agent_core_manual.py` — the ~400-LOC loop
- [ ] Redis Streams worker wrapper
- [ ] First sub-agent: `file_agent`
- [ ] Layer-1 plumbing tests

### Phase 3b — Agent Core (Testbed, Optional)
- [ ] `agent_core_sdk.py` using OpenAI Agents SDK 0.14
- [ ] Parity test: same `Task` → equivalent `Result` on both variants

### Phase 4 — Orchestrator
- [ ] FastAPI app, session management, rate limiting
- [ ] `OrchestratorAgent` built on `agent_core_manual`
- [ ] `discover_agents` via Meilisearch
- [ ] `dispatch_to_*` tool factory, Redis Streams producer
- [ ] SSE streaming + polling fallback
- [ ] Input guardrails
- [ ] Janitor (XAUTOCLAIM)

### Phase 5 — Observability & Admin
- [ ] Full OTEL span taxonomy
- [ ] Prometheus metric exposition
- [ ] Canonical Grafana dashboard JSON
- [ ] Admin API (`/admin/v1/*`)
- [ ] `oactl` CLI

### Phase 6 — Hardening
- [ ] API key auth (`oa_live_*`)
- [ ] Rate limit Lua scripts
- [ ] Audit log Postgres sink
- [ ] Layer-2 evaluation suites (DeepEval)
- [ ] Router regression eval
- [ ] Load test baseline

### Deferred to v1.3+
- Full Reliability spec (circuit breakers, bulkheads, chaos tests)
- Full Multi-tenancy spec
- Output guardrails
- Code executor agent + sandbox
- Custom dashboard UI
- Helm charts + HPA + blue/green

---

## 19. Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestration style | Orchestrator-as-agent (Claude-Code-style) | Single conversational surface; natural composition via tool calls |
| Routing | Via `discover_agents` + `dispatch_to_*` tool calls | No separate LLM router round-trip; auditable via traces |
| Agent composition | Redis Streams (multi-process) | Isolated fault domains, independent scaling, matches container model |
| Handoffs | Mediated by orchestrator (no peer-to-peer) | Simpler tracing; cleaner user-visible progress |
| LLM framework | None (manual loop for production) + SDK testbed | Avoid lock-in; architecture bypasses most SDK value |
| Result delivery | SSE primary, polling fallback | Natural fit for streaming; script-friendly fallback |
| Orchestrator replication | Stateless, N replicas, HPA | Required for 100+ concurrent users |
| Session state | Redis, 24h TTL, bearer token auth | Stateless orchestrator; token bound to session |
| Agent registry | Postgres canonical; Redis pub/sub for updates | Durable, restart-resilient; live updates |
| Capability discovery | Meilisearch full-text → `discover_agents` tool | Keeps orchestrator prompt small at 20+ agents |
| Guardrails | Hybrid execution (orchestrator + agent + gateway) | Each layer enforces what it uniquely sees |
| Secrets | `.env` → Sealed Secrets on k8s migration | Keep v1.2 simple; upgrade path documented |
| Code executor | Deferred to post-v1.2 | Sandbox is an engineering project unto itself |
| Dashboard | Admin API + Grafana + CLI, no custom UI | Avoid speculative frontend work |
| Evaluation | Pytest plumbing + DeepEval quality | Two layers: fast deterministic + slow real-LLM |
| Python | 3.13 | Proven; 3.14 upgrade deferred |

---

## 20. Durable Agent Runs Overview

Full design in `2026-04-23-durable-agent-runs.md`. Summary:

**Motivation.** Chat turns are short (seconds, SSE-attached). But some agent work is **long-running** — a deep-research job that searches, self-critiques, formats, and saves a report may take hours. The user should be able to kick it off, close the browser or start a new session, and come back later to see the result. Losing such a job to an orchestrator restart is unacceptable.

**Two distinct workloads.** These do not share infrastructure:

| | Chat turn | Durable run |
|---|---|---|
| Duration | <100ms–30s | minutes to hours |
| User attached | Yes (SSE) | No (detaches) |
| Survives restart | N/A | **Required** |
| Mid-task state | None | Checkpoints every step |
| Observable | SSE only | `GET /runs/{id}` anytime |
| Cancellable | No | Yes |

**v1.2 approach.** Redis Streams + Postgres checkpoint table, reusing the same streams-based fabric used for sub-agent dispatch. `agent_runs` table in Postgres stores canonical state; worker checkpoints after every LLM call or tool call. On worker crash, XAUTOCLAIM resurrects the run to another worker, which resumes from the last checkpoint.

**Deliberately not chosen for v1.2.**
- **Temporal** — correct industrial-grade answer; premature for one workflow type; revisit at v2.
- **Celery / arq / dramatiq** — task queues, not durable execution; don't solve checkpointing, which is the hard part.
- **Postgres-as-queue** — works, but we already have Redis Streams running; don't introduce a second queueing primitive.

**Key primitives (see sub-spec for full design):**
- `Run` as a first-class concept; sessions and runs are orthogonal (runs outlive sessions)
- Checkpoint protocol agents implement: `await ctx.checkpoint(state, step=N)` after each step
- `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/stream`, `DELETE /runs/{id}` on the public API
- Cancellation is cooperative (worker checks `cancel_requested` between steps)
- DLQ + operator replay for runs that fail their retry budget

**Relationship to §8 (sessions).** A session can *launch* a run but does not *own* its lifecycle. Run results are pushed to the launching session if still active, and always persisted to `agent_runs.result` for later retrieval. A user can list their runs via `GET /runs?user_id=me` regardless of session state.

---

## 21. Changelog

### v1.2 (2026-04-23)

**Architecture**
- Orchestrator redesigned as an agent with sub-agents as tools ("Claude-Code-style"); separate Router/Dispatcher/Aggregator components removed
- `discover_agents(intent)` tool added, powered by Meilisearch
- Orchestrator replication story made explicit (stateless, N replicas, HPA)
- Session token no longer path-scoped; moved to `Authorization: Bearer`

**Framework**
- OpenAI Agents SDK removed as runtime dependency for production path
- Agent core designated as the `BaseAgent` protocol with two implementations: manual (production) in `agent-core-manual.md`, SDK-backed (testbed) in `agent-core-sdk.md`

**Delivery**
- SSE added as primary result delivery; polling retained as fallback
- SSE reconnection semantics via `Last-Event-ID`

**Reliability**
- Redis Streams: consumer groups, XAUTOCLAIM-based janitor, per-agent DLQ streams
- Dispatch timeouts enforced per-tool-call at the orchestrator

**Registry**
- Postgres canonical; dual-source drift eliminated
- Redis pub/sub `agent:registry:changed` drives live tool-list updates in orchestrator + gateway
- Heartbeat-based liveness (30s heartbeat, 120s miss → dispatch tool removed)

**Security / Guardrails**
- Guardrails scope clarified: Input + Tool + Jailbreak in v1.2; Output deferred
- Hybrid execution model (orchestrator + agent + gateway)
- API key design specified (`oa_live_*`, argon2, scoped)

**Sub-specs introduced**
- `agent-core-sdk.md`
- `agent-core-manual.md`
- `guardrails.md`
- `dashboard-and-ops-ui.md`
- `agent-evaluation-and-testing.md`
- `security.md`
- `durable-agent-runs.md`

**Version bumps**
- FastAPI: 0.128.0 → ≥0.136.0
- FastMCP: confirmed v3.2.4
- Python: held at 3.13

**Critical-review amendments (2026-04-24)**
- §8.4 conversation persistence made explicit as **async-non-blocking per-turn writes** via in-process `asyncio.Queue` + Redis DLQ on retry exhaustion. Celery/arq explicitly rejected for this workload.
- §11.6 Langfuse added as **testbed-only** observability, complement to OTEL, no production coupling.
- §16.2 multi-tenancy stub **tightened to single-tenant Case A** and explicitly labeled a v2 redesign (not a v1.3 increment). Scale ≠ multi-tenancy clarified.
- §20 + new sub-spec `durable-agent-runs.md` introduced to cover long-running agent work (deep research, hours-scale jobs) with Redis-Streams + Postgres-checkpoint design. Temporal deferred to v2.
- `services/` kept (not renamed to `src/`); multi-service monorepo convention retained.

### v1.1 (2026-04-22)
- Prior version; superseded by this document

### v1.0 (2026-04-22)
- Initial design

---

*End of Document*

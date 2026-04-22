# Multi-Agent Orchestration System Design

**Document Version:** 1.1
**Date:** 2026-04-22
**Status:** Draft — Pending Review

> **⚠️ Version Check Required:** Before implementation, verify the following package versions against their official sources (PyPI, GitHub releases). The versions below were current as of the document date but may have updated since.
>
> | Package | Documented Version | Check At |
> |---------|-------------------|----------|
> | Python | 3.13 | python.org/downloads |
> | OpenAI Agents SDK | v0.7.0 | github.com/openai/openai-agents-python/releases |
> | FastMCP | v3.2.4 | github.com/prefecthq/fastmcp/releases |
> | FastAPI | 0.128.0 | pypi.org/project/fastapi |

---

## 1. Project Overview

### 1.1 Purpose

A standalone multi-agent orchestration system that serves as a workplace AI assistant platform. The system receives tasks from users via a REST API, decomposes them using an LLM-powered orchestrator, and dispatches them to specialized agents equipped with tools via MCP (Model Context Protocol) servers.

### 1.2 Target Users

- Enterprise employees requiring AI assistance for workplace tasks
- External systems (Slack, Teams, internal portals) integrating via REST API
- Frontend developers building chat interfaces on top of the API

### 1.3 Target Scale

| Metric | Value |
|--------|-------|
| Concurrent users | 100+ |
| Concurrent active agents | 20+ |
| Target deployment | On-premise private server |
| Estimated LLM backend | vLLM (OpenAI-compatible, self-hosted) |

---

## 2. Technical Stack

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| **Language** | Python | 3.13 | Latest stable, on-premise compatible |
| **Package Manager** | UV | latest | Fast Rust-based Python package manager |
| **Agents Framework** | OpenAI Agents SDK | v0.7.0 | Native OpenAI model support, tool/function calling |
| **LLM Backend** | vLLM | — | Self-hosted, on-premise, OpenAI API compatibility |
| **Cache / Sessions** | Redis | 7-alpine | Token-carrying stateless sessions, rate limiting |
| **Persistent Memory** | PostgreSQL | 16-alpine | Structured storage; swap to Mem0 later without API changes |
| **MCP Framework** | FastMCP | v3.2.4 | Lightweight, Python-native MCP server development |
| **API Framework** | FastAPI | 0.128.0 | Async, OpenAPI generation, easy REST integration |
| **Observability** | OpenTelemetry | — | Full distributed tracing, vendor-neutral |
| **Packaging** | Docker Compose → Kubernetes | — | Containerization from day one for k8s migration |
| **Vector Search** | Meilisearch | v1.6 | On-premise semantic search capability |

> **Note on UV:** UV is used as the Python package manager across all services. It replaces pip/poetry/pipenv with a single unified tool. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh`.

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           External Clients                               │
│         (REST API / Slack / Teams / Custom Frontends)                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP/REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Orchestrator Service                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Router     │  │  Task        │  │  Session     │  │   Rate       │ │
│  │  (LLM-based) │  │  Dispatcher  │  │  Manager     │  │   Limiter    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Agent Service A │ │  Agent Service B │ │  Agent Service N │
│  ┌────────────┐  │ │  ┌────────────┐  │ │  ┌────────────┐  │
│  │  Worker    │  │ │  │  Worker    │  │ │  │  Worker    │  │
│  └────────────┘  │ │  └────────────┘  │ │  └────────────┘  │
└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
              ┌───────────────────────────────────────┐
              │         Central MCP Gateway           │
              │         (FastMCP-based)               │
              │  ┌─────────────────────────────────┐  │
              │  │  Tool Registry / Capability     │  │
              │  │  Directory                      │  │
              │  └─────────────────────────────────┘  │
              └───────────────────┬───────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│  MCP Server A │       │  MCP Server B │       │  MCP Server N │
│  (File Tools) │       │ (Web Search)  │       │ (Code Exec)   │
└───────────────┘       └───────────────┘       └───────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Orchestrator Service** | Central hub: receives requests, routes via LLM, dispatches tasks, manages sessions |
| **Agent Workers** | Execute assigned tasks using OpenAI Agents SDK, call MCP tools |
| **Central MCP Gateway** | Single entry point for all tool access; manages MCP server lifecycle |
| **Redis** | Stateless session storage, rate limiting, async task queue (Streams) |
| **PostgreSQL** | Persistent memory, conversation history, user preferences, agent registry |
| **Meilisearch** | Semantic search over documents and knowledge bases |

---

## 4. Component Details

### 4.1 Orchestrator Service

The orchestrator is the central coordinator. It is designed as a **single monolithic service** for simplicity of development and debugging, while keeping agent workers as separate processes for independent scaling.

#### 4.1.1 Sub-components

| Component | Role |
|-----------|------|
| **LLM Router** | Uses the LLM to reason about which agent is best suited for a given task. Receives agent capability descriptions and selects the optimal match. |
| **Task Dispatcher** | Sends tasks to Redis Streams for async processing by agents. Handles timeout tracking and retry logic. |
| **Session Manager** | Validates session tokens, retrieves conversation context from Redis, manages turn-by-turn state. |
| **Rate Limiter** | Per-user and per-endpoint rate limiting using Redis. Prevents abuse. |
| **Result Aggregator** | Collects results from agent workers via Redis Streams, assembles responses, handles partial failures. |

#### 4.1.2 Routing Logic

The router uses **LLM-powered reasoning** (Option C from evaluation):

1. Request arrives with user message and session context
2. Router builds a prompt containing:
   - Available agent capabilities (registered in agent registry)
   - Conversation history (last N turns)
   - User message
3. Router calls the LLM with a structured output schema requesting:
   - Target agent selection
   - Task description for the selected agent
   - Priority (if relevant)
4. Dispatcher queues the task for the selected agent

**Rationale:** LLM-based routing is most flexible for a scaffold where agent types evolve. New agents register their capabilities; no retraining or rule updates required.

#### 4.1.3 Configuration

```yaml
orchestrator:
  host: "0.0.0.0"
  port: 8000
  max_concurrent_tasks: 100
  task_timeout_seconds: 300
  max_retries: 2

redis:
  host: "localhost"
  port: 6379
  db: 0

database:
  host: "localhost"
  port: 5432
  name: "orchestrator_db"

llm:
  api_base: "http://localhost:8001/v1"  # vLLM server
  model: "your-model-name"
  timeout: 60
```

### 4.2 Agent Workers

Agents are independent worker processes that consume tasks from Redis Streams and execute them using the OpenAI Agents SDK.

#### 4.2.1 Agent Interface

Each agent:
- Registers capabilities with the MCP Gateway at startup
- Consumes tasks from its dedicated Redis stream channel
- Uses the OpenAI Agents SDK to process tasks with its assigned tools
- Writes results back to a response Redis stream
- Emits OpenTelemetry traces for observability

#### 4.2.2 Agent Registry (PostgreSQL)

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    capabilities JSONB NOT NULL,  -- ["file_read", "code_execute", "web_search"]
    status VARCHAR(50) DEFAULT 'active',  -- active, inactive, maintenance
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.2.3 Adding New Agents

1. Create a new agent service project (Python package)
2. Implement the agent worker class using OpenAI Agents SDK
3. Register capabilities with the MCP Gateway
4. Add agent metadata to PostgreSQL registry
5. Deploy as a new container in Docker Compose / k8s

**Rationale for separate agent processes:** Isolated fault domains, independent scaling, different tool dependencies per agent type.

### 4.3 Central MCP Gateway

The MCP Gateway is a **single shared service** that all agents connect to for tool access.

#### 4.3.1 Responsibilities

| Responsibility | Description |
|----------------|-------------|
| **Tool Registry** | Maintains a directory of all available tools and their schemas |
| **Capability Discovery** | Agents query the gateway to discover available tools |
| **Tool Execution Proxy** | Forwards tool execution requests to the appropriate MCP server |
| **Connection Management** | Manages connections to underlying MCP servers |
| **Rate Limiting** | Per-tool rate limiting to prevent abuse |

#### 4.3.2 Architecture

```
Agent Worker                    MCP Gateway                    MCP Servers
     │                              │                                │
     │──── get_capabilities() ─────►│                                │
     │◄─── capability_list ─────────│                                │
     │                              │                                │
     │──── execute_tool() ─────────►│                                │
     │                              │──── forward_request() ─────────►│
     │                              │◄─── tool_result ────────────────│
     │◄─── result ──────────────────│                                │
```

#### 4.3.3 Tool Definition Schema

```python
from pydantic import BaseModel
from typing import Optional

class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: Optional[dict] = None
    mcp_server: str  # Which MCP server provides this tool
    rate_limit_per_minute: int = 60
```

#### 4.3.4 MCP Server Management

MCP servers are registered with the gateway via configuration:

```yaml
mcp_gateway:
  servers:
    file_tools:
      type: fastmcp
      module: mcp_servers.file_tools
      enabled: true

    web_search:
      type: fastmcp
      module: mcp_servers.web_search
      enabled: true

    code_executor:
      type: fastmcp
      module: mcp_servers.code_exec
      enabled: true
```

### 4.4 FastMCP-Based Tool Servers

Tools are built using **FastMCP**, a lightweight Python library for creating MCP servers.

#### 4.4.1 Example Tool Structure

```
mcp_servers/
├── file_tools/
│   ├── __init__.py
│   ├── server.py          # FastMCP server definition
│   └── requirements.txt
├── web_search/
│   ├── __init__.py
│   ├── server.py
│   └── requirements.txt
└── code_executor/
    ├── __init__.py
    ├── server.py
    └── requirements.txt
```

#### 4.4.2 FastMCP Tool Example

```python
from fastmcp import FastMCP

mcp = FastMCP("file_tools")

@mcp.tool()
async def read_file(path: str, max_lines: int = 100) -> str:
    """Read contents of a file."""
    with open(path) as f:
        lines = f.readlines()[:max_lines]
    return "".join(lines)

mcp.run()
```

### 4.5 Session Management (Redis)

Sessions are **stateless** — the client carries a session token, and all session data lives in Redis.

#### 4.5.1 Session Data Structure

```json
{
  "session_id": "sess_abc123",
  "user_id": "user_456",
  "created_at": "2026-04-22T10:00:00Z",
  "last_active": "2026-04-22T10:05:00Z",
  "context": {
    "conversation_history": [
      {"role": "user", "content": "Analyze this report"},
      {"role": "assistant", "content": "Which report would you like analyzed?"}
    ],
    "metadata": {
      "language": "en",
      "priority": "normal"
    }
  }
}
```

#### 4.5.2 Redis Key Patterns

| Pattern | Purpose | TTL |
|---------|---------|-----|
| `session:{session_id}` | Full session data | 24 hours |
| `ratelimit:user:{user_id}` | Rate limit counters | Sliding window |
| `ratelimit:global` | Global rate limit | Sliding window |
| `task:{task_id}` | Task state tracking | 1 hour |
| `stream:agent:{agent_name}` | Redis Stream channel per agent | No TTL |

### 4.6 Persistent Memory (PostgreSQL)

PostgreSQL stores structured data that survives beyond a single session.

#### 4.6.1 Conversation History

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    metadata JSONB
);
```

#### 4.6.2 Message Store

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    role VARCHAR(50) NOT NULL,  -- user, assistant, agent
    agent_name VARCHAR(255),     -- which agent handled this
    content TEXT NOT NULL,
    tool_calls JSONB,            -- captured tool invocations
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.6.3 User Preferences

```sql
CREATE TABLE user_preferences (
    user_id VARCHAR(255) PRIMARY KEY,
    default_agent VARCHAR(255),
    language VARCHAR(10),
    settings JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Rationale for PostgreSQL over Mem0:** On-premise deployment, full control, simple migration path. When Mem0 is adopted, replace the memory layer only — keep the schema and API interface unchanged.

### 4.7 Meilisearch Integration

Meilisearch provides semantic search capabilities for:

- **Document retrieval** — agents can search internal knowledge bases
- **Tool discovery** — find relevant tools based on natural language queries
- **Context enrichment** — pull relevant documents to augment agent prompts

```python
# Agent can query Meilisearch for relevant context
results = meilisearch.index("documents").search(
    query="Q4 financial report analysis",
    attributes_to_retrieve=["title", "content", "metadata"]
)
```

### 4.8 Redis Streams for Async Task Processing

Tasks are dispatched via **Redis Streams** for reliable async processing.

#### 4.8.1 Stream Architecture

```
                                    ┌──────────────────┐
                                    │   Orchestrator   │
                                    │   (Producer)     │
                                    └────────┬─────────┘
                                             │
                         ┌───────────────────┼───────────────────┐
                         ▼                   ▼                   ▼
                  ┌────────────┐      ┌────────────┐      ┌────────────┐
                  │ Stream:    │      │ Stream:    │      │ Stream:    │
                  │ agent.file │      │ agent.code │      │ agent.web  │
                  └─────┬──────┘      └─────┬──────┘      └─────┬──────┘
                        │                   │                   │
                        ▼                   ▼                   ▼
                  ┌────────────┐      ┌────────────┐      ┌────────────┐
                  │ Agent      │      │ Agent      │      │ Agent      │
                  │ Worker A   │      │ Worker B   │      │ Worker C   │
                  └────────────┘      └────────────┘      └────────────┘
```

#### 4.8.2 Task Message Schema

```json
{
  "task_id": "task_xyz789",
  "agent_name": "file_agent",
  "user_id": "user_456",
  "session_id": "sess_abc123",
  "prompt": "Read the contents of /data/reports/q4.csv",
  "context": {
    "conversation_history": [...],
    "attachments": []
  },
  "priority": "normal",
  "created_at": "2026-04-22T10:00:00Z"
}
```

#### 4.8.3 Result Message Schema

```json
{
  "task_id": "task_xyz789",
  "status": "completed",
  "agent_name": "file_agent",
  "result": {
    "content": "file contents...",
    "tools_used": ["read_file"]
  },
  "trace_id": "abc123trace",
  "completed_at": "2026-04-22T10:00:15Z"
}
```

---

## 5. API Design

### 5.1 REST Endpoints

All endpoints are under `/api/v1`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions/{session_id}` | Get session details |
| `DELETE` | `/sessions/{session_id}` | End a session |
| `POST` | `/sessions/{session_id}/messages` | Send a message (invoke orchestrator) |
| `GET` | `/sessions/{session_id}/messages` | Get conversation history |
| `GET` | `/agents` | List registered agents |
| `GET` | `/agents/{agent_name}` | Get agent capabilities |
| `GET` | `/health` | Health check |
| `GET` | `/ready` | Readiness probe |

### 5.2 Request/Response Examples

#### Create Session

```http
POST /api/v1/sessions
Content-Type: application/json

{
  "user_id": "user_456",
  "metadata": {
    "language": "en"
  }
}
```

```json
{
  "session_id": "sess_abc123",
  "created_at": "2026-04-22T10:00:00Z",
  "expires_at": "2026-04-23T10:00:00Z"
}
```

#### Send Message

```http
POST /api/v1/sessions/sess_abc123/messages
Content-Type: application/json

{
  "content": "Analyze the Q4 sales report",
  "attachments": []
}
```

```json
{
  "message_id": "msg_789xyz",
  "agent_assigned": "file_agent",
  "status": "processing",
  "created_at": "2026-04-22T10:00:01Z"
}
```

#### Poll for Result

```http
GET /api/v1/sessions/sess_abc123/messages/msg_789xyz
```

```json
{
  "message_id": "msg_789xyz",
  "status": "completed",
  "content": "Here is the analysis of Q4 sales...",
  "agent_name": "file_agent",
  "tools_used": ["read_file", "search_documents"],
  "completed_at": "2026-04-22T10:00:15Z"
}
```

---

## 6. Observability

### 6.1 OpenTelemetry Integration

Full distributed tracing from user request through agent execution to tool results.

#### 6.1.1 Trace Structure

```
Session: sess_abc123
└── Orchestrator Request
    ├── LLM: Router Decision
    ├── Dispatch Task
    │   └── Redis Streams Enqueue
    └── Agent Invocation
        ├── LLM: Agent Reasoning
        ├── MCP: Tool Call (file_tools.read_file)
        ├── MCP: Tool Call (meilisearch.search)
        └── Response Assembly
```

#### 6.1.2 Span Attributes

| Attribute | Value |
|-----------|-------|
| `session.id` | Session identifier |
| `user.id` | User identifier |
| `agent.name` | Which agent handled the request |
| `tool.name` | Which tool was called |
| `llm.model` | Model used for reasoning |
| `llm.prompt_tokens` | Token count |
| `llm.completion_tokens` | Token count |

### 6.2 Logging

Structured logging with `structlog`:

```json
{
  "timestamp": "2026-04-22T10:00:01Z",
  "level": "INFO",
  "trace_id": "abc123trace",
  "session_id": "sess_abc123",
  "message": "Task dispatched to agent",
  "agent_name": "file_agent",
  "task_id": "task_xyz789"
}
```

### 6.3 Metrics (Future Dashboard)

Metrics to be exposed for the future dashboard:

| Metric | Type | Description |
|--------|------|-------------|
| `orchestrator.requests.total` | Counter | Total requests by endpoint |
| `orchestrator.requests.active` | Gauge | Currently processing requests |
| `agent.tasks.total` | Counter | Tasks processed by agent |
| `agent.tasks.duration_seconds` | Histogram | Task processing time |
| `agent.tasks.failed` | Counter | Failed tasks by agent |
| `mcp.tool.calls.total` | Counter | Tool invocations |
| `mcp.tool.duration_seconds` | Histogram | Tool execution time |
| `redis.streams.lag` | Gauge | Consumer lag per stream |
| `session.active` | Gauge | Active sessions count |

---

## 7. Security

### 7.1 Rate Limiting

- **Per-user:** 60 requests/minute (configurable)
- **Per-endpoint:** Different limits (e.g., `/sessions` vs `/messages`)
- **Global:** 1000 requests/minute aggregate

Implemented via Redis sliding window algorithm.

### 7.2 Authentication

| Method | Use Case |
|--------|----------|
| **API Key** | External systems, frontend integration |
| **OAuth 2.0 / OIDC** | Enterprise SSO integration |

API key passed via `X-API-Key` header or `Authorization: Bearer` header.

### 7.3 Guardrails

| Guardrail | Description |
|-----------|-------------|
| **Input validation** | Pydantic models validate all API inputs |
| **Output sanitization** | Agent outputs scrubbed before storage/return |
| **Tool access control** | Per-user/per-session tool access policies |
| **Audit logging** | All tool invocations logged with user context |

---

## 8. Containerization

### 8.1 Docker Compose Structure

```yaml
services:
  orchestrator:
    build:
      context: ./services/orchestrator
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - REDIS_HOST=redis
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/orchestrator
      - LLM_API_BASE=http://vllm:8001/v1
    depends_on:
      - redis
      - postgres
    volumes:
      - ./services/orchestrator:/app

  agent_file:
    build:
      context: ./services/agents/file_agent
      dockerfile: Dockerfile
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

### 8.2 Kubernetes Migration Path

The Docker Compose setup is designed for direct k8s migration:

| Docker Compose | Kubernetes |
|----------------|------------|
| Service | Deployment |
| `ports` | Service + Ingress |
| `depends_on` | Init containers / Service dependencies |
| `volumes` | PersistentVolumeClaim |
| `environment` | ConfigMap + Secret |

Container images should be built and pushed to a private registry before k8s deployment.

---

## 9. Project Structure

```
openagent/
├── services/
│   ├── orchestrator/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py              # FastAPI app
│   │   │   ├── config.py            # Pydantic settings
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── routes/
│   │   │   │   │   ├── sessions.py
│   │   │   │   │   ├── messages.py
│   │   │   │   │   └── agents.py
│   │   │   │   └── deps.py          # Dependencies
│   │   │   ├── core/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py        # LLM-based routing
│   │   │   │   ├── dispatcher.py    # Redis Streams producer
│   │   │   │   ├── session.py       # Session management
│   │   │   │   └── rate_limiter.py
│   │   │   ├── db/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py        # SQLAlchemy models
│   │   │   │   └── repositories.py
│   │   │   └── observability/
│   │   │       ├── __init__.py
│   │   │       ├── tracing.py
│   │   │       └── logging.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── agents/
│   │   ├── base/
│   │   │   ├── __init__.py
│   │   │   ├── worker.py            # Base agent worker
│   │   │   └── config.py
│   │   ├── file_agent/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py             # OpenAI Agents SDK agent
│   │   │   ├── tools.py             # Agent-specific tools
│   │   │   └── Dockerfile
│   │   └── ... (other agents)
│   │
│   └── mcp_gateway/
│       ├── __init__.py
│       ├── server.py                # FastMCP gateway
│       ├── tool_registry.py
│       ├── config.py
│       ├── Dockerfile
│       └── mcp_servers/
│           ├── __init__.py
│           ├── file_tools/
│           │   ├── server.py
│           │   └── requirements.txt
│           ├── web_search/
│           │   ├── server.py
│           │   └── requirements.txt
│           └── ... (other MCP servers)
│
├── docker-compose.yml
├── docker-compose.k8s.yml           # Future k8s manifest
├── .env.example
├── pyproject.toml                   # Workspace config (UV)
└── README.md
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Scaffold)
- [ ] Project structure setup (UV workspace)
- [ ] Docker Compose with all services
- [ ] PostgreSQL schema initialization
- [ ] Redis connection and stream setup
- [ ] Basic FastAPI orchestrator with health/ready endpoints
- [ ] OpenTelemetry tracing setup (basic)
- [ ] Structured logging

### Phase 2: Core Orchestration
- [ ] Session management (create, get, delete)
- [ ] LLM router integration with vLLM
- [ ] Task dispatcher (Redis Streams producer)
- [ ] Rate limiter implementation
- [ ] Message endpoint (sync response mode)

### Phase 3: Agent Workers
- [ ] Base agent worker class
- [ ] First agent (file_agent) implementation
- [ ] Redis Streams consumer per agent
- [ ] Agent result aggregation
- [ ] Task timeout and retry logic

### Phase 4: MCP Gateway
- [ ] Central MCP gateway service
- [ ] Tool registry
- [ ] First MCP server (file_tools with FastMCP)
- [ ] Agent capability registration
- [ ] Tool execution proxy

### Phase 5: Observability Dashboard
- [ ] OpenTelemetry spans throughout
- [ ] Jaeger integration
- [ ] Metrics exposition
- [ ] Dashboard for agent status, MCP health, guardrails

### Phase 6: Production Hardening
- [ ] Authentication (API Key + OAuth)
- [ ] Output sanitization
- [ ] Tool access control policies
- [ ] Load testing
- [ ] Kubernetes manifests
- [ ] CI/CD pipeline

---

## 11. Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestrator architecture | Monolithic single service | Simpler to build/debug; scales via agents, not orchestrator |
| Task routing | LLM-powered reasoning | Most flexible for evolving agent set; no retraining |
| Agent communication | Redis Streams (async) | Handles long-running tasks; same Redis for sessions/rate-limiting |
| Session management | Stateless (token-carrying) | Horizontal scaling; no server-side session affinity |
| Persistent memory | PostgreSQL | On-premise friendly; swap to Mem0 later without API change |
| MCP integration | Central gateway + FastMCP | DRY resource usage; single source of truth for tools |
| Observability | OpenTelemetry | Full trace visibility; vendor-neutral; future dashboard-ready |
| User interface | REST API only | Frontend team integrates via API |
| Scale target | ~100 users, 20+ concurrent agents | Container-ready from day one; k8s migration path clear |
| Package manager | UV | Fast, reliable, unified Python dependency management |

---

## 12. Future Considerations

| Area | Consideration |
|------|---------------|
| **Mem0 Integration** | Replace PostgreSQL memory layer with Mem0. Keep schema interface compatible. |
| **Agent Feedback Loops** | Agents that refine output by calling other agents iteratively |
| **Human-in-the-loop** | Approval checkpoints for high-stakes agent actions |
| **Multi-modal** | Image/document processing agents |
| **Real-time WebSocket** | Interactive streaming responses (future frontend need) |

---

## Appendix A: Environment Variables

```env
# Orchestrator
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
REDIS_HOST=redis
REDIS_PORT=6379
DATABASE_URL=postgresql://postgres:password@postgres:5432/orchestrator
LLM_API_BASE=http://vllm:8001/v1
LLM_MODEL=your-model-name
LLM_API_KEY=sk-...  # If required by vLLM

# MCP Gateway
MCP_GATEWAY_PORT=8002

# Meilisearch
MEILISEARCH_HOST=http://meilisearch:7700
MEILISEARCH_MASTER_KEY=your_master_key

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_SERVICE_NAME=orchestrator
```

---

## Appendix B: OpenAPI Schema (Core Types)

```yaml
components:
  schemas:
    Session:
      type: object
      properties:
        session_id:
          type: string
        user_id:
          type: string
        created_at:
          type: string
          format: date-time
        expires_at:
          type: string
          format: date-time

    Message:
      type: object
      properties:
        message_id:
          type: string
        session_id:
          type: string
        role:
          type: string
          enum: [user, assistant, agent]
        content:
          type: string
        agent_name:
          type: string
        status:
          type: string
          enum: [pending, processing, completed, failed]
        created_at:
          type: string
          format: date-time

    Agent:
      type: object
      properties:
        name:
          type: string
        description:
          type: string
        capabilities:
          type: array
          items:
            type: string
        status:
          type: string
          enum: [active, inactive, maintenance]
```

---

## Appendix C: Changelog

### v1.1 (2026-04-22)
- Updated Python version from 3.12+ to 3.13
- Added UV as package manager (replaces pip/poetry/pipenv)
- Updated OpenAI Agents SDK to v0.7.0
- Updated FastMCP to v3.2.4
- Updated FastAPI to 0.128.0
- Added version check warning with URLs for online verification
- Updated project structure to reflect UV workspace
- Minor formatting and consistency improvements

### v1.0 (2026-04-22)
- Initial design document

---

*End of Design Document*
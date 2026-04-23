# Dashboard & Ops UI

**Document Version:** 1.0
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Parent:** `2026-04-23-multi-agent-system-design-v1.2.md`

---

## 1. Purpose and Scope

### 1.1 What v1.2 ships

The "dashboard" for v1.2 is **not a custom frontend**. It is:

1. An **admin REST API** (`/admin/v1/*`) exposing read and control operations
2. A **Prometheus metric naming convention** for all services
3. An **OTEL attribute naming convention** usable by Jaeger for trace drill-down
4. A **canonical Grafana dashboard JSON** shipped in `ops/grafana/`
5. A **CLI tool** (`oactl`) wrapping the admin API for ops workflows

Ops personnel use Grafana + Jaeger + `oactl`. That's the v1.2 "dashboard."

### 1.2 Why not a custom UI

- No one knows yet which ops flows will actually be used. A custom UI built on speculation is the canonical wasted-work pattern.
- Grafana + Jaeger + a well-designed admin API covers every realistic ops need for a 100-user scaffold.
- A future custom UI is a pure consumer of the admin API. Building the admin API now means no backend refactor later.

### 1.3 v1.3 roadmap (not delivered here)

- React/Vue admin SPA consuming `/admin/v1/*`
- Unified view of agents + sessions + traces + costs
- In-browser ops actions (drain, disable, terminate) as thin wrappers over the API

---

## 2. Admin API

### 2.1 Authentication

- Separate credential from user API keys
- Header: `X-Admin-Key: <token>`
- Admin keys live in Postgres table `admin_keys` (argon2-hashed, scopes in JSONB)
- Admin API and user API routes are both served by the orchestrator service, but middleware enforces the correct header per route
- 401 on missing/invalid admin key; never fall through to user-auth paths

### 2.2 Endpoint Catalog

All under `/admin/v1`. All responses JSON unless noted.

#### Agents

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/agents/status` | List all registered agents with live health: `name`, `status`, `version`, `last_heartbeat`, `queue_depth`, `active_tasks`, `error_rate_5m` |
| `GET` | `/agents/{name}` | Detail view: capabilities, tool allowlist, recent task stats |
| `POST` | `/agents/{name}/drain` | Graceful: stop accepting new dispatch; let in-flight finish. Sets `status=draining` in registry; orchestrator stops generating `dispatch_to_<name>` tool |
| `POST` | `/agents/{name}/resume` | Reverses drain |
| `POST` | `/agents/{name}/disable` | Hard: immediate. Any in-flight task is dropped. Sets `status=disabled` |
| `POST` | `/agents/{name}/enable` | Reverses disable |

#### Sessions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/sessions/active` | List active sessions: `session_id`, `user_id`, `started_at`, `duration_s`, `message_count`, `tokens_used`, `currently_streaming` |
| `GET` | `/sessions/{id}` | Single session with full event trace link |
| `DELETE` | `/sessions/{id}` | Force-terminate a session (close SSE streams, clear Redis state) |

#### Streams

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/streams/lag` | Per-stream consumer lag: `stream_name`, `pending_count`, `oldest_pending_age_s`, `consumer_count` |
| `POST` | `/streams/{name}/claim-stuck` | Run `XAUTOCLAIM` manually on stuck messages beyond the janitor's schedule |
| `GET` | `/streams/{name}/dlq` | List DLQ messages (last 100) with their original task metadata and failure reason |
| `POST` | `/streams/{name}/dlq/{msg_id}/replay` | Re-enqueue a DLQ message |
| `DELETE` | `/streams/{name}/dlq/{msg_id}` | Acknowledge a DLQ message (drop permanently) |

#### Users & Rate Limits

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/users/{id}/usage` | Last 24h + 30d: requests, tokens, estimated cost, abuse_score |
| `PATCH` | `/users/{id}/rate-limit` | Override user rate limit; persists to Redis + optional DB record |
| `POST` | `/users/{id}/suspend` | Immediate block on all user API keys |
| `POST` | `/users/{id}/unsuspend` | Reverse |

#### MCP Gateway

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/mcp/servers` | List all MCP servers with health: name, up/down, avg latency, error rate |
| `POST` | `/mcp/servers/{name}/restart` | Signal restart (deferred — requires process supervisor hook; v1.3) |

#### Guardrails

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/guardrails/recent-blocks` | Last N audit events from `audit_guardrail_blocks` |
| `POST` | `/guardrails/reload` | Reload guardrail config without restart (deferred; v1.3) |

#### Diagnostics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/config` | Non-secret runtime config snapshot |
| `GET` | `/version` | Service versions, git SHA, build time |

### 2.3 Safety

- All write endpoints (`POST`/`PATCH`/`DELETE`) require admin scope `ops:write`
- Read-only endpoints require `ops:read`
- All admin actions emit an OTEL span and a row in Postgres `audit_admin_actions`:

```sql
CREATE TABLE audit_admin_actions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    admin_key_id   VARCHAR(64) NOT NULL,
    action         VARCHAR(128) NOT NULL,
    target_type    VARCHAR(64),
    target_id      VARCHAR(255),
    payload        JSONB,
    result         VARCHAR(16)        -- success | failure
);
```

### 2.4 OpenAPI

Admin API routes generate OpenAPI under `/admin/v1/openapi.json` — separate from the user API's OpenAPI. Tag routes appropriately so schema tooling doesn't merge them accidentally.

---

## 3. Prometheus Metric Taxonomy

All metrics use `snake_case`; prefixes namespace by concern.

### 3.1 Orchestrator

| Metric | Type | Labels | Description |
|---|---|---|---|
| `orchestrator_requests_total` | Counter | `endpoint`, `status_code` | All HTTP requests |
| `orchestrator_request_duration_seconds` | Histogram | `endpoint`, `status_code` | End-to-end request latency |
| `orchestrator_active_sessions` | Gauge | — | Currently live sessions |
| `orchestrator_active_sse_streams` | Gauge | — | Open SSE connections (used for HPA) |
| `orchestrator_message_turns_total` | Counter | `result` (completed/failed/timeout) | Full message turns |
| `orchestrator_iterations_per_turn` | Histogram | — | LLM iterations per message |

### 3.2 Agents

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agent_tasks_total` | Counter | `agent`, `result` | Tasks consumed |
| `agent_task_duration_seconds` | Histogram | `agent` | Task processing time |
| `agent_queue_depth` | Gauge | `agent` | `XLEN` of input stream |
| `agent_pending_count` | Gauge | `agent` | `XPENDING` size |
| `agent_dlq_count` | Gauge | `agent` | Size of DLQ stream |
| `agent_heartbeat_age_seconds` | Gauge | `agent` | Seconds since last heartbeat (freshness) |

### 3.3 LLM

| Metric | Type | Labels | Description |
|---|---|---|---|
| `llm_calls_total` | Counter | `agent`, `model`, `status` | LLM API calls |
| `llm_call_duration_seconds` | Histogram | `agent`, `model` | Latency |
| `llm_prompt_tokens_total` | Counter | `agent`, `model` | Tokens sent |
| `llm_completion_tokens_total` | Counter | `agent`, `model` | Tokens received |

### 3.4 Tools / MCP

| Metric | Type | Labels | Description |
|---|---|---|---|
| `mcp_tool_calls_total` | Counter | `tool`, `server`, `status` | Tool invocations |
| `mcp_tool_duration_seconds` | Histogram | `tool`, `server` | Tool latency |
| `mcp_server_up` | Gauge | `server` | 1/0 liveness |

### 3.5 Guardrails

See the Guardrails sub-spec §10.2. Owned there; included in the canonical dashboard.

### 3.6 Redis Streams

| Metric | Type | Labels | Description |
|---|---|---|---|
| `redis_stream_length` | Gauge | `stream` | `XLEN` |
| `redis_stream_lag_seconds` | Gauge | `stream`, `group` | Age of oldest pending entry |
| `redis_stream_autoclaim_total` | Counter | `stream` | Count of janitor-claimed messages |

### 3.7 Cost

| Metric | Type | Labels | Description |
|---|---|---|---|
| `user_tokens_total` | Counter | `user_id`, `model`, `direction` | Per-user token usage (direction = prompt/completion) |

Cardinality warning: `user_id` label can explode at 100+ users. Mitigation: sample into a top-N gauge (`user_tokens_top_n`), keep raw in Postgres for detailed reporting. v1.2 keeps full cardinality with a monitoring alert if it passes 10,000 distinct label combinations.

---

## 4. OTEL Attribute Taxonomy

Standard attributes appear on every span within a request. Listed in §11.2 of the umbrella doc. Additional attributes per span kind:

| Span | Required attributes |
|---|---|
| `agent.run` | `agent.name`, `agent.core` (manual/sdk), `task.id`, `session.id`, `user.id` |
| `llm.chat.completion` | `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.iteration`, `llm.parallel_tool_calls` |
| `tool.call` | `tool.name`, `tool.kind` (mcp/inprocess), `tool.duration_ms` |
| `mcp.gateway.execute_tool` | `mcp.server`, `mcp.tool`, `mcp.upstream_status` |
| `guardrail.*.check` | `guardrail.name`, `guardrail.kind`, `guardrail.decision`, `guardrail.reason` |
| `redis.stream.*` | `redis.stream`, `redis.group` |
| `session.*` | `session.id` |
| `admin.action` | `admin.action`, `admin.target_type`, `admin.target_id` |

These names are normative — dashboards and alerts are authored against them.

---

## 5. Canonical Grafana Dashboard

### 5.1 Location

`ops/grafana/dashboards/openagent-overview.json` — committed to the repo. Versioned with the rest of the code.

### 5.2 Panels (in order)

1. **Request rate & error rate** (orchestrator endpoints)
2. **SSE active streams** + HPA threshold line
3. **Message turn outcomes** (completed / failed / timeout stacked)
4. **p50/p95/p99 latency** (end-to-end request, LLM call, tool call)
5. **Agent grid** (table: agent × queue depth × pending × error rate × heartbeat age — red/yellow/green threshold coloring)
6. **DLQ size per agent** (alert fires at > 0 for 5m)
7. **LLM token rate** (prompt + completion stacked, per model)
8. **Estimated cost / 5m** (from token metrics × model-price config; model-price table in Prometheus file_sd)
9. **Top 10 users by token usage** (last 1h)
10. **Guardrail blocks** (rate by guardrail name)
11. **MCP server up/down** + avg latency panel
12. **Redis stream lag per stream**
13. **Jaeger trace link panel** (Grafana + Jaeger datasource: click to see worst traces)

### 5.3 Alerts (minimum set)

- **DLQ non-empty** for > 5m (severity: page)
- **Agent heartbeat missing** for > 2m (severity: warn)
- **MCP server down** for > 1m (severity: page)
- **Guardrail block rate > 10% of requests** for > 5m (severity: warn)
- **p99 latency > 30s** for > 5m (severity: warn)
- **SSE active streams > 90% of per-replica cap** for > 2m (severity: scale-up signal)

Alert routing and paging policy: deferred to Deployment sub-spec (stub in umbrella §16.3).

---

## 6. `oactl` CLI

A thin wrapper over the admin API for terminal-friendly ops.

### 6.1 Installation

```bash
# Shipped with the repo
uv tool install ./ops/cli
```

### 6.2 Commands

```
oactl agents list
oactl agents status <name>
oactl agents drain <name>
oactl agents disable <name> [--reason "..."]

oactl sessions list [--user USER] [--active]
oactl sessions show <session_id>
oactl sessions kill <session_id>

oactl streams lag
oactl streams dlq list <agent>
oactl streams dlq replay <agent> <msg_id>

oactl users show <user_id>
oactl users suspend <user_id> [--reason "..."]
oactl users set-rate-limit <user_id> --rpm 100

oactl mcp servers
oactl guardrails recent-blocks [--user USER] [--limit 50]
```

### 6.3 Config

```
# ~/.config/oactl/config.toml
endpoint = "https://orchestrator.internal/admin/v1"
admin_key = "env:OACTL_ADMIN_KEY"         # never hardcode
default_output = "table"                   # or "json"
```

### 6.4 Output

- Default: human-readable tables with color
- `--json`: machine-readable for scripting
- `--watch`: for any `list`/`show` command, refresh every 2s

---

## 7. Project Structure Additions

```
ops/
├── grafana/
│   ├── dashboards/
│   │   └── openagent-overview.json
│   ├── datasources.yaml                  # Prometheus + Jaeger
│   └── provisioning/                     # Grafana auto-provision config
│
├── prometheus/
│   ├── prometheus.yml
│   └── rules/
│       └── openagent-alerts.yaml
│
├── cli/
│   ├── oactl/
│   │   ├── __main__.py
│   │   ├── commands/
│   │   │   ├── agents.py
│   │   │   ├── sessions.py
│   │   │   ├── streams.py
│   │   │   ├── users.py
│   │   │   ├── mcp.py
│   │   │   └── guardrails.py
│   │   └── client.py                     # HTTP client
│   └── pyproject.toml
│
└── runbooks/                             # Human-written ops playbooks
    ├── agent-heartbeat-missing.md
    ├── dlq-non-empty.md
    └── mcp-server-down.md
```

---

## 8. Testing

### 8.1 Admin API tests (Layer 1)

- Each endpoint: happy path + auth failure + not-found + permission-denied
- `drain` → verify orchestrator drops the dispatch tool
- `kill session` → verify SSE stream closes

### 8.2 CLI tests

- Each command: correct HTTP call, correct argument parsing, JSON vs table output

### 8.3 Dashboard JSON validation

- CI step: parse `openagent-overview.json`, verify references to metrics and attributes exist in our normative lists
- Fails build if a dashboard panel references a metric that doesn't exist (drift protection)

---

## 9. v1.3 Path to Custom UI

A SPA consuming the admin API. Separate spec. Reuses:

- Existing admin API (no changes)
- Existing auth (same admin key)
- Existing OpenAPI for codegen
- Existing metric names for live panels

The expectation is that the SPA launches as an **additive** layer — the admin API and `oactl` remain supported forever.

---

*End of Document*

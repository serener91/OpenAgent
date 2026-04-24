# Durable Agent Runs

**Document Version:** 1.0
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Parent:** `2026-04-23-multi-agent-system-design-v1.2.md`
**Peers:** `agent-core-manual.md`, `agent-core-sdk.md`, `security.md`, `dashboard-and-ops-ui.md`

---

## 1. Purpose and Motivation

Chat turns are short-lived: user sends a message, orchestrator streams a response over SSE, done in seconds. But some agent work is fundamentally long-lived:

- A deep-research job searches, critiques, formats, and saves a report — potentially hours
- A batch document analysis processes thousands of files
- A multi-step refactor plan executes across many tool calls

For this class of work, the user must be able to:

1. **Detach.** Kick off the job, close the browser, go home — the job keeps running.
2. **Start new sessions.** Open a new conversation while the job runs. The new session must not be blocked by the background work.
3. **Reattach.** Come back later, query status, optionally re-open a live event stream.
4. **Survive crashes.** An orchestrator or worker restart during a 2-hour job must not throw away the first 1:50.
5. **Cancel.** Stop a run cleanly between steps.

Chat infrastructure (SSE, session-scoped state) does not solve this. Task queues (Celery, arq) do not solve it either — they dispatch tasks but do not checkpoint mid-task, so a worker crash mid-run loses everything.

This spec defines a first-class **`Run`** concept with **durable execution**: checkpoint every step to Postgres, resume from last checkpoint on worker failure, and expose runs via a public API independent of sessions.

---

## 2. Non-Goals for v1.2

- **Full workflow engine semantics** (Temporal-style signals, queries, child workflows, deterministic replay). Revisit at v2 if the shape of work demands it.
- **Distributed transactions / sagas across external systems.** Runs are idempotent at the step level or tolerate at-least-once step execution.
- **Graphical workflow authoring.** Runs are defined in code by the agent implementation.
- **Cross-run dependencies** (run B starts only when run A completes). User can sequence via separate API calls.

---

## 3. Concept Model

### 3.1 Run

A `Run` is one long-lived execution of an agent on a task, with durable state.

**Fields:**

- `run_id` — UUID
- `user_id` — owner (always required)
- `session_id` — optional; the session that launched it. Nullable because the session may expire before the run completes.
- `agent_name` — which agent is executing (must exist in registry)
- `status` — `queued | running | completed | failed | cancelled`
- `input` — original task payload (immutable after creation)
- `checkpoint_state` — opaque JSONB written by the agent between steps
- `step_count` — monotonic counter, incremented at each checkpoint
- `result` — final `Result` object when status = completed
- `error` — failure reason when status = failed
- `cancel_requested` — boolean flag, settable via `DELETE /runs/{id}`
- Timestamps: `created_at`, `started_at`, `last_checkpoint_at`, `completed_at`

### 3.2 Run vs Session

Runs and sessions are **orthogonal**. A session may launch 0..N runs. A run may outlive its launching session. A user may list all runs regardless of session membership.

When a session launches a run:
- The launch is recorded in session history as a "launched run" event
- If the session is still active when the run completes, the run result is also pushed into the session's message stream as an assistant message

When a session expires while a run is still running:
- The run continues unaffected
- The user can retrieve the result via `GET /runs/{id}` from any future session

### 3.3 Step and Checkpoint

A **step** is one observable unit of agent progress — typically one LLM call or one tool call. After each step the agent writes a checkpoint:

```python
await ctx.checkpoint(
    state={
        "phase": "research",
        "queries_completed": ["...", "..."],
        "findings": [...],
        "next_action": "summarize",
    },
    step=self.step_count + 1,
)
```

Checkpoints are idempotent keyed on `(run_id, step)`. Replay tolerance: if the worker crashes after a step but before acking, another worker may re-execute that step. Agents must design steps to be idempotent or to detect re-execution via the checkpoint state.

---

## 4. Storage

### 4.1 Postgres Schema

```sql
CREATE TABLE agent_runs (
    run_id              UUID PRIMARY KEY,
    user_id             UUID NOT NULL,
    session_id          UUID,
    agent_name          VARCHAR(255) NOT NULL REFERENCES agents(name),
    status              VARCHAR(32) NOT NULL
                          CHECK (status IN ('queued','running','completed','failed','cancelled')),
    input               JSONB NOT NULL,
    checkpoint_state    JSONB,
    step_count          INTEGER NOT NULL DEFAULT 0,
    result              JSONB,
    error               TEXT,
    cancel_requested    BOOLEAN NOT NULL DEFAULT FALSE,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    max_retries         INTEGER NOT NULL DEFAULT 2,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMPTZ,
    last_checkpoint_at  TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);

CREATE INDEX ix_agent_runs_user_status ON agent_runs (user_id, status);
CREATE INDEX ix_agent_runs_status_last_checkpoint ON agent_runs (status, last_checkpoint_at)
  WHERE status IN ('queued', 'running');

CREATE TABLE agent_run_events (
    event_id            BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    step                INTEGER NOT NULL,
    kind                VARCHAR(64) NOT NULL,     -- matches AgentEvent.kind
    data                JSONB NOT NULL,
    emitted_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_agent_run_events_run_id ON agent_run_events (run_id, event_id);
```

`agent_runs` is the source of truth for run state. `agent_run_events` is the append-only event log used to replay events to late-attaching SSE clients.

### 4.2 Redis Streams

| Stream | Purpose | Consumer |
|---|---|---|
| `stream:runs:<agent_name>` | Queued runs for a given agent | Run-worker consumer group `<agent_name>-run-workers` |
| `stream:runs:<agent_name>:dlq` | Runs that exhausted retries | Operator-only, alerting on non-empty |
| `stream:run:<run_id>:events` | Live event fan-out for attached SSE clients | Orchestrator SSE handlers; TTL 10 min |

A run is acked (`XACK`) only when it reaches a terminal status (`completed`, `failed`, `cancelled`, or `failed` after DLQ move). This is the key durability property: a worker crash mid-run leaves the message pending; `XAUTOCLAIM` resurrects it to another worker, which reloads state from Postgres and resumes.

---

## 5. Worker Lifecycle

### 5.1 Worker Process

Run workers are separate from chat-path agent workers. This is deliberate — we do **not** want a 2-hour research run starving the pool of workers that service interactive chat turns.

- One worker pool per agent type, sized independently (e.g., `file-agent-run-workers` at N=2, `file-agent-chat-workers` at N=8)
- Consumer group: `<agent_name>-run-workers`
- Shares the same `BaseAgent` implementation — the difference is only the driver loop around it

### 5.2 Execution Loop

Pseudocode:

```python
async def run_worker_loop(agent_name: str):
    async for msg in claim_or_read(stream=f"stream:runs:{agent_name}",
                                   group=f"{agent_name}-run-workers"):
        run_id = msg["run_id"]
        run = await db.load_run(run_id)

        if run.status == "cancelled":
            await ack(msg); continue

        await db.mark_running(run_id, started_at=now())

        try:
            agent = build_agent(agent_name)
            ctx = RunContext(run_id=run_id, db=db, events_stream=f"stream:run:{run_id}:events")
            # Agent reads run.checkpoint_state to decide where to resume
            result = await agent.run_durable(run.input, ctx=ctx, resume_from=run.checkpoint_state)
            await db.mark_completed(run_id, result=result)
            await publish_terminal_event(run_id, kind="done", data={"result": result.dict()})
            await ack(msg)

        except CancelRequested:
            await db.mark_cancelled(run_id)
            await publish_terminal_event(run_id, kind="cancelled", data={})
            await ack(msg)

        except RetryableError as e:
            run.retry_count += 1
            if run.retry_count > run.max_retries:
                await db.mark_failed(run_id, error=str(e))
                await move_to_dlq(msg)
                await ack(msg)
            else:
                await db.save_retry_count(run_id, run.retry_count)
                # Do NOT ack — XAUTOCLAIM will re-deliver after idle timeout
                raise

        except Exception as e:
            await db.mark_failed(run_id, error=f"fatal: {e}")
            await publish_terminal_event(run_id, kind="error", data={"error": str(e)})
            await ack(msg)
```

### 5.3 Cooperative Cancellation

Between steps, agents check `ctx.cancel_requested()`:

```python
async def run_durable(self, input, ctx, resume_from=None):
    state = resume_from or {"phase": "init"}

    while state["phase"] != "done":
        if await ctx.cancel_requested():
            raise CancelRequested()

        # do the next step
        state = await self._execute_step(state, ctx)
        await ctx.checkpoint(state, step=state.get("step", 0))
```

`ctx.cancel_requested()` reads the `cancel_requested` column from Postgres (cached briefly; refreshed between steps). Cancellation is not preemptive — an in-flight LLM call completes before the worker checks and exits.

### 5.4 Recovery from Crash

`XAUTOCLAIM` janitor (same pattern as §7.4 of the umbrella) claims messages idle > 2 min for run streams (longer than chat streams because runs have longer step latencies). On reclaim:

- Worker loads `agent_runs` row, sees `checkpoint_state` is non-null
- Invokes `agent.run_durable(input, ctx, resume_from=checkpoint_state)`
- Agent resumes from last good state; previously completed steps are not re-executed *if* the agent's checkpoint captured enough state to skip them (this is the agent's responsibility)

---

## 6. Public API

All endpoints under `/api/v1/runs`. Authenticated with the same bearer token as sessions; runs are scoped to `user_id`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/runs` | Create + enqueue a run. Body: `{agent_name, input, session_id?, max_retries?}`. Returns `{run_id, status, stream_url, poll_url}`. |
| `GET` | `/runs/{run_id}` | Snapshot: status, step_count, last_checkpoint_at, result (if done), error (if failed). |
| `GET` | `/runs/{run_id}/stream` | SSE: live events from run start (or `Last-Event-ID` for resume). Replays from `agent_run_events` then attaches to Redis Stream. |
| `DELETE` | `/runs/{run_id}` | Request cancellation. Idempotent. Returns current status. |
| `GET` | `/runs` | List runs for the authenticated user. Query params: `status`, `agent_name`, `limit`, `before` (cursor). |

### 6.1 POST /runs

```json
POST /api/v1/runs
{
  "agent_name": "deep_research_agent",
  "input": {"prompt": "...", "context": {...}},
  "session_id": "sess_..."
}

-> 202 Accepted
{
  "run_id": "run_...",
  "status": "queued",
  "stream_url": "/api/v1/runs/run_.../stream",
  "poll_url":   "/api/v1/runs/run_..."
}
```

### 6.2 SSE Contract for /runs/{id}/stream

- On connect, the handler:
  1. Replays events from `agent_run_events WHERE run_id = ? AND event_id > Last-Event-ID` (or from 0 if first connect)
  2. Attaches to `stream:run:{run_id}:events` for live tail
  3. Emits `done` or `cancelled` or `error` terminal event and closes
- Clients must treat the connection as resumable and re-attempt with `Last-Event-ID`

---

## 7. Retry and DLQ Semantics

| Failure mode | Handling |
|---|---|
| Transient error within a step (network, 5xx from tool) | Step-level retry via `tenacity` inside the agent |
| Worker crash mid-step | `XAUTOCLAIM` → another worker resumes from last checkpoint |
| Agent raises `RetryableError` | Whole-run retry: `retry_count += 1`; re-delivered by XAUTOCLAIM; max_retries default 2 |
| Agent raises other exception | Run marked `failed`; NOT retried; DLQ'd if not already terminal |
| Retry budget exhausted | Run marked `failed`; message moved to `stream:runs:<agent>:dlq`; alert fires |
| User requests cancel | Worker detects on next `ctx.cancel_requested()` check; clean exit as `cancelled` |

**DLQ operator playbook:** see Dashboard sub-spec. Operators can inspect DLQ contents, mark a run for replay (moves back to main stream with reset retry counter), or discard.

---

## 8. Integration Points

### 8.1 Agent-core-manual

`ManualAgent` gains an optional `run_durable(input, ctx, resume_from=None)` method. If the agent doesn't implement it, `POST /runs` rejects with 400 ("agent does not support durable runs"). Short-lived agents (e.g., simple file-read agent) don't need durable-run support.

### 8.2 Agent-core-sdk (testbed)

The SDK variant can implement `run_durable` by wrapping `Runner.run_streamed` and checkpointing after each `RunItemStreamEvent`. Expect coarser checkpoints than manual because the SDK controls the step boundary. Testbed-only; not a production surface.

### 8.3 Orchestrator

The orchestrator exposes a `dispatch_durable_to_<name>` tool family alongside the normal `dispatch_to_<name>`. The durable variant:

- Creates a run via `POST /runs` internally
- Returns immediately with `{run_id, stream_url}` instead of blocking on a result
- The orchestrator LLM is instructed to tell the user "I've started a background research task; I'll let you know when it's done" and end the chat turn

Whether to offer the durable variant is per-agent metadata (`agent_metadata.supports_durable_runs = true`). Added to the Postgres `agents` registry row.

### 8.4 Guardrails

Guardrails run at run-creation time (input guardrails on the initial prompt) and at each tool call during the run (same as chat-path agents). Output guardrails are deferred to v1.3 across the whole system and apply equally here when added.

### 8.5 Observability

- Every run produces a single OTEL trace spanning its full lifetime, including restarts (`trace_id` stored on `agent_runs`). Resumed runs continue the same trace with a new span.
- Metrics (Prometheus, full taxonomy in Dashboard sub-spec):
  - `agent_runs_created_total{agent}`
  - `agent_runs_completed_total{agent,status}`
  - `agent_runs_duration_seconds{agent}` (histogram)
  - `agent_runs_active{agent}` (gauge)
  - `agent_runs_checkpoints_total{agent}`
  - `agent_runs_dlq_depth{agent}` (gauge)

### 8.6 Security

- Runs are scoped to `user_id` at creation; all read endpoints enforce `run.user_id == caller.user_id`
- Admin endpoints (under `/admin/v1/runs`) bypass user scoping, audited per `audit_admin_actions`
- DLQ inspection is an admin-only action

---

## 9. Implementation Phases

Fits into the umbrella's Phase sequencing as follows:

- **Phase 4 (Orchestrator) depends on Phase 3 (Agent Core).** Add the `run_durable` hook to `ManualAgent` in Phase 3.
- **Phase 4.5 (Durable Runs)** — new sub-phase:
  - `agent_runs` + `agent_run_events` schema + Alembic migration
  - Run worker process (`services/agents/base/run_worker.py`)
  - `/api/v1/runs` endpoints
  - Cancellation path
  - Phase-1 plumbing tests (durable-run lifecycle, crash recovery, cancellation)
- **Phase 5 (Observability)** adds run metrics to the canonical dashboard
- **Phase 6 (Hardening)** adds Layer-2 evals for at least one durable agent (e.g., deep-research)

---

## 10. Known Tradeoffs and When to Revisit

**Why not Temporal now.** Temporal solves durable execution more robustly than what we're building: deterministic workflow replay, built-in signals and queries, non-retryable-error primitives, automatic history retention. But it's a separate cluster to operate and a learning curve for the team. For one or two workflow types in v1.2–v1.3 the Redis+Postgres approach is sufficient.

**Revisit Temporal when:**
- We have 3+ distinct long-running workflow types
- Crash-recovery correctness bugs surface (agent replay semantics get hard with multiple external side effects per step)
- Team grows to the point where operating Temporal is justified
- Cross-workflow orchestration becomes a requirement

**Checkpoint granularity.** The agent decides when to checkpoint. Coarse checkpoints = fewer Postgres writes, more re-work on crash. Fine checkpoints = opposite. We start with one checkpoint per LLM call and one per significant tool call; tune per agent based on observed crash/cost tradeoffs.

**Worker saturation.** A small pool plus hours-long runs means the pool can fill. The run-worker pool is sized independently per agent; HPA keys on `agent_runs_active{agent}` and stream lag. For agents expected to run many concurrent hours-long jobs, overprovision deliberately.

**Storage growth.** `agent_run_events` grows unbounded without retention. Retention policy v1.2: keep event rows for 30 days after run completion; archive or drop older. `checkpoint_state` is kept for the lifetime of the run row. Runs themselves retained indefinitely (it's the user's work product) until explicit deletion.

---

*End of Document*

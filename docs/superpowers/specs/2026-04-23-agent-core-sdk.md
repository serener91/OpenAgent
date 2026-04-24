# Agent Core — SDK Variant (Testbed)

**Document Version:** 1.0
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Parent:** `2026-04-23-multi-agent-system-design-v1.2.md`
**Peer:** `2026-04-23-agent-core-manual.md` (production path)

> **⚠️ Testbed, not production.** This variant exists to let us prototype agent behaviors quickly against the OpenAI Agents SDK. Behaviors validated here must be re-implemented against the manual agent core before shipping. Do not deploy the SDK variant to production. Do not build new features exclusively against this variant.

---

## 1. Purpose

The SDK variant lets developers:

- Spin up new agents with minimal boilerplate while exploring behavior
- Use the SDK's ergonomic features (`@function_tool`, `Runner.run_streamed`, `Session`, `Guardrail`) for fast iteration
- Validate that the `BaseAgent` protocol defined in the umbrella doc is expressive enough to cover a framework-backed implementation

The SDK variant is **opt-in**. An agent worker chooses at startup which core to use; the rest of the system can't tell the difference.

---

## 2. When to Use

| Situation | Use SDK variant? |
|---|---|
| Exploring a new agent idea, unsure of tool shape | ✅ Yes |
| Prototyping guardrail rules before committing to them | ✅ Yes |
| Building an agent intended for production | ❌ No — use manual |
| Adding a new first-party agent to the system | ❌ No — use manual |
| Benchmarking latency / token usage | ⚠️ Caution — SDK overhead differs from manual |

---

## 3. Implementation

### 3.1 Package Dependencies

```toml
# services/agents/pyproject.toml (testbed extra)
[project.optional-dependencies]
sdk-testbed = [
  "openai-agents>=0.14.3,<0.15",
]
```

The `openai-agents` package is an **optional** dependency. Production Docker images exclude it (`uv sync --no-group sdk-testbed`).

### 3.1.1 Import Namespace Hazard (`agents`)

The `openai-agents` package installs itself as a **top-level `agents` module** — `from agents import Agent, Runner`. That name is both generic and conflicts semantically with our internal `services/agents/*` package tree. Two rules apply:

**Rule A — Our code never uses the bare `agents` name.**
All our internal imports are fully qualified: `from services.agents.base.agent_core_sdk import SDKBackedAgent`. No file anywhere in our codebase may do `from agents import ...` as a reference to *our* package; our package is always `services.agents.*`. A CI guard (ruff custom rule or grep) enforces this.

**Rule B — All SDK imports are aliased on entry.**
When pulling from the SDK, alias at the import site so downstream code never references a bare `Agent` / `Runner` / `Session` that could be mistaken for one of ours:

```python
# services/agents/base/agent_core_sdk.py
from agents import (
    Agent as OpenAIAgent,
    Runner as OpenAIRunner,
    Session as OpenAISession,
    function_tool as openai_function_tool,
    input_guardrail as openai_input_guardrail,
    output_guardrail as openai_output_guardrail,
    set_tracing_disabled,
)
```

**Rule C — SDK tracing is disabled at module load.**
We do not use the SDK's built-in tracing. OTEL (production) and Langfuse (testbed) are the observability surfaces. Disable immediately on import so no stray trace emitter starts up:

```python
# services/agents/base/agent_core_sdk.py (at module top, after imports)
set_tracing_disabled(disabled=True)
```

This must happen **before** any `OpenAIAgent` or `OpenAIRunner` is constructed. Put the call at module scope, not inside `__init__`, so it runs exactly once when the adapter module is imported.

### 3.2 Class Layout

```python
# services/agents/base/agent_core_sdk.py
from agents import (
    Agent as OpenAIAgent,
    Runner as OpenAIRunner,
    Session as OpenAISession,
    function_tool as openai_function_tool,
    input_guardrail as openai_input_guardrail,
    output_guardrail as openai_output_guardrail,
    set_tracing_disabled,
)

# Disable SDK's built-in tracing at module load — we use OTEL + Langfuse.
set_tracing_disabled(disabled=True)

from services.common.interfaces import BaseAgent, Task, Result, AgentEvent
from services.common.interfaces import LLMClient, MCPClient, SessionStore, GuardrailRegistry

class SDKBackedAgent(BaseAgent):
    """
    Implements BaseAgent by delegating to the OpenAI Agents SDK.
    SDK imports are aliased to avoid collision with services.agents.*.
    """

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        tools: list,                    # wrapped via openai_function_tool
        llm_client: LLMClient,          # Our LLMClient — adapted to SDK internally
        mcp_client: MCPClient,          # Our MCPClient — SDK tools wrap these calls
        session_store: SessionStore,    # Our SessionStore — we bridge to SDK Session
        guardrails: GuardrailRegistry,
    ):
        self.name = name
        self._session_store = session_store
        self._guardrails = guardrails
        self._sdk_agent = OpenAIAgent(
            name=name,
            instructions=system_prompt,
            tools=tools,
            input_guardrails=[self._adapt_guardrail(g) for g in guardrails.input],
            output_guardrails=[self._adapt_guardrail(g) for g in guardrails.output],
            model=llm_client.model_name,     # vLLM-served model
        )

    async def run(self, task: Task) -> Result:
        sdk_session = await self._bridge_session(task.session_id)
        run_result = await OpenAIRunner.run(
            self._sdk_agent,
            input=task.prompt,
            session=sdk_session,
        )
        await self._persist_session(task.session_id, sdk_session)
        return self._to_result(task, run_result)

    async def run_streamed(self, task: Task):
        sdk_session = await self._bridge_session(task.session_id)
        async for sdk_event in OpenAIRunner.run_streamed(
            self._sdk_agent,
            input=task.prompt,
            session=sdk_session,
        ):
            yield self._to_agent_event(sdk_event)
        await self._persist_session(task.session_id, sdk_session)
```

### 3.3 Session Bridge

- Our `SessionStore` (Redis-backed) is the authoritative session store
- On `run` start, we load our `Session` from Redis and construct an SDK `Session` from it (feeding conversation history as initial messages)
- On `run` end, we extract the final message history from the SDK `Session` and persist back to our `SessionStore`
- The SDK's internal session state is ephemeral to the run

### 3.4 Guardrail Bridge

Our `Guardrail` protocol is authoritative. For each of our guardrails, we wrap it in the SDK's `input_guardrail` / `output_guardrail` decorator:

```python
def _adapt_guardrail(self, g: Guardrail):
    decorator = openai_input_guardrail if g.kind == "input" else openai_output_guardrail

    @decorator
    async def wrapped(ctx, agent, payload):
        decision = await g.check(payload)
        return GuardrailFunctionOutput(
            output_info={"decision": decision.verdict, "reason": decision.reason},
            tripwire_triggered=decision.verdict == "blocked",
        )
    return wrapped
```

The SDK invokes the wrapped guardrail at the same lifecycle points we'd invoke it ourselves. Audit log emission and OTEL span creation happen inside `g.check`, unchanged.

### 3.5 Tool Bridge

The SDK's `@function_tool` expects Python callables. Our MCP-backed tools become SDK tools via a thin adapter:

```python
def mcp_tool_as_sdk_tool(mcp_client: MCPClient, tool_spec: ToolSpec):
    @openai_function_tool(name=tool_spec.name, description=tool_spec.description)
    async def impl(**kwargs):
        result = await mcp_client.call_tool(tool_spec.name, kwargs)
        return result.content
    # SDK uses Pydantic model from tool_spec.input_schema for validation
    impl._schema = tool_spec.input_schema
    return impl
```

The MCP Gateway remains the source of truth for tool definitions; the SDK sees one wrapper per tool.

### 3.6 Event Translation

SDK stream events are translated to our `AgentEvent` taxonomy:

| SDK event | Our `AgentEvent.kind` |
|---|---|
| `RawResponsesStreamEvent` (token delta) | `partial_content` |
| `RunItemStreamEvent(tool_call_item)` | `tool_call` |
| `RunItemStreamEvent(tool_call_output_item)` | `tool_result` |
| `RunItemStreamEvent(message_output_item)` | accumulated into `partial_content` |
| `RunItemStreamEvent(guardrail_triggered)` | `error` with `{"kind": "guardrail", "name": ...}` |
| Run completed | `done` |

Sub-agent dispatch tools (`dispatch_to_<name>`) are regular SDK tools; their `partial_content` maps to our `dispatched` event.

---

## 4. Mapping SDK Concepts → Umbrella Concepts

| SDK concept | Umbrella concept | Notes |
|---|---|---|
| `Agent` | `BaseAgent` impl | Our adapter wraps the SDK `Agent` |
| `Runner.run` | `BaseAgent.run` | 1:1 |
| `Runner.run_streamed` | `BaseAgent.run_streamed` | With event translation |
| SDK `Session` | Our `SessionStore` | Ours is canonical; SDK's is in-run scratch |
| SDK `Guardrail` | Our `Guardrail` | Ours is canonical; SDK wraps ours |
| SDK `@function_tool` | `ToolSpec` from MCP | Thin adapter; MCP is source of truth |
| SDK `handoff_to` | Not used | Our composition is Redis Streams across processes, not intra-process |
| SDK `Sandbox Agent` | Not used | Code executor is deferred; when added, we use our own sandbox |

---

## 5. Known Divergences From Manual Variant

These are intentional, documented, and acceptable for a testbed. A behavior validated on the SDK variant should be verified on the manual variant before declaring it shippable.

| Divergence | Impact | Mitigation |
|---|---|---|
| Retry / timeout policy differs (SDK has its own; manual uses `tenacity`) | Latency profiles can differ | Parity tests (§6) assert final outcomes match, not timing |
| Tool-call parallelism may differ (SDK dispatches in parallel by default; manual can opt-in) | Different execution orders possible | Tests must tolerate equivalent orderings |
| SDK emits its own OTEL spans with different names | Dashboards may need SDK-aware filters during testbed work | Span attribute `agent.core=sdk` vs `agent.core=manual` added by adapter |
| SDK's `Session` semantics are richer (automatic history pruning, token-limit-aware truncation) | Our bridge only passes full history; very long sessions may hit different truncation thresholds | Cap history length in bridge (last N turns) to match manual behavior |
| SDK version upgrades can shift behavior silently | Test suite must re-run after SDK bumps | Pin SDK to `>=0.14.3,<0.15`; bump explicitly |

---

## 6. Parity Testing

A parity test suite lives under `evals/plumbing/parity/`. For each test case:

1. Build the same agent config twice — one `SDKBackedAgent`, one `ManualAgent`
2. Run the same `Task` through both
3. Assert:
   - `Result.status` matches
   - Same tools were called (names, not necessarily in same order)
   - Final content is semantically equivalent (tolerance via LLM-as-judge for free-form; exact for structured outputs)
   - Same guardrail decisions fired

Parity does **not** require identical latency, identical token counts, or identical event ordering.

---

## 7. Migration Path: SDK → Manual

When a behavior is ready to ship:

1. Port the system prompt verbatim — both variants accept the same text
2. Rebuild each SDK `@function_tool` as a Pydantic model + MCP tool (most already are; SDK tools were thin wrappers)
3. Port guardrails — they're already `Guardrail` protocol instances on our side; no work needed
4. Run parity tests — must pass before removing the SDK variant
5. Flip the agent's worker config from `core: sdk` to `core: manual`; restart

Expected porting effort per agent: **1–2 hours** once the manual core and MCP tools exist, because our abstraction layer already isolates the SDK.

---

## 8. Lifecycle Policy

- The SDK variant stays in the codebase as long as there is active agent prototyping happening
- It is **not** wired into any production Docker image
- At the point where all shipped agents are on the manual core and no new agent is being prototyped, the SDK variant can be removed entirely — it should take only a PR that deletes `agent_core_sdk.py` and the optional dependency

---

## 9. Observability (Testbed) — Langfuse

The SDK variant additionally integrates with **Langfuse**, an LLM-specific observability tool, to accelerate prompt and behavior iteration. This is **testbed-only**; the manual core does not touch Langfuse at all.

> **Version note:** Langfuse's Python SDK was rewritten on top of OpenTelemetry starting with v3. The API shown here targets v3+ (`get_client`, `start_as_current_observation`, `current_trace_span().update_trace(...)`). The legacy v2 `langfuse_context` / `langfuse.decorators.langfuse_context` import path is **not** used.

### 9.1 Why Langfuse Here and Not Everywhere

- OTEL remains the system-wide tracing backbone (covers Redis Streams, MCP Gateway, Postgres, HTTP — things Langfuse does not)
- Langfuse is specialized: prompt/completion/tool-call views, session-aware quality signals, side-by-side prompt comparison, dataset-backed run grading
- During testbed work, developers iterate on prompts and want LLM-focused ergonomics the OTEL+Jaeger pairing does not give them
- Coupling this to the SDK variant keeps production dependency-free

### 9.2 Optional Dependency

```toml
# services/agents/pyproject.toml (testbed extra — extends sdk-testbed)
[project.optional-dependencies]
sdk-testbed = [
  "openai-agents>=0.14.3,<0.15",
  "langfuse>=3.0,<4",   # OTEL-based SDK; LLM-specific observability (testbed only)
]
```

> **Version check at implementation time.** Verify current Langfuse Python SDK version on [PyPI](https://pypi.org/project/langfuse) and adjust the pin. If v4 has reached stable and the API surface we use below (`get_client`, `start_as_current_observation`, `current_trace_span().update_trace`) is unchanged or forward-compatible, widening the pin to `>=3.0,<5` is acceptable.

Production `uv sync --no-group sdk-testbed` excludes Langfuse. A CI guard asserts the production image has zero reachable `langfuse` imports.

### 9.3 Initialization

Langfuse is initialized once per worker process using environment-variable credentials. We let `get_client()` read the env rather than passing keys explicitly, so testbed and developer environments behave identically:

```python
# services/agents/base/observability_testbed.py
import os
from langfuse import Langfuse, get_client

_langfuse: Langfuse | None = None

def init_langfuse_if_enabled() -> Langfuse | None:
    """Called once at worker startup. Returns None if disabled."""
    global _langfuse
    if os.environ.get("LANGFUSE_ENABLED", "false").lower() != "true":
        return None
    if _langfuse is not None:
        return _langfuse
    # Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
    _langfuse = get_client()
    # Sanity check; raises if credentials are wrong. Testbed-only, so fail fast.
    _langfuse.auth_check()
    return _langfuse

def get_langfuse() -> Langfuse | None:
    return _langfuse
```

### 9.4 Wiring Into `SDKBackedAgent`

```python
# services/agents/base/agent_core_sdk.py  (additions)
from services.agents.base.observability_testbed import get_langfuse

class SDKBackedAgent(BaseAgent):
    async def run(self, task: Task) -> Result:
        lf = get_langfuse()
        if lf is None:
            return await self._run_inner(task)

        # Langfuse v3 is OTEL-based; start_as_current_observation creates an
        # OTEL span that Langfuse automatically captures.
        with lf.start_as_current_observation(
            as_type="span",
            name=f"agent.run/{self.name}",
            input={"prompt": task.prompt, "context": task.context},
        ) as span:
            lf.current_trace_span().update_trace(
                user_id=task.user_id,
                session_id=task.session_id,
                metadata={"agent.core": "sdk", "task_id": task.task_id},
                tags=[f"agent:{self.name}"],
            )
            try:
                result = await self._run_inner(task)
                span.update(output={"content": result.content, "status": result.status})
                return result
            except Exception as e:
                span.update(level="ERROR", status_message=str(e))
                raise
```

`run_streamed` follows the same pattern: wrap the stream body in `start_as_current_observation`, call `update_trace` once, and update the span on terminal event.

### 9.5 Trace Shape

A Langfuse trace mirrors an agent run:

- **Trace name:** `agent.run/<agent_name>`
- **User ID:** `task.user_id` (via `update_trace(user_id=...)`)
- **Session ID:** `task.session_id` — groups all agent runs by chat session in the Langfuse UI
- **Tags:** `["agent:<name>"]`
- **Metadata:** `{agent.core: "sdk", task_id, model, ...}`
- **Generations:** one per LLM call, with input/output messages and token counts. For the OpenAI Agents SDK, set `as_type="generation"` around the LLM dispatch point (the SDK's internal dispatcher).
- **Spans:** one per tool call, with arguments + result
- **Score events:** optional, emitted by guardrails (e.g., `langfuse.score(name="guardrail.verdict", value=..., trace_id=...)`)

### 9.6 Relationship to OTEL

Because Langfuse v3 is OTEL-native, **trace-ID correlation is automatic** when OTEL is already configured in the process. We do not need to manually copy the OTEL `trace_id` into Langfuse. Rules:

- Initialize OTEL (Jaeger exporter) **first** at process startup
- Initialize Langfuse **after** OTEL — it attaches to the running OTEL tracer
- Any span created via `lf.start_as_current_observation(...)` shows up in *both* Jaeger and Langfuse with the same trace ID
- Developers can paste a trace ID from one UI into the other

If OTEL is disabled (unusual), Langfuse still works standalone; correlation is just lost.

### 9.7 Error Handling and Back-Pressure

- `auth_check()` at init is the only blocking call. After that, span operations are buffered and flushed asynchronously by the SDK.
- If Langfuse backend is unreachable mid-run, the SDK drops events and logs locally — **the agent run is never blocked or failed by Langfuse outages**.
- On clean worker shutdown, call `lf.flush()` to drain pending events. SIGTERM handler in the run-worker does this.

### 9.8 Configuration

```env
# .env (testbed profile only)
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://langfuse.internal
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

Production `.env` either omits these or sets `LANGFUSE_ENABLED=false`. The env loader **hard-fails a production build that has Langfuse enabled** (startup assertion: `assert not (env.is_production and env.langfuse_enabled)`).

### 9.9 Out of Scope for v1.2

- Pushing evaluation datasets from Langfuse into DeepEval suites (manual export for now)
- Langfuse prompt management as the source of truth for system prompts (prompts stay in code under `services/agents/<agent>/prompts/`)
- Any production agent depending on Langfuse being available at runtime

---

*End of Document*

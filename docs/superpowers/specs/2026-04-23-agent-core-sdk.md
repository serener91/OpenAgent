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

### 3.2 Class Layout

```python
# services/agents/base/agent_core_sdk.py
from agents import Agent as SDKAgent, Runner
from agents import function_tool, Session as SDKSession, input_guardrail, output_guardrail

from services.common.interfaces import BaseAgent, Task, Result, AgentEvent
from services.common.interfaces import LLMClient, MCPClient, SessionStore, GuardrailRegistry

class SDKBackedAgent(BaseAgent):
    """
    Implements BaseAgent by delegating to the OpenAI Agents SDK.
    """

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        tools: list,                    # SDK @function_tool definitions
        llm_client: LLMClient,          # Our LLMClient — adapted to SDK internally
        mcp_client: MCPClient,          # Our MCPClient — SDK tools wrap these calls
        session_store: SessionStore,    # Our SessionStore — we bridge to SDK Session
        guardrails: GuardrailRegistry,
    ):
        self.name = name
        self._session_store = session_store
        self._guardrails = guardrails
        self._sdk_agent = SDKAgent(
            name=name,
            instructions=system_prompt,
            tools=tools,
            input_guardrails=[self._adapt_guardrail(g) for g in guardrails.input],
            output_guardrails=[self._adapt_guardrail(g) for g in guardrails.output],
            model=llm_client.model_name,     # vLLM-served model
        )

    async def run(self, task: Task) -> Result:
        sdk_session = await self._bridge_session(task.session_id)
        run_result = await Runner.run(
            self._sdk_agent,
            input=task.prompt,
            session=sdk_session,
        )
        await self._persist_session(task.session_id, sdk_session)
        return self._to_result(task, run_result)

    async def run_streamed(self, task: Task):
        sdk_session = await self._bridge_session(task.session_id)
        async for sdk_event in Runner.run_streamed(
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
    @input_guardrail  # or output_guardrail based on g.kind
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
    @function_tool(name=tool_spec.name, description=tool_spec.description)
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
  "langfuse>=2.50,<3",   # LLM-specific observability (testbed only)
]
```

Production `uv sync --no-group sdk-testbed` excludes both. A CI job asserts the production image has zero `langfuse` imports reachable.

### 9.3 Wiring

```python
# services/agents/base/agent_core_sdk.py (additions)
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

_langfuse: Langfuse | None = None

def _maybe_init_langfuse(settings) -> Langfuse | None:
    if not settings.langfuse_enabled:
        return None
    return Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )

class SDKBackedAgent(BaseAgent):
    def __init__(self, *, name, ..., settings):
        ...
        self._langfuse = _maybe_init_langfuse(settings)

    async def run(self, task: Task) -> Result:
        if self._langfuse:
            langfuse_context.update_current_trace(
                name=f"agent.run/{self.name}",
                user_id=task.user_id,
                session_id=task.session_id,
                metadata={"agent.core": "sdk", "task_id": task.task_id},
            )
        return await self._run_inner(task)
```

The `@observe` decorator is applied to LLM call and tool call sites — already instrumented by the SDK's own Langfuse integration in most cases; we add a top-level trace annotation to propagate `user_id`/`session_id`.

### 9.4 Trace Shape

A Langfuse trace mirrors an agent run:

- **Trace name:** `agent.run/<agent_name>`
- **User id:** `task.user_id`
- **Session id:** `task.session_id` — lets Langfuse group all runs by chat session
- **Metadata:** `{agent.core: sdk, task_id, model, ...}`
- **Generations:** one per LLM call, with input/output messages and token counts
- **Spans:** one per tool call, with arguments + result
- **Score events:** optional, emitted by guardrails (e.g., `guardrail.verdict`)

### 9.5 Relationship to OTEL

- OTEL and Langfuse both receive the same logical events
- Trace correlation: we set Langfuse's `trace_id` to match OTEL's `trace_id` via `langfuse_context.update_current_trace(id=otel_trace_id)` so developers can jump from Jaeger to Langfuse and vice versa
- **If Langfuse is unreachable or disabled, the agent continues unaffected** — all Langfuse calls are non-blocking with timeouts, and errors are logged but swallowed

### 9.6 Configuration

```env
# .env (testbed profile only)
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://langfuse.internal
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

Production `.env` either omits these or sets `LANGFUSE_ENABLED=false`. The env loader hard-fails a production build that has Langfuse enabled.

### 9.7 Out of Scope for v1.2

- Pushing evaluation datasets from Langfuse into DeepEval suites (manual export for now)
- Langfuse prompt management as the source of truth for system prompts (prompts stay in code under `services/agents/<agent>/prompts/`)
- Any production agent depending on Langfuse being available at runtime

---

*End of Document*

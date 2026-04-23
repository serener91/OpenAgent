# Agent Core — Manual Variant (Production)

**Document Version:** 1.0
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Parent:** `2026-04-23-multi-agent-system-design-v1.2.md`
**Peer:** `2026-04-23-agent-core-sdk.md` (testbed)

> **Production path.** This is the agent core used for all shipped agents. It has no framework dependency beyond `openai` (for the Chat Completions API, served by vLLM), `fastmcp` (client side, to reach the MCP Gateway), `tenacity` (retries), and the OTEL SDK.

---

## 1. Purpose

A hand-rolled agent loop, ~400 lines of Python, that implements the `BaseAgent` protocol. Every shipped agent — orchestrator included — runs on this core. No framework lock-in, no SDK upgrade treadmill, every line auditable.

---

## 2. Design Constraints

| Constraint | Implication |
|---|---|
| Must implement `BaseAgent` exactly | Drop-in swap with SDK variant |
| No framework imports except `openai`, `fastmcp`, `tenacity`, OTEL | Framework independence is the whole point |
| Streaming is first-class (not bolted on) | SSE requires token-granular events |
| Parallel tool calls supported (opt-in per agent config) | LLMs can call multiple tools per turn; we execute them concurrently |
| All I/O async | Orchestrator is FastAPI; agents are async workers |
| Deterministic behavior given fake `LLMClient` | Required by Layer 1 eval suite |

---

## 3. File Layout

```
services/agents/base/
├── agent_core_manual.py      # ManualAgent class
├── llm_client.py             # LLMClient protocol + OpenAIChatClient impl
├── mcp_client.py             # MCPClient protocol + FastMCPClient impl
├── tool_schema.py            # Pydantic → OpenAI tool spec converter
├── retry.py                  # tenacity wrappers
└── worker.py                 # Redis Streams consumer loop (reused across agents)
```

---

## 4. `ManualAgent` Implementation Sketch

```python
# services/agents/base/agent_core_manual.py
from typing import AsyncIterator
from opentelemetry import trace
from tenacity import retry, stop_after_attempt, wait_exponential

from services.common.interfaces import (
    BaseAgent, Task, Result, AgentEvent, ToolCall,
    LLMClient, MCPClient, SessionStore, GuardrailRegistry,
)
from services.agents.base.tool_schema import build_openai_tool_specs

class ManualAgent(BaseAgent):
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        tools: list,                         # list[ToolSpec] with pydantic input_schema
        llm_client: LLMClient,
        mcp_client: MCPClient,
        session_store: SessionStore,
        guardrails: GuardrailRegistry,
        max_iterations: int = 10,
        parallel_tool_calls: bool = True,
        model: str,
        tracer: trace.Tracer,
    ):
        self.name = name
        self._system_prompt = system_prompt
        self._tools = tools
        self._tool_specs = build_openai_tool_specs(tools)   # OpenAI-format schemas
        self._tool_by_name = {t.name: t for t in tools}
        self._llm = llm_client
        self._mcp = mcp_client
        self._sessions = session_store
        self._guardrails = guardrails
        self._max_iterations = max_iterations
        self._parallel_tool_calls = parallel_tool_calls
        self._model = model
        self._tracer = tracer

    async def run(self, task: Task) -> Result:
        final: Result | None = None
        async for event in self.run_streamed(task):
            if event.kind == "done":
                final = Result(**event.data)
            elif event.kind == "error":
                final = Result(task_id=task.task_id, status="failed",
                               content=None, error=event.data.get("message"))
        assert final is not None
        return final

    async def run_streamed(self, task: Task) -> AsyncIterator[AgentEvent]:
        with self._tracer.start_as_current_span(f"agent.run") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("agent.core", "manual")
            span.set_attribute("session.id", task.session_id)
            span.set_attribute("user.id", task.user_id)

            # Load conversation history, build initial messages
            session = await self._sessions.load(task.session_id)
            messages = [
                {"role": "system", "content": self._system_prompt},
                *session.history,
                {"role": "user", "content": task.prompt},
            ]

            tool_calls_recorded: list[ToolCall] = []
            prompt_tokens_total = 0
            completion_tokens_total = 0

            for iteration in range(self._max_iterations):
                yield AgentEvent(kind="thinking", data={"iteration": iteration})

                resp = await self._call_llm(messages)
                prompt_tokens_total += resp.usage.prompt_tokens
                completion_tokens_total += resp.usage.completion_tokens

                msg = resp.choices[0].message

                if not msg.tool_calls:
                    # Terminal answer
                    final_content = msg.content or ""
                    if final_content:
                        yield AgentEvent(kind="partial_content",
                                         data={"delta": final_content})
                    await self._persist_turn(task, session, final_content)
                    yield AgentEvent(kind="done", data={
                        "task_id": task.task_id,
                        "status": "completed",
                        "content": final_content,
                        "tool_calls": [tc.model_dump() for tc in tool_calls_recorded],
                        "tokens": {
                            "prompt": prompt_tokens_total,
                            "completion": completion_tokens_total,
                        },
                    })
                    return

                # Tool calls requested
                messages.append(msg.model_dump())

                # Execute tool calls (parallel or sequential)
                async def _run_one(tc):
                    yield_events = []
                    yield_events.append(AgentEvent(
                        kind="tool_call",
                        data={"name": tc.function.name,
                              "arguments": tc.function.arguments,
                              "id": tc.id},
                    ))
                    result_data, error = await self._execute_tool(tc)
                    call_record = ToolCall(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                        result=result_data if not error else None,
                        error=error,
                    )
                    tool_calls_recorded.append(call_record)
                    yield_events.append(AgentEvent(
                        kind="tool_result",
                        data={"id": tc.id,
                              "result": result_data,
                              "error": error},
                    ))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result_data) if not error else f"ERROR: {error}",
                    })
                    return yield_events

                if self._parallel_tool_calls and len(msg.tool_calls) > 1:
                    buckets = await asyncio.gather(*[_run_one(tc) for tc in msg.tool_calls])
                    for events in buckets:
                        for e in events:
                            yield e
                else:
                    for tc in msg.tool_calls:
                        events = await _run_one(tc)
                        for e in events:
                            yield e

            # Hit max_iterations without terminal answer
            yield AgentEvent(kind="error", data={
                "message": f"max_iterations ({self._max_iterations}) exceeded"
            })

    # -- internals -----------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _call_llm(self, messages):
        return await self._llm.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=self._tool_specs,
            parallel_tool_calls=self._parallel_tool_calls,
        )

    async def _execute_tool(self, tc) -> tuple[dict | None, str | None]:
        tool = self._tool_by_name.get(tc.function.name)
        if tool is None:
            return None, f"unknown tool: {tc.function.name}"
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError as e:
            return None, f"malformed tool arguments: {e}"

        # Tool-level guardrail (pre-call parameter validation + policy)
        g_decision = await self._guardrails.tool.check({
            "agent": self.name, "tool": tc.function.name, "args": args,
        })
        if g_decision.verdict == "blocked":
            return None, f"guardrail blocked: {g_decision.reason}"

        # Dispatch: MCP Gateway for ordinary tools, or inline for in-process tools
        # (dispatch_to_* tools are registered as in-process callables on the orchestrator)
        if tool.kind == "mcp":
            result = await self._mcp.call_tool(tc.function.name, args)
            return result.content, None
        elif tool.kind == "inprocess":
            return await tool.invoke(args), None
        else:
            return None, f"unknown tool kind: {tool.kind}"

    async def _persist_turn(self, task: Task, session, final_content: str):
        session.history.append({"role": "user", "content": task.prompt})
        session.history.append({"role": "assistant", "content": final_content})
        await self._sessions.save(task.session_id, session)
```

This sketch is illustrative — the real implementation will separate concerns more (tool dispatch, event generation, LLM call wrapper). LOC target: **~400 in `agent_core_manual.py`**, plus ~100 across `tool_schema.py`, `retry.py`, `llm_client.py`.

---

## 5. Tool Schema Generation

```python
# services/agents/base/tool_schema.py
from pydantic import BaseModel

class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: type[BaseModel]        # Pydantic class
    kind: str                            # "mcp" | "inprocess"
    invoke: object | None = None         # callable for inprocess

def build_openai_tool_specs(tools: list[ToolSpec]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema.model_json_schema(),
            },
        }
        for t in tools
    ]
```

The orchestrator's `dispatch_to_<name>` tools are built as `ToolSpec(kind="inprocess", invoke=...)` at startup, with `input_schema` a generated Pydantic model matching `(task, ctx)`.

---

## 6. Retry Policy

`tenacity` wraps the LLM call:

- 3 attempts
- exponential backoff (1s → 10s)
- retry on `openai.APITimeoutError`, `openai.APIConnectionError`, `openai.RateLimitError`
- do **not** retry on 4xx other than rate-limit (model errors are not transient)

Tool calls via MCP do **not** retry at the agent level — the MCP Gateway handles transient MCP-server failures. An agent sees either a success or a terminal error and decides (via LLM) whether to try a different tool.

---

## 7. Streaming

The loop yields events token-by-token is **not** the design. It yields event-by-event: `thinking`, `tool_call`, `tool_result`, then a single `partial_content` containing the final answer.

**Why not token streaming?**
- vLLM supports streaming, but agent loops with tool calls are not naturally token-streamable — the LLM commits to "use tool X" or "answer with Y" atomically
- Token streaming within the final answer turn is a future enhancement (set `stream=True` on the terminal LLM call, yield deltas). Deferred to when UI need arises.

**What streams today:** events are emitted as they happen. The orchestrator forwards these directly to SSE. Clients see progress ("calling tool X", "received result") in near real time.

---

## 8. OTEL Instrumentation

| Span | Parent | Attributes |
|---|---|---|
| `agent.run` | inherited from caller | `agent.name`, `agent.core=manual`, `session.id`, `user.id`, `task.id` |
| `llm.chat.completion` | `agent.run` | `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `iteration` |
| `tool.call` | `agent.run` | `tool.name`, `tool.kind`, `tool.duration_ms` |
| `mcp.gateway.execute_tool` | `tool.call` (when `tool.kind=mcp`) | `mcp.server`, `mcp.tool` |
| `guardrail.tool.check` | `tool.call` | `guardrail.name`, `guardrail.decision` |

Trace context propagates into Redis Streams messages (task metadata carries `traceparent`), so orchestrator → sub-agent traces stitch together.

---

## 9. Integration Points

### 9.1 SessionStore (from `services/common`)

The agent doesn't know or care that sessions live in Redis. It calls `await session_store.load(session_id)` and `await session_store.save(session_id, session)`. Fake implementation for tests: in-memory dict.

### 9.2 MCPClient (from `services/common`)

FastMCP client wrapping the MCP Gateway HTTP/SSE endpoint. Fake for tests: dict of `name → callable`.

### 9.3 LLMClient

```python
class LLMClient(Protocol):
    model_name: str
    chat: ChatCompletions  # OpenAI-compatible
```

Production impl: `openai.AsyncOpenAI(base_url=vllm_url)`. Fake for tests: returns canned responses keyed by `(system_prompt_hash, user_prompt)`.

### 9.4 GuardrailRegistry

Exposes `.input`, `.tool`, `.output` (list of `Guardrail` impls). Agent invokes `.tool.check(...)` before each tool execution. Input/output guardrails are invoked by the orchestrator, not the sub-agent.

---

## 10. Worker Wrapper

All sub-agents run inside a shared worker wrapper that consumes from Redis Streams. The agent itself doesn't know about Redis.

```python
# services/agents/base/worker.py (sketch)
async def run_worker(agent: BaseAgent, redis, group: str, consumer: str):
    stream = f"stream:agent:{agent.name}"
    result_stream = f"stream:agent:{agent.name}:results"

    try:
        await redis.xgroup_create(stream, group, mkstream=True, id="$")
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):   # group already exists is fine
            raise

    while True:
        entries = await redis.xreadgroup(
            groupname=group, consumername=consumer,
            streams={stream: ">"}, count=1, block=30_000,
        )
        for _stream_name, messages in entries or []:
            for msg_id, fields in messages:
                task = Task.model_validate_json(fields[b"task"])
                try:
                    result = await agent.run(task)
                except Exception as e:
                    result = Result(task_id=task.task_id, status="failed",
                                    content=None, error=str(e))
                await redis.xadd(result_stream, {
                    "task_id": task.task_id,
                    "result": result.model_dump_json(),
                })
                await redis.xack(stream, group, msg_id)
```

The same wrapper runs the orchestrator too — except its "stream" is the HTTP request handler rather than Redis.

---

## 11. Testing Approach

### 11.1 Layer 1 (plumbing, deterministic)

- Fake `LLMClient` returns scripted responses: `[{"tool_calls": [...]}, {"content": "..."}]`
- Fake `MCPClient` returns canned tool results
- Tests assert: correct number of LLM calls, correct tool selection, correct message threading, guardrail invocation points, retry behavior on transient errors, `max_iterations` enforcement, malformed tool arguments handled gracefully

### 11.2 Property tests

- Arbitrary tool-call sequences terminate or hit `max_iterations`
- Any LLM error surface surfaces as `Result(status="failed")` (never raises)

### 11.3 Integration (real vLLM)

Under Layer 2 (DeepEval). Out of scope for this doc.

---

## 12. Known Limitations / Future Work

| Area | Current | Future |
|---|---|---|
| Token streaming inside final answer | Not supported | `stream=True` on terminal LLM call; yield deltas |
| History truncation | Naïve (unbounded until session cap) | Token-aware rolling window |
| Tool-result caching | None | Per-session memoization for idempotent tools |
| Structured final outputs | Free-form `content` | Pydantic response model, JSON mode |
| Multi-modal inputs | Text only | Image inputs when agents need them |
| Interruption | Not supported | WebSocket-based cancel; currently task runs to completion |

---

## 13. Success Criteria for v1.2

- [ ] `ManualAgent` implements `BaseAgent` per umbrella §5
- [ ] Layer 1 plumbing tests cover: happy path, tool-call loop, guardrail blocks, retries, malformed args, max_iterations
- [ ] `orchestrator_agent.py` successfully built on `ManualAgent`
- [ ] `file_agent` successfully built on `ManualAgent`
- [ ] Parity tests (vs SDK variant) pass for a minimal test matrix
- [ ] OTEL spans present with full attribute set
- [ ] Under 500 LOC across the manual-core files

---

*End of Document*

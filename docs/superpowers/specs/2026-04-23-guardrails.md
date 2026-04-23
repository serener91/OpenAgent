# Guardrails

**Document Version:** 1.0
**Date:** 2026-04-23
**Status:** Draft — Pending Review
**Parent:** `2026-04-23-multi-agent-system-design-v1.2.md`

---

## 1. Purpose

Define the guardrail system for v1.2: the interface every guardrail implements, where guardrails run, which guardrails ship in v1.2, and how their decisions are audited.

Guardrails exist to enforce safety, policy, and correctness invariants that must not depend on LLM good behavior. They are the deterministic layer around the non-deterministic agent.

---

## 2. Scope

### 2.1 In scope for v1.2

| Category | Examples |
|---|---|
| **Input guardrails** | Prompt-injection patterns, PII in user prompts, language/locale check, message length limits |
| **Tool guardrails** | Per-agent tool allowlist, parameter validation, per-user tool access policy |
| **Jailbreak/abuse scoring** | Rolling per-user abuse score, auto-suspend at threshold |

### 2.2 Deferred to v1.3

- **Output guardrails** — PII scrubbing in responses, citation enforcement, hallucination flagging, factuality checks.
  Reason: output guardrails that actually work require real traffic and failure examples to calibrate. Shipping naïve output guardrails does more harm (false positives in customer responses) than good. Defer until we have data.

### 2.3 Out of scope permanently

- **Prompt rewriting** ("safer" rewrites of user input) — treats symptom, not cause
- **LLM-as-judge for every message** — cost and latency unacceptable at 100+ users

---

## 3. The `Guardrail` Protocol

One interface. All guardrails — rule-based, regex, classifier, LLM-backed — implement the same shape.

```python
# services/common/interfaces.py
from typing import Protocol, Literal
from pydantic import BaseModel

class GuardrailDecision(BaseModel):
    verdict: Literal["allowed", "flagged", "blocked"]
    reason: str | None = None
    metadata: dict = {}

class Guardrail(Protocol):
    name: str                    # stable identifier, e.g., "prompt_injection_v1"
    kind: Literal["input", "tool", "output"]
    async def check(self, payload: dict) -> GuardrailDecision: ...

class GuardrailRegistry(Protocol):
    input:  list[Guardrail]
    tool:   list[Guardrail]
    output: list[Guardrail]
```

### 3.1 Verdict Semantics

| Verdict | Meaning | Downstream behavior |
|---|---|---|
| `allowed` | No action needed | Continue |
| `flagged` | Warning logged; decision may influence later guardrails (e.g., abuse score) | Continue, but emit audit event |
| `blocked` | Hard stop | Return error to caller; emit audit event; increment abuse score |

Guardrails are pure functions of their input plus their configured policy. No side effects on state — audit emission is done by the caller (orchestrator / agent) based on the decision returned.

### 3.2 Composition

Multiple guardrails may run on the same payload. Execution is **in configured order, short-circuit on first `blocked`**. `flagged` results accumulate — all are emitted to audit, any of them can be used by downstream logic.

---

## 4. Execution Locations

Defense in depth: each layer enforces what it uniquely sees.

| Layer | Guardrails run | Reason |
|---|---|---|
| **Orchestrator** (input) | Prompt injection, PII detection, language check, message length, jailbreak score lookup | It's the user-facing boundary; wraps every incoming message |
| **Agent (sub-agent or orchestrator itself)** (tool) | Tool allowlist, parameter validation | Agent is what actually *constructs* the tool call |
| **MCP Gateway** (tool) | Per-user tool access policy, egress rules, rate limits per tool | Gateway sees every tool *invocation* regardless of which agent made it |

The same `Guardrail` protocol is used across all three layers.

### 4.1 Flow

```
User ─► Orchestrator
          │
          ├─► GuardrailRegistry.input.check(user_prompt)
          │     └─► if blocked: return 400 to user, emit audit
          │
          ├─► Orchestrator agent loop
          │     │
          │     ├─► LLM decides to call tool
          │     ├─► GuardrailRegistry.tool.check({agent, tool, args})   ← agent-local
          │     │     └─► if blocked: tell LLM "guardrail refused", let it adapt
          │     │
          │     └─► MCP Gateway receives tool call
          │           ├─► Gateway-side guardrails (policy + egress + rate limit)
          │           │     └─► if blocked: return error to agent
          │           └─► Forward to MCP server
          │
          └─► Response to user
```

---

## 5. Built-in Guardrails for v1.2

### 5.1 Input guardrails (on orchestrator)

| Name | Implementation | Config |
|---|---|---|
| `message_length_v1` | Pure Python; counts tokens via `tiktoken`-style approximation | `max_tokens` (default 4000) |
| `language_v1` | `langdetect` library | `allowed_languages` list (default `["en", "ko"]`); `flagged` if outside |
| `prompt_injection_v1` | Rule set: regex patterns for known injection phrases (`"ignore previous"`, `"you are now"`, `"system:"` impersonation, direct-tool-invocation attempts) | `pattern_file` path, `block_threshold` score |
| `pii_input_v1` | Regex + Presidio (if available) for emails, phone numbers, national IDs, credit cards | `block_categories` (default `["credit_card", "national_id"]`; others `flagged`) |
| `abuse_score_gate_v1` | Reads `abuse_score:{user_id}` from Redis; blocks if above threshold | `block_threshold` (default 100) |

**`prompt_injection_v1` specifics:** pattern list in `services/orchestrator/guardrails/patterns/prompt_injection.yaml`. Patterns are versioned. Falsely blocked messages can appeal via a separate admin flow (deferred). Expect false positives at ~1–2% initially; tune on real traffic.

### 5.2 Tool guardrails (on agents)

| Name | Implementation | Config |
|---|---|---|
| `tool_allowlist_v1` | Consults agent's Postgres registry entry (`tool_allowlist` JSONB). Block if requested tool not listed. | per-agent |
| `tool_args_schema_v1` | Validates args against tool's Pydantic schema. Blocks on malformed args (vs returning error to LLM — design choice: blocking is clearer in audit). | per-tool |

### 5.3 Tool guardrails (on MCP Gateway)

| Name | Implementation | Config |
|---|---|---|
| `user_tool_access_v1` | Per-user scope check. A user's API key scopes specify which tools they can access transitively through any agent. | API key scope JSONB |
| `egress_allowlist_v1` | For tools that make outbound network calls: URL allowlist. Block non-allowlisted domains. | per-MCP-server config |
| `tool_rate_limit_v1` | Redis sliding window per `(user_id, tool_name)`. | per-tool RPM |

### 5.4 Jailbreak / abuse scoring

Not a guardrail in the `Guardrail` protocol sense — it's a **side effect** of blocked decisions.

- Every `blocked` verdict (from any guardrail) increments `abuse_score:{user_id}` in Redis (default: +10)
- `flagged` verdicts from `prompt_injection_v1` or `pii_input_v1` also increment (default: +3)
- Score has TTL 24h (rolling window)
- `abuse_score_gate_v1` (input guardrail, see §5.1) reads this score and blocks at threshold
- Threshold breach also inserts a row in Postgres `user_abuse_events` for ops review

---

## 6. Audit Log

### 6.1 What gets logged

Every guardrail decision (regardless of verdict) produces:

- An OTEL span `guardrail.{kind}.check` with attributes `guardrail.name`, `guardrail.decision`, `guardrail.reason`, `user.id`, `session.id`
- A Redis Stream event on `audit:guardrails` with the same fields plus timestamp
- For `blocked` only: a Postgres row in `audit_guardrail_blocks` for durable record

### 6.2 Postgres schema

```sql
CREATE TABLE audit_guardrail_blocks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id          VARCHAR(255),
    session_id       VARCHAR(255),
    guardrail_name   VARCHAR(128) NOT NULL,
    guardrail_kind   VARCHAR(16)  NOT NULL,
    reason           TEXT,
    metadata         JSONB,
    trace_id         VARCHAR(64)
);

CREATE INDEX idx_audit_guardrail_blocks_user_time
    ON audit_guardrail_blocks (user_id, occurred_at DESC);
```

### 6.3 Retention

- Redis stream: 7 days (`MAXLEN ~ 1_000_000` approximate trim)
- Postgres audit table: 180 days, partition by month (manual dropping in v1.2; automated in deployment spec)

---

## 7. Configuration

### 7.1 Per-orchestrator config

```yaml
# services/orchestrator/guardrails/config.yaml
input:
  - name: message_length_v1
    config: { max_tokens: 4000 }
  - name: language_v1
    config: { allowed_languages: [en, ko] }
  - name: prompt_injection_v1
    config: { pattern_file: patterns/prompt_injection.yaml, block_threshold: 0.8 }
  - name: pii_input_v1
    config: { block_categories: [credit_card, national_id], flag_categories: [email, phone] }
  - name: abuse_score_gate_v1
    config: { block_threshold: 100 }
```

### 7.2 Per-agent config

```yaml
# services/agents/file_agent/guardrails.yaml
tool:
  - name: tool_allowlist_v1   # allowlist comes from Postgres registry, no extra config
  - name: tool_args_schema_v1
```

### 7.3 Per-MCP-server config

```yaml
# services/mcp_gateway/mcp_servers/web_search/guardrails.yaml
tool:
  - name: egress_allowlist_v1
    config:
      allowed_domains:
        - "*.wikipedia.org"
        - "docs.*.internal"
  - name: tool_rate_limit_v1
    config: { per_user_rpm: 20, per_tool_rpm_global: 200 }
```

### 7.4 Hot reload

- v1.2: config is read at process start. Reload via process restart.
- v1.3+: watch config files + apply without restart (deferred).

---

## 8. Failure Modes

### 8.1 Guardrail raises an exception

- Treated as `blocked` with `reason="guardrail_error"`, error logged
- Fail-closed posture: if we can't check, we don't pass
- Exception to fail-closed: `language_v1` (flaky `langdetect`) — if it errors, treat as `allowed` and emit `flagged` with reason. Language mismatch is low-stakes.

### 8.2 Redis unavailable (for `abuse_score_gate_v1`)

- Fall back to `allowed` (fail-open), emit `flagged` with reason `"abuse_score_unavailable"`
- Rationale: Redis outage would otherwise block 100% of traffic; better to temporarily skip one guardrail

### 8.3 Pattern/schema file missing

- Refuse to start the service. Don't start without your guardrails loaded.

---

## 9. Testing

### 9.1 Unit tests (Layer 1)

For each guardrail:
- Positive: known `allowed` inputs return `allowed`
- Negative: known `blocked` inputs return `blocked`
- Edge: empty payload, extremely long input, unicode, homoglyphs (for injection patterns)

### 9.2 Integration tests

- End-to-end: user sends prompt → orchestrator → expected verdict → expected HTTP response (200 or 400)
- Redis-dependent: `abuse_score_gate_v1` increments and blocks at threshold

### 9.3 Accuracy evals (Layer 2)

- `evals/quality/guardrails/` — curated dataset of labeled prompts
- Metrics: precision, recall, F1 per guardrail
- Run nightly; report deltas when patterns change

### 9.4 Red-team corpus

A file `evals/datasets/prompt_injection_attacks.yaml` contains known jailbreak attempts (from public datasets + internally curated). CI refuses to regress — if a newly added prompt fails to trigger `prompt_injection_v1`, the test fails until the pattern set is updated.

---

## 10. OTEL & Metrics

### 10.1 Spans

- `guardrail.input.check` — attributes: `guardrail.name`, `guardrail.decision`, `guardrail.reason`
- `guardrail.tool.check` — same attributes plus `tool.name`, `agent.name`
- `guardrail.output.check` — reserved for v1.3

### 10.2 Prometheus metrics

| Metric | Type | Labels |
|---|---|---|
| `guardrail_checks_total` | Counter | `name`, `kind`, `decision` |
| `guardrail_check_duration_seconds` | Histogram | `name`, `kind` |
| `guardrail_errors_total` | Counter | `name` |
| `user_abuse_score` | Gauge | `user_id` (careful with cardinality — consider sampling) |

Cardinality note: `user_abuse_score` per-user is fine for hundreds of users; if it grows, switch to a gauge of top-N or histogram.

---

## 11. Future Work (v1.3+)

- **Output guardrails** (PII scrubbing on responses, citation enforcement, hallucination flags)
- **ML-based PII classifier** (replace regex-only for better recall on noisy inputs)
- **Jailbreak classifier** (small distilled model; replace rule-based when false-positive rate becomes limiting)
- **Appeal flow** for users incorrectly blocked
- **Configurable per-tenant guardrails** (once multi-tenancy lands)
- **Hot reload of config**

---

*End of Document*

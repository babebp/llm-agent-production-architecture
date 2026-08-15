# ADR-0004: Langfuse Cloud for observability instead of self-hosting

Status: accepted

## Context

We want full LLM observability: traces per agent run, per-step latency,
token usage, and cost. Langfuse v3 self-hosted requires Postgres,
ClickHouse, Redis, and S3-compatible storage — four stateful services that
would dominate this compose file while adding no architectural signal.

## Decision

Use Langfuse Cloud (free tier). The agent attaches the Langfuse LangChain
callback when `LANGFUSE_*` env vars are present; tracing is a no-op when
they are absent, so the stack runs without an account.

## Rationale

- Observability is a cross-cutting concern consumed via SDK keys — where the
  backend runs is an ops decision, not an architecture decision. The
  integration code is identical either way (`LANGFUSE_HOST` switch).
- Keeping the demo stack to five containers keeps the parts that *do* carry
  architectural signal (gateway, MCP, agent) legible.

## Consequences

- Trace data leaves the local machine. For regulated environments, deploy
  Langfuse self-hosted and change `LANGFUSE_HOST` — nothing else changes.
- LiteLLM additionally tracks cost per key at the gateway, so basic spend
  visibility exists even without Langfuse.

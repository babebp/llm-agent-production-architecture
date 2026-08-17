# ADR-0008: A2A protocol for the agent-to-agent boundary

Status: accepted

## Context

A second agent joins the stack, which forces a decision this repo was built
to demonstrate: what is the boundary *between agents*? Three options:

1. **In-process orchestration** (LangGraph supervisor/subgraphs): one
   process, one framework, function calls between agents.
2. **Custom REST** between agent services: our own request/response schema.
3. **A2A protocol**: each agent publishes an Agent Card at
   `/.well-known/agent-card.json` and speaks a standard message/task
   protocol (JSON-RPC here; gRPC/REST bindings exist).

## Decision

A2A. The user-facing **orchestrator** discovers specialists by fetching
their Agent Cards, routes each message with an LLM call over the card
descriptions, and delegates via `message/send`. MCP stays the **capability**
boundary (tools/data: `search_docs`); A2A is the **peer** boundary
(delegation between autonomous agents). They are complementary, not
competing.

## Rationale

- **Adding an agent is publishing a card**: new service + one URL in
  `A2A_AGENT_URLS`. The orchestrator has no per-agent code — routing reads
  the card. In-process orchestration would make every new agent a code
  change in the supervisor.
- **Independent deploy/scale**: specialists are containers with their own
  lifecycle (the docs agent carries MCP + checkpointer deps; the writer is
  ~90 lines with none of that).
- **No framework lock-in at the boundary**: a CrewAI or plain-SDK agent
  joins by serving a card; LangGraph is an implementation detail inside one
  box. Custom REST would just be A2A minus interop and discovery.
- In-process supervisors remain right for tightly-coupled subagents sharing
  one state; that is not the boundary this repo demonstrates.

## Consequences

- One network hop per delegation — same trade accepted for MCP (ADR-0003),
  negligible next to LLM latency.
- Session continuity maps cleanly: the UI `session_id` becomes the A2A
  `context_id`, which the docs agent uses as its checkpointer thread id.
- Internal hops stay authenticated: bearer token on the JSON-RPC endpoint,
  cards remain open for discovery.
- The SDK is young (1.x, moving fast) — version pinned in requirements.
- Demo uses `message/send` only; long-running task lifecycle, streaming,
  and push notifications are deliberate omissions until an agent needs them.

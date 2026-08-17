# Production LLM Agent Architecture (Open-Source Stack)

[![CI](https://github.com/babebp/llm-agent-production-architecture/actions/workflows/ci.yml/badge.svg)](https://github.com/babebp/llm-agent-production-architecture/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small but production-style **multi-agent** LLM stack: an orchestrator that
discovers specialist agents via the A2A protocol, capabilities behind MCP,
and every LLM call through one gateway.

> **How this was built:** the architecture, component choices, and trade-offs
> are mine — that thinking is written down in the [ADRs](docs/adr/), which are
> the point of this repo. The implementation code was written by Claude from
> that design (AI writes code fast; deciding *what* to build and *why* is the
> part that still needs a human). Every component is the smallest thing that demonstrates the
production concern it stands for — the value here is the *architecture and
the decisions*, not the line count.

**Demo app:** ask about the architecture and the orchestrator routes to the
**docs specialist** (RAG over this repo's ADRs and README); ask for a
rewrite or an ELI5 and it routes to the **writer specialist**. The UI shows
which agent answered.

![Chat UI — agent answers with the ADR cited](docs/img/chat-ui.png)

Every run is fully traced in Langfuse — each agent step, `search_docs` tool
call, and LLM call with latency and token usage:

![Langfuse traces of an agent run](docs/img/langfuse-traces.png)

## Architecture

```mermaid
flowchart LR
    subgraph client
        W[Next.js UI]
    end
    subgraph agents
        O[Orchestrator<br/>card discovery · routing]
        A[Docs Agent<br/>LangGraph ReAct]
        R[Writer Agent<br/>explain · rewrite]
    end
    subgraph capabilities
        M[MCP Server<br/>bearer auth]
        Q[(Qdrant)]
    end
    subgraph gateway
        L[LiteLLM Gateway<br/>keys · budgets · fallbacks]
    end
    G[(Postgres<br/>keys · spend · checkpoints)]
    P[Provider API<br/>Claude / OpenAI]
    F[Langfuse Cloud<br/>traces · cost]

    W -->|/api/chat proxy| O
    O -->|A2A| A
    O -->|A2A| R
    A -->|MCP streamable HTTP| M
    M --> Q
    O --> L
    A --> L
    R --> L
    A -->|session state| G
    L --> G
    L --> P
    A -.->|traces| F
```

| Concern | Component | Why this one |
|---|---|---|
| UI | Next.js 15 | Server-side proxy route; browser never reaches the agent network |
| Agent interop | A2A | Card discovery + delegation; any framework can join by publishing a card ([ADR-0008](docs/adr/0008-a2a-for-agent-interop.md)) |
| Agent runtime | LangGraph | ReAct docs specialist, Postgres-backed session memory ([ADR-0007](docs/adr/0007-postgres-agent-checkpointer.md)) |
| Tooling protocol | MCP | Vector DB exposed as a pluggable capability ([ADR-0003](docs/adr/0003-vector-db-as-mcp-server.md)) |
| Vector DB | Qdrant | Single container, local embeddings via fastembed ([ADR-0005](docs/adr/0005-local-embeddings-fastembed.md)) |
| AI gateway | LiteLLM + Postgres | Credential isolation, virtual keys, per-key spend ([ADR-0002](docs/adr/0002-litellm-over-kong.md), [ADR-0006](docs/adr/0006-db-backed-gateway-virtual-keys.md)) |
| Model serving | Provider API | No vLLM — and exactly when we'd add it ([ADR-0001](docs/adr/0001-api-llm-behind-gateway-not-vllm.md)) |
| Observability | Langfuse Cloud | Full traces without four extra stateful containers ([ADR-0004](docs/adr/0004-langfuse-cloud-over-self-host.md)) |

Design decisions are recorded as [ADRs](docs/adr/) — read those first; they
are the point of this repo.

## Security model

- **Provider keys exist in exactly one place** — the LiteLLM container. The
  agent holds a LiteLLM key; the UI holds nothing.
- **Every internal hop is authenticated**: orchestrator → specialists uses
  an A2A bearer token (agent cards stay open for discovery); agent → MCP
  uses a bearer token; every agent → gateway uses a LiteLLM key.
- **Minimal network exposure**: only the UI (`:3000`) and the gateway
  (`:4000`, for local inspection) are published; Qdrant, MCP, and the agent
  are compose-network-internal.
- **Three credential tiers** ([ADR-0006](docs/adr/0006-db-backed-gateway-virtual-keys.md)):
  provider keys → LiteLLM master key (ops only) → per-app **virtual keys**
  with budgets and rate limits. The agent's key burns at most its budget and
  rotates with one script:

  ```bash
  ./gateway/issue-key.sh   # budgeted, rate-limited key for the agent
  ```
- **No secrets in the repo** — `.env` from `.env.example`; production swaps
  this for a secret manager (Secrets Manager / Vault / SOPS).
- Remaining hardening, documented not demo-blocking: OAuth on the MCP
  server, TLS.

## Quickstart

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY, generate the other secrets
docker compose up -d --build
docker compose exec mcp python ingest.py   # index README + ADRs into Qdrant
open http://localhost:3000
```

The first `ingest.py` run downloads the embedding model (~130 MB, one-time);
give it a minute.

Ask it: *"Why LiteLLM instead of Kong?"* — the agent retrieves the ADR via
MCP and answers with the source cited.

## Tests & evals

- **Unit/contract tests** (`test_*.py` next to each service, run in CI):
  chunking edge cases, MCP and A2A auth boundaries, orchestrator routing +
  delegation (session_id → A2A context_id), `/chat` contract including
  upstream-failure mapping — no containers or API keys needed.
- **Retrieval eval**: a golden question set scored as hit-rate@4 against the
  live index — catches regressions from chunking/embedding/corpus changes
  without spending LLM tokens. **It gates CI**: every push re-indexes the
  corpus into a throwaway Qdrant and fails the build below 80% hit-rate.
  Locally:

  ```bash
  docker compose exec mcp python eval_retrieval.py
  ```

## Repository layout

```
apps/web/              Next.js UI + server-side proxy route
services/orchestrator/ User-facing agent: A2A card discovery + LLM routing
services/agent/        Docs specialist: LangGraph ReAct (MCP RAG, checkpointer)
services/agent-writer/ Writer specialist: explain/rewrite, no tools
services/mcp-qdrant/   MCP server wrapping Qdrant + ingest + retrieval eval
gateway/               LiteLLM config + virtual-key issuance (issue-key.sh)
postgres/              init.sql: gateway DB + agent checkpoint DB
docs/adr/              Architecture Decision Records
.github/workflows/     CI: per-service tests + web build
docker-compose.yml     Full stack, healthchecks, internal-only networking
```

## Deliberate omissions

- **No streaming**: `/chat` returns the whole reply. ReAct + RAG latency is
  dominated by tool-call round trips, and SSE plumbing through proxy + agent
  would double the demo's surface for zero architectural signal. Adding it is
  contained: LangGraph `astream` in the agent, an SSE route in the proxy.
- **No request timeouts/rate limits at the proxy**: the trust boundary is
  enforced by validation at the agent and auth on every internal hop;
  timeout/rate policy belongs to the ingress layer this demo doesn't have.
- **A2A `message/send` only**: no long-running task lifecycle, streaming,
  or push notifications until an agent needs them (ADR-0008).

## Scaling path (documented, intentionally not built)

- **Kubernetes/EKS**: each service is already a stateless container with a
  healthcheck; compose services map 1:1 to Deployments, Qdrant to a
  StatefulSet or managed Qdrant Cloud.
- **Agent state**: done — checkpoints live in Postgres
  ([ADR-0007](docs/adr/0007-postgres-agent-checkpointer.md)), so the agent
  is stateless and horizontal scale is a replica count.
- **Self-hosted models**: add a vLLM backend as a LiteLLM `model_list` entry
  — zero agent changes (ADR-0001).
- **Multi-agent**: done — orchestrator + two specialists over A2A
  ([ADR-0008](docs/adr/0008-a2a-for-agent-interop.md)). The next agent is a
  new service publishing a card plus one URL in `A2A_AGENT_URLS` — no
  orchestrator code changes.

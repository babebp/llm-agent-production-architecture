# ADR-0007: Postgres-backed agent checkpointer

Status: accepted

## Context

LangGraph's checkpointer held session state in process memory
(`MemorySaver`): a restart loses every conversation, and horizontal scaling
is impossible because a session is pinned to the replica that holds it. The
README's scaling path promised this swap; ADR-0006 put a Postgres instance
in the stack anyway.

## Decision

Use LangGraph's `AsyncPostgresSaver` against a **separate database**
(`agent_state`) on the existing Postgres instance. `MemorySaver` remains the
fallback when `CHECKPOINT_DB_URL` is unset, so the agent still runs without
a database in dev.

## Rationale

- **Postgres over Redis**: the instance already runs for the gateway — zero
  new services, one backup story. The access pattern (one read-modify-write
  per agent turn) is nowhere near needing Redis latency.
- **Separate database, not tables inside the gateway's DB**: gateway state
  and agent state have different owners and lifecycles; wiping or migrating
  one must never risk the other.

## Consequences

- Agent replicas are now stateless: horizontal scale is a replica count,
  and sessions survive restarts/deploys.
- Both databases share one Postgres role; per-service roles are the next
  hardening step if tenancy demands it.
- Managed Postgres (RDS) or a Redis saver later is a connection-string
  change confined to the agent's env.

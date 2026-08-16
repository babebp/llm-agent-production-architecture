# ADR-0006: DB-backed LiteLLM with per-app virtual keys

Status: accepted

## Context

ADR-0002 chose LiteLLM for four concerns; two of them — virtual keys and
per-key cost tracking — were deferred because they require LiteLLM to run
with a database. Until now the agent called the gateway with the master key:
one credential, unlimited budget, shared blast radius, and nothing to revoke
if it leaks.

## Decision

Run LiteLLM with Postgres and issue the agent a **virtual key** via
`/key/generate`: budgeted (`max_budget`), rate-limited (`rpm_limit`), and
rotatable. The master key leaves the app path entirely — it exists to issue
and revoke keys, nothing else.

## Rationale

- **Blast radius**: a leaked agent key now burns at most its budget and can
  be revoked without touching the master key or provider keys — three
  credential tiers (provider key → master key → per-app key), each with a
  smaller scope than the one above.
- **Cost attribution**: spend is tracked per key, so "which service spent
  what" is a gateway query, not a log-archaeology exercise.
- **This is the production shape**: one more container in the demo buys the
  exact key lifecycle a multi-team deployment uses — nothing is thrown away
  when scaling (ADR-0001's vLLM path, README's multi-agent path both plug
  into the same key model).

## Consequences

- One stateful service more (Postgres). Accepted: unlike the Langfuse case
  (ADR-0004, four stateful services for a cross-cutting concern), this
  single container unlocks features that *are* the gateway's architectural
  signal.
- The quickstart still works with the master key as a fallback; issuing the
  virtual key is one script (`gateway/issue-key.sh`) and documented in the
  README.
- Key rotation is issuing a new key and swapping one env var — the agent
  never restarts against a changed provider credential.

# ADR-0002: LiteLLM as the AI gateway instead of Kong

Status: accepted

## Context

We want a single choke point between agents and LLM providers for four
production concerns:

1. **Credential isolation** — provider keys live in exactly one service.
2. **Virtual keys** — per-app keys with budgets and rate limits, rotatable
   without touching provider keys.
3. **Cost tracking** — spend per key/model/request.
4. **Provider abstraction** — model/provider swaps and fallbacks as config.

Candidates: Kong (+ AI plugins), LiteLLM, Portkey.

## Decision

LiteLLM.

## Rationale

- Kong is a full API gateway platform; its AI capability is a plugin layer.
  Running Kong for LLM routing alone means operating a much larger system
  (its own datastore, plugin config, enterprise features for the useful
  parts) for a fraction of its surface. Right tool if you already run Kong
  for your API estate — we don't.
- LiteLLM is purpose-built for exactly the four concerns above, is a single
  container, speaks OpenAI-compatible on the app side, and supports 100+
  providers plus self-hosted OpenAI-compatible backends (see ADR-0001).
- Portkey is strong but the gateway's key features push toward its hosted
  platform; LiteLLM keeps everything self-contained and open source.

## Consequences

- The agent uses the plain OpenAI client — no provider SDK in app code.
- In this demo the agent uses the master key; production runs LiteLLM with
  Postgres and issues per-app **virtual keys** with `max_budget` and
  rate limits via `/key/generate`.
- If we outgrow LiteLLM (multi-team governance, existing Kong estate), the
  app-facing contract is OpenAI-compatible either way — migration is a
  base-URL change.

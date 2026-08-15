# ADR-0005: Local embeddings via fastembed instead of an embedding API

Status: accepted

## Context

RAG needs embeddings for ingestion and queries. Anthropic does not offer an
embedding API, so an API-based approach would require a second provider key
(OpenAI, Voyage, Cohere) just for embeddings.

## Decision

Use Qdrant's built-in fastembed integration (ONNX, CPU, runs inside the MCP
service). `client.add()` / `client.query()` handle embedding transparently
with a small local model (default: BGE-small).

## Rationale

- Zero extra credentials and zero per-token embedding cost — the demo works
  with a single provider key.
- Embedding happens inside the MCP service (ADR-0003), so the choice is
  invisible to every consumer.

## Consequences

- BGE-small quality is below frontier embedding APIs; fine for a small docs
  corpus, revisit for large or multilingual corpora.
- Upgrade path: route embeddings through LiteLLM (`/embeddings` with an
  `embedding` model entry) — the change is confined to `ingest.py` and
  `main.py` in the MCP service, and gains the same gateway-side key
  isolation and cost tracking as chat traffic.

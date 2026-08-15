# ADR-0003: Expose the vector DB as an MCP server, not an in-process retriever

Status: accepted

## Context

The common LangGraph pattern wires a Qdrant retriever directly into the
agent process. That couples retrieval to one framework and one process: a
second consumer (another agent, an eval harness, Claude Desktop) would
re-implement the same retrieval logic and need direct DB credentials.

## Decision

Wrap Qdrant behind a dedicated MCP server (`services/mcp-qdrant`) exposing
`search_docs` over streamable HTTP with bearer-token auth. The LangGraph
agent consumes it as an MCP client via `langchain-mcp-adapters`.

## Rationale

- **Capability boundary**: retrieval becomes a service with an interface,
  auth, and its own lifecycle — the agent knows the tool contract, not the
  DB schema or embedding model.
- **Reuse**: any MCP-capable client gets RAG for free; the demo corpus is
  this repo's own docs, so the agent answers questions about its own
  architecture.
- **Security**: only the MCP server holds Qdrant access; agents authenticate
  to the MCP server, not to the database.

## Consequences

- One extra network hop per retrieval — negligible next to LLM latency.
- One more service to run; accepted, since it is ~80 lines.
- Embedding model choice is encapsulated in the MCP service (see ADR-0005);
  swapping it never touches agent code.

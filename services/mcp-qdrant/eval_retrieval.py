"""Retrieval eval: golden questions must surface the expected doc in top-k.

Run after ingest, inside the mcp container:

    docker compose exec mcp python eval_retrieval.py

Scores the retrieval layer in isolation (hit-rate@k) — no LLM calls, so it
is free and deterministic enough to run on every corpus, chunking, or
embedding-model change. Exits non-zero below threshold, so it can gate CI
once the stack runs there.
"""

import os
import sys

from qdrant_client import QdrantClient, models

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.environ.get("COLLECTION", "docs")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
K = 4
THRESHOLD = 0.8

# ponytail: golden set inline; move to a dataset file (or Langfuse datasets) when it grows
GOLDEN = [
    ("Why LiteLLM instead of Kong?", "docs/adr/0002-litellm-over-kong.md"),
    ("Why is there no vLLM in this stack?", "docs/adr/0001-api-llm-behind-gateway-not-vllm.md"),
    ("When would we add self-hosted model serving?", "docs/adr/0001-api-llm-behind-gateway-not-vllm.md"),
    ("Why is the vector DB exposed as an MCP server?", "docs/adr/0003-vector-db-as-mcp-server.md"),
    ("Why Langfuse Cloud instead of self-hosting it?", "docs/adr/0004-langfuse-cloud-over-self-host.md"),
    ("Which embedding model is used, and why local embeddings?", "docs/adr/0005-local-embeddings-fastembed.md"),
    ("Where do the LLM provider API keys live?", "README.md"),
    ("What is the scaling path to Kubernetes?", "README.md"),
]


def main() -> None:
    client = QdrantClient(url=QDRANT_URL)
    hits = 0
    for question, expected in GOLDEN:
        res = client.query_points(
            collection_name=COLLECTION,
            query=models.Document(text=question, model=EMBED_MODEL),
            limit=K,
        )
        sources = [(p.payload or {}).get("source") for p in res.points]
        ok = expected in sources
        hits += ok
        print(f"{'PASS' if ok else 'FAIL'}  {question}\n      expected {expected}, got {sources}")
    rate = hits / len(GOLDEN)
    print(f"\nhit-rate@{K}: {hits}/{len(GOLDEN)} ({rate:.0%}), threshold {THRESHOLD:.0%}")
    if rate < THRESHOLD:
        sys.exit(1)


if __name__ == "__main__":
    main()

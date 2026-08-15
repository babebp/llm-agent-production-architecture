"""MCP server exposing the Qdrant document store as tools.

RAG is a pluggable capability here, not logic hard-wired into the agent:
any MCP-capable client (LangGraph, Claude Desktop, another agent) can
consume `search_docs` over streamable HTTP.
"""

import os

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from qdrant_client import QdrantClient, models
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
AUTH_TOKEN = os.environ["MCP_AUTH_TOKEN"]
COLLECTION = os.environ.get("COLLECTION", "docs")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

mcp = MCPServer("qdrant-docs")
qdrant = QdrantClient(url=QDRANT_URL)


@mcp.tool()
def search_docs(query: str, limit: int = 4) -> list[dict]:
    """Search this project's documentation (architecture, ADRs, README).

    Args:
        query: Natural-language search query.
        limit: Max number of chunks to return.
    """
    res = qdrant.query_points(
        collection_name=COLLECTION,
        query=models.Document(text=query, model=EMBED_MODEL),
        limit=limit,
    )
    return [
        {
            "text": (p.payload or {}).get("text"),
            "source": (p.payload or {}).get("source"),
            "score": p.score,
        }
        for p in res.points
    ]


class BearerAuth(BaseHTTPMiddleware):
    # ponytail: shared static token; swap for OAuth/JWT when multi-tenant
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {AUTH_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


async def health(request):
    return JSONResponse({"ok": True})


app = mcp.streamable_http_app(
    stateless_http=True,
    # Internal service reached as "mcp:8080" — DNS-rebinding host checks would
    # reject that Host header; access is gated by bearer auth + network isolation.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
app.add_middleware(BearerAuth)
app.routes.append(Route("/health", health))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

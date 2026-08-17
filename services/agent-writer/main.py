"""Writer specialist: explains and rewrites, no retrieval.

Exposes only the A2A surface (ADR-0008): an Agent Card for discovery and a
bearer-authed JSON-RPC endpoint. LLM calls go through the LiteLLM gateway
like every other agent.
"""

import os

import uvicorn
from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import a2a_pb2
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

AUTH_TOKEN = os.environ["A2A_AUTH_TOKEN"]
SELF_URL = os.environ.get("SELF_URL", "http://agent-writer:8000")

SYSTEM_PROMPT = (
    "You are the writing specialist of a multi-agent system. Explain "
    "concepts simply, rewrite or summarize text the user provides, and adapt "
    "tone/level on request. You have no retrieval tools — if the question "
    "needs facts about this repository you don't have, say so briefly."
)

CARD = a2a_pb2.AgentCard(
    name="writer-agent",
    description=(
        "Explains, rewrites, summarizes, and simplifies. Use for style, "
        "tone, or level-of-detail requests. Has no access to the "
        "repository's documentation."
    ),
    version="1.0.0",
    supported_interfaces=[
        a2a_pb2.AgentInterface(url=f"{SELF_URL}/a2a", protocol_binding="JSONRPC")
    ],
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        a2a_pb2.AgentSkill(
            id="explain",
            name="Explain & rewrite",
            description="Explain simply, rewrite, summarize, change tone.",
            tags=["writing", "explanation"],
        )
    ],
)

llm = ChatOpenAI(
    model=os.environ.get("LLM_MODEL", "chat"),
    api_key=os.environ["LITELLM_API_KEY"],
    base_url=os.environ.get("LITELLM_BASE_URL", "http://litellm:4000"),
)


class WriterExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        result = await llm.ainvoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context.get_user_input()},
            ]
        )
        await event_queue.enqueue_event(
            new_text_message(result.content, context_id=context.context_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


class BearerAuth(BaseHTTPMiddleware):
    # card stays open for discovery; the RPC endpoint requires the token
    async def dispatch(self, request, call_next):
        if request.url.path == "/a2a" and request.headers.get(
            "authorization"
        ) != f"Bearer {AUTH_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app = FastAPI()
handler = DefaultRequestHandler(
    agent_executor=WriterExecutor(), task_store=InMemoryTaskStore(), agent_card=CARD
)
add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=create_agent_card_routes(CARD),
    jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a"),
)
app.add_middleware(BearerAuth)


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

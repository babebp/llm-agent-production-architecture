"""LangGraph ReAct agent: the docs specialist of the multi-agent stack.

- Consumed by the orchestrator over A2A (ADR-0008): card open at
  /.well-known/agent-card.json, JSON-RPC endpoint bearer-authed. The
  legacy /chat endpoint remains for direct internal access.
- LLM calls go through the LiteLLM gateway (OpenAI-compatible) — the agent
  holds a LiteLLM key, never a provider key.
- RAG arrives as MCP tools from the mcp-qdrant server (bearer-auth).
- Traces go to Langfuse Cloud when LANGFUSE_* keys are set.
- Session state checkpoints to Postgres when CHECKPOINT_DB_URL is set
  (ADR-0007); in-memory fallback otherwise. The A2A context_id is the
  checkpointer thread id, so delegated sessions keep their memory.
"""

import os
from contextlib import AsyncExitStack, asynccontextmanager

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
from fastapi.responses import JSONResponse
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

SYSTEM_PROMPT = (
    "You are an assistant for this repository's production LLM agent "
    "architecture. Answer questions about the architecture, its components, "
    "and the design decisions behind it. Use the search_docs tool to ground "
    "answers in the actual documentation, and cite the source file."
)

state: dict = {}

A2A_AUTH_TOKEN = os.environ["A2A_AUTH_TOKEN"]
SELF_URL = os.environ.get("SELF_URL", "http://agent:8000")

CARD = a2a_pb2.AgentCard(
    name="docs-agent",
    description=(
        "Answers factual questions about this repository's architecture, "
        "components, and design decisions, grounded in the ADRs and README "
        "via retrieval. Use for anything that needs repository knowledge."
    ),
    version="1.0.0",
    supported_interfaces=[
        a2a_pb2.AgentInterface(url=f"{SELF_URL}/a2a", protocol_binding="JSONRPC")
    ],
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        a2a_pb2.AgentSkill(
            id="architecture-qa",
            name="Architecture Q&A",
            description="RAG-grounded answers about this stack, sources cited.",
            tags=["rag", "architecture"],
        )
    ],
)


async def _run_agent(text: str, thread_id: str) -> str:
    result = await state["agent"].ainvoke(
        {"messages": [{"role": "user", "content": text}]},
        config={
            "configurable": {"thread_id": thread_id},
            "callbacks": callbacks,
            "metadata": {"langfuse_session_id": thread_id},
        },
    )
    return result["messages"][-1].content


class DocsExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # A2A context_id → checkpointer thread: sessions survive delegation
        reply = await _run_agent(
            context.get_user_input(), context.context_id or "default"
        )
        await event_queue.enqueue_event(
            new_text_message(reply, context_id=context.context_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


class BearerAuth(BaseHTTPMiddleware):
    # card stays open for discovery; the RPC endpoint requires the token
    async def dispatch(self, request, call_next):
        if request.url.path == "/a2a" and request.headers.get(
            "authorization"
        ) != f"Bearer {A2A_AUTH_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

callbacks = []
if os.environ.get("LANGFUSE_PUBLIC_KEY"):
    from langfuse.langchain import CallbackHandler

    callbacks.append(CallbackHandler())


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm = ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "chat"),
        api_key=os.environ["LITELLM_API_KEY"],
        base_url=os.environ.get("LITELLM_BASE_URL", "http://litellm:4000"),
    )
    mcp = MultiServerMCPClient(
        {
            "docs": {
                "transport": "streamable_http",
                "url": os.environ.get("MCP_URL", "http://mcp:8080/mcp"),
                "headers": {
                    "Authorization": f"Bearer {os.environ['MCP_AUTH_TOKEN']}"
                },
            }
        }
    )
    tools = await mcp.get_tools()
    async with AsyncExitStack() as stack:
        db_url = os.environ.get("CHECKPOINT_DB_URL")
        if db_url:
            # sessions survive restarts; agent replicas stay stateless (ADR-0007)
            checkpointer = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(db_url)
            )
            await checkpointer.setup()
        else:
            checkpointer = MemorySaver()  # dev fallback: state dies with the process
        state["agent"] = create_react_agent(
            llm, tools, prompt=SYSTEM_PROMPT, checkpointer=checkpointer
        )
        yield


app = FastAPI(lifespan=lifespan)
add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=create_agent_card_routes(CARD),
    jsonrpc_routes=create_jsonrpc_routes(
        DefaultRequestHandler(
            agent_executor=DocsExecutor(),
            task_store=InMemoryTaskStore(),
            agent_card=CARD,
        ),
        rpc_url="/a2a",
    ),
)
app.add_middleware(BearerAuth)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = await _run_agent(req.message, req.session_id)
    except Exception as e:  # surface upstream failures (gateway/provider) as JSON
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
    return {"reply": reply}


@app.get("/health")
async def health():
    return {"ok": True}

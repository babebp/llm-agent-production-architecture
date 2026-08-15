"""LangGraph ReAct agent behind a FastAPI endpoint.

- LLM calls go through the LiteLLM gateway (OpenAI-compatible) — the agent
  holds a LiteLLM key, never a provider key.
- RAG arrives as MCP tools from the mcp-qdrant server (bearer-auth).
- Traces go to Langfuse Cloud when LANGFUSE_* keys are set.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

SYSTEM_PROMPT = (
    "You are an assistant for this repository's production multi-agent "
    "architecture. Answer questions about the architecture, its components, "
    "and the design decisions behind it. Use the search_docs tool to ground "
    "answers in the actual documentation, and cite the source file."
)

state: dict = {}

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
    # ponytail: in-memory checkpointer — swap for Postgres/Redis saver when horizontally scaled
    state["agent"] = create_react_agent(
        llm, tools, prompt=SYSTEM_PROMPT, checkpointer=MemorySaver()
    )
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        result = await state["agent"].ainvoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config={
                "configurable": {"thread_id": req.session_id},
                "callbacks": callbacks,
                "metadata": {"langfuse_session_id": req.session_id},
            },
        )
    except Exception as e:  # surface upstream failures (gateway/provider) as JSON
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
    return {"reply": result["messages"][-1].content}


@app.get("/health")
async def health():
    return {"ok": True}

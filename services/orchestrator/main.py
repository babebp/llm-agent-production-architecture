"""Orchestrator: the user-facing agent that delegates over A2A (ADR-0008).

At startup it fetches the Agent Card of every specialist in A2A_AGENT_URLS.
Per message, an LLM routes over the card descriptions, then the message is
delegated via A2A `message/send`. The UI session_id travels as the A2A
context_id, so specialists keep per-session memory. No per-agent code:
adding a specialist is publishing a card and adding its URL.
"""

import os
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_stream_response_text, new_text_message
from a2a.types import a2a_pb2
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

AGENT_URLS = [u for u in os.environ.get("A2A_AGENT_URLS", "").split(",") if u]
AUTH_HEADERS = {"Authorization": f"Bearer {os.environ['A2A_AUTH_TOKEN']}"}

state: dict = {}


def pick_agent(choice: str, cards: dict) -> str:
    """Normalize the router LLM's output; first (docs) agent is the fallback."""
    choice = choice.strip().strip("\"'`").lower()
    for name in cards:
        if name.lower() in choice:
            return name
    return next(iter(cards))


async def route(message: str) -> str:
    menu = "\n".join(
        f"- {name}: {card.description}" for name, card in state["cards"].items()
    )
    result = await state["llm"].ainvoke(
        [
            {
                "role": "system",
                "content": "Route the user message to exactly one specialist "
                f"agent.\n{menu}\nReply with the agent name only.",
            },
            {"role": "user", "content": message},
        ]
    )
    return pick_agent(result.content, state["cards"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        state["llm"] = ChatOpenAI(
            model=os.environ.get("LLM_MODEL", "chat"),
            api_key=os.environ["LITELLM_API_KEY"],
            base_url=os.environ.get("LITELLM_BASE_URL", "http://litellm:4000"),
        )
        http = await stack.enter_async_context(
            httpx.AsyncClient(headers=AUTH_HEADERS, timeout=120)
        )
        state["cards"], state["clients"] = {}, {}
        for url in AGENT_URLS:
            card = await A2ACardResolver(http, url).get_agent_card()
            client = await create_client(
                card, ClientConfig(streaming=False, httpx_client=http)
            )
            state["cards"][card.name] = card
            state["clients"][card.name] = client
        yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        agent_name = await route(req.message)
        request = a2a_pb2.SendMessageRequest(
            message=new_text_message(
                req.message, role=a2a_pb2.ROLE_USER, context_id=req.session_id
            )
        )
        texts = []
        async for resp in state["clients"][agent_name].send_message(request):
            if text := get_stream_response_text(resp):
                texts.append(text)
    except Exception as e:  # surface downstream failures as JSON
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
    return {"reply": "\n".join(texts), "agent": agent_name}


@app.get("/health")
async def health():
    return {"ok": True, "agents": list(state.get("cards", {}))}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

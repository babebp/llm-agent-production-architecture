"""Contract tests: routing normalization and the /chat delegation path.

No lifespan (httpx.ASGITransport) — fake cards, router LLM, and A2A
clients are injected into `state`.
"""

import os

os.environ.setdefault("A2A_AUTH_TOKEN", "test-token")
os.environ.setdefault("LITELLM_API_KEY", "test-key")

import httpx
import pytest
from a2a.helpers import new_text_message
from a2a.types import a2a_pb2

import main

CARDS = {
    "docs-agent": a2a_pb2.AgentCard(name="docs-agent", description="repo facts"),
    "writer-agent": a2a_pb2.AgentCard(name="writer-agent", description="rewriting"),
}


def test_pick_agent_normalizes_llm_output():
    assert main.pick_agent("writer-agent", CARDS) == "writer-agent"
    assert main.pick_agent('  "Writer-Agent".', CARDS) == "writer-agent"
    assert main.pick_agent("no idea", CARDS) == "docs-agent"  # fallback: first


class FakeRouterLLM:
    def __init__(self, choice):
        self.choice = choice

    async def ainvoke(self, messages):
        return type("R", (), {"content": self.choice})()


class FakeA2AClient:
    def __init__(self, reply="delegated reply", fail=False):
        self.reply, self.fail = reply, fail
        self.last_request = None

    async def send_message(self, request, **kwargs):
        if self.fail:
            raise RuntimeError("specialist down")
        self.last_request = request
        yield a2a_pb2.StreamResponse(message=new_text_message(self.reply))


def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    )


@pytest.mark.anyio
async def test_chat_routes_and_delegates():
    fake = FakeA2AClient()
    main.state.update(
        llm=FakeRouterLLM("writer-agent"),
        cards=CARDS,
        clients={"docs-agent": FakeA2AClient(), "writer-agent": fake},
    )
    async with client() as c:
        r = await c.post("/chat", json={"message": "explain simply", "session_id": "s1"})
    assert r.status_code == 200
    assert r.json() == {"reply": "delegated reply", "agent": "writer-agent"}
    # session_id must travel as the A2A context_id
    assert fake.last_request.message.context_id == "s1"


@pytest.mark.anyio
async def test_specialist_failure_maps_to_502():
    main.state.update(
        llm=FakeRouterLLM("docs-agent"),
        cards=CARDS,
        clients={"docs-agent": FakeA2AClient(fail=True)},
    )
    async with client() as c:
        r = await c.post("/chat", json={"message": "hi"})
    assert r.status_code == 502
    assert "RuntimeError" in r.json()["error"]


@pytest.fixture
def anyio_backend():
    return "asyncio"

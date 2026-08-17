"""Contract tests for the /chat endpoint.

Uses httpx.ASGITransport (no lifespan) so no real MCP/LLM is needed —
a fake agent is injected into `state` instead.
"""

import os

os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")
os.environ.setdefault("LITELLM_API_KEY", "test-key")
os.environ.setdefault("A2A_AUTH_TOKEN", "test-a2a-token")

import httpx
import pytest

import main


class FakeAgent:
    async def ainvoke(self, payload, config=None):
        return {"messages": [type("Msg", (), {"content": "grounded answer"})()]}


class BrokenAgent:
    async def ainvoke(self, payload, config=None):
        raise RuntimeError("gateway unreachable")


def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    )


@pytest.mark.anyio
async def test_chat_returns_last_message():
    main.state["agent"] = FakeAgent()
    async with client() as c:
        r = await c.post("/chat", json={"message": "why litellm?"})
    assert r.status_code == 200
    assert r.json() == {"reply": "grounded answer"}


@pytest.mark.anyio
async def test_upstream_failure_maps_to_502_json():
    main.state["agent"] = BrokenAgent()
    async with client() as c:
        r = await c.post("/chat", json={"message": "hi"})
    assert r.status_code == 502
    assert "RuntimeError" in r.json()["error"]


@pytest.mark.anyio
async def test_missing_message_is_422():
    main.state["agent"] = FakeAgent()
    async with client() as c:
        r = await c.post("/chat", json={})
    assert r.status_code == 422


@pytest.mark.anyio
async def test_a2a_card_is_open():
    async with client() as c:
        r = await c.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    assert r.json()["name"] == "docs-agent"


@pytest.mark.anyio
async def test_a2a_rpc_requires_bearer_token():
    async with client() as c:
        assert (await c.post("/a2a", json={})).status_code == 401
        r = await c.post("/a2a", json={}, headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


@pytest.fixture
def anyio_backend():
    return "asyncio"

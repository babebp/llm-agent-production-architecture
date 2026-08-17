"""Contract tests: A2A card discovery is open, the RPC endpoint is not."""

import os

os.environ.setdefault("A2A_AUTH_TOKEN", "test-token")
os.environ.setdefault("LITELLM_API_KEY", "test-key")

from starlette.testclient import TestClient

import main


def test_agent_card_is_open():
    with TestClient(main.app) as client:
        r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert card["name"] == "writer-agent"
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_rpc_requires_bearer_token():
    with TestClient(main.app) as client:
        assert client.post("/a2a", json={}).status_code == 401
        r = client.post("/a2a", json={}, headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401


def test_health_is_open():
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

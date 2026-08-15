"""Contract tests: chunking logic and the MCP server's auth boundary."""

import os

os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")

import pytest
from starlette.testclient import TestClient

import ingest
import main


@pytest.fixture(scope="module")
def client():
    # single TestClient for all tests: the MCP session manager's lifespan
    # can only run once per app instance
    with TestClient(main.app) as c:
        yield c


def test_chunk_splits_on_paragraph_boundary():
    text = "a" * 1000 + "\n\n" + "b" * 1000
    assert ingest.chunk(text, size=1500) == ["a" * 1000, "b" * 1000]


def test_chunk_keeps_small_text_whole():
    assert ingest.chunk("hello\n\nworld", size=1500) == ["hello\n\nworld"]


def test_chunk_oversized_paragraph_is_not_dropped():
    big = "x" * 5000
    assert ingest.chunk(big, size=1500) == [big]


def test_chunk_empty_input():
    assert ingest.chunk("") == []


def test_health_is_open(client):
    assert client.get("/health").status_code == 200


def test_mcp_rejects_missing_and_wrong_token(client):
    assert client.post("/mcp").status_code == 401
    r = client.post("/mcp", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401

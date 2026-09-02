import json

import httpx
import pytest
from mem0_mcp.client import Mem0ApiError, Mem0RestClient, Settings


def request_json(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.mark.asyncio
async def test_add_memory_sends_shared_user_and_process_agent():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{"id": "m-1"}]})

    settings = Settings("https://mem0.example", "key", "laptop-owner", "codex")
    client = Mem0RestClient(settings, transport=httpx.MockTransport(handler))
    try:
        result = await client.add_memory("I prefer concise answers")
    finally:
        await client.aclose()

    assert result == {"results": [{"id": "m-1"}]}
    assert requests[0].headers["X-API-Key"] == "key"
    assert request_json(requests[0]) == {
        "messages": [{"role": "user", "content": "I prefer concise answers"}],
        "user_id": "laptop-owner",
        "agent_id": "codex",
        "infer": True,
    }


@pytest.mark.asyncio
async def test_search_defaults_to_shared_user_and_accepts_agent_filter():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    settings = Settings("https://mem0.example", "key", "laptop-owner", "claude-code")
    client = Mem0RestClient(settings, transport=httpx.MockTransport(handler))
    try:
        await client.search("preferences", agent_id="codex", top_k=5)
    finally:
        await client.aclose()

    assert request_json(requests[0]) == {
        "query": "preferences",
        "filters": {"user_id": "laptop-owner", "agent_id": "codex"},
        "top_k": 5,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["list", "get", "history", "update", "delete"])
async def test_memory_operations_use_oss_rest_routes(operation):
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    settings = Settings("https://mem0.example", "key", "laptop-owner", "codex")
    client = Mem0RestClient(settings, transport=httpx.MockTransport(handler))
    try:
        if operation == "list":
            result = await client.list_memories(agent_id="codex", top_k=3)
        elif operation == "get":
            result = await client.get_memory("memory-1")
        elif operation == "history":
            result = await client.memory_history("memory-1")
        elif operation == "update":
            result = await client.update_memory("memory-1", text="updated")
        else:
            result = await client.delete_memory("memory-1")
    finally:
        await client.aclose()

    assert result == {"ok": True}
    assert requests[0].headers["X-API-Key"] == "key"
    if operation == "list":
        assert requests[0].method == "GET"
        assert dict(requests[0].url.params) == {
            "user_id": "laptop-owner",
            "agent_id": "codex",
            "top_k": "3",
            "show_expired": "false",
        }
    elif operation == "get":
        assert requests[0].method == "GET"
        assert requests[0].url.path == "/memories/memory-1"
    elif operation == "history":
        assert requests[0].method == "GET"
        assert requests[0].url.path == "/memories/memory-1/history"
    elif operation == "update":
        assert requests[0].method == "PUT"
        assert requests[0].url.path == "/memories/memory-1"
        assert request_json(requests[0]) == {"text": "updated"}
    else:
        assert requests[0].method == "DELETE"
        assert requests[0].url.path == "/memories/memory-1"


@pytest.mark.asyncio
async def test_api_error_preserves_status_without_logging_credentials():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid API key."})

    settings = Settings("https://mem0.example", "secret-key", "laptop-owner", "codex")
    client = Mem0RestClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(Mem0ApiError) as error:
            await client.search("preferences")
    finally:
        await client.aclose()

    assert error.value.status_code == 401
    assert "401" in str(error.value)
    assert "secret-key" not in str(error.value)


def test_settings_reject_missing_key_and_insecure_public_url(monkeypatch):
    monkeypatch.delenv("MEM0_API_KEY", raising=False)
    monkeypatch.setenv("MEM0_API_URL", "https://mem0.example")
    monkeypatch.setenv("MEM0_USER_ID", "laptop-owner")
    monkeypatch.setenv("MEM0_AGENT_ID", "codex")

    with pytest.raises(ValueError, match="MEM0_API_KEY"):
        Settings.from_env()

    with pytest.raises(ValueError, match="https"):
        Settings("http://server.example", "key", "laptop-owner", "codex")

import json
from pathlib import Path

import pytest
from mem0_mcp.server import create_server


MCP_ROOT = Path(__file__).parents[1]


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def add_memory(self, content, **kwargs):
        self.calls.append(("add", content, kwargs))
        return {"results": [{"id": "m-1"}]}


@pytest.mark.asyncio
async def test_server_registers_memory_tools():
    server = create_server(client=object())
    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "memory_add",
        "memory_search",
        "memory_list",
        "memory_get",
        "memory_history",
        "memory_update",
        "memory_delete",
    }


@pytest.mark.asyncio
async def test_memory_add_tool_forwards_content_and_options():
    client = RecordingClient()
    server = create_server(client=client)

    result = await server.call_tool(
        "memory_add",
        {"content": "I prefer concise answers", "role": "assistant", "infer": False},
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == {"results": [{"id": "m-1"}]}
    assert client.calls == [
        (
            "add",
            "I prefer concise answers",
            {
                "role": "assistant",
                "metadata": None,
                "infer": False,
                "run_id": None,
                "expiration_date": None,
                "memory_type": None,
                "prompt": None,
            },
        )
    ]


def test_macos_launcher_reads_keychain_and_runs_project_entrypoint():
    launcher = MCP_ROOT / "bin/mem0-mcp-macos"
    content = launcher.read_text()

    assert "security find-generic-password" in content
    assert "MEM0_API_KEY" in content
    assert 'exec "${UV_BIN:-uv}" run --project' in content

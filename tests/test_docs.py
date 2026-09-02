from pathlib import Path


MCP_ROOT = Path(__file__).parents[1]


def test_setup_docs_use_placeholders_and_shared_defaults():
    readme = (MCP_ROOT / "README.md").read_text()
    example = (MCP_ROOT / ".env.example").read_text()

    assert "MEM0_API_KEY" in readme
    assert "./setup.sh" in readme
    assert "MEM0_AGENT_ID=mem0-client" in readme
    assert "./setup.sh --user-id juner-team" in readme
    assert "your-api-key" in example
    assert "X-API-Key" in readme
    assert "password" not in example.lower()

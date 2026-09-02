from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import Mem0RestClient, Settings

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """
Use this server for durable, user-approved Mem0 memory.

Memories are shared through the configured user_id. Writes are tagged with the
agent_id configured for this process; use distinct agent IDs only when client
attribution is needed. Search before storing duplicates. Store durable
preferences, decisions, and project context only; never store passwords, API
keys, tokens, or other secrets.
""".strip()


def create_server(*, client: Mem0RestClient | None = None, settings: Settings | None = None) -> FastMCP:
    """Build an MCP server around a configured Mem0 REST client."""

    bridge = client or Mem0RestClient(settings or Settings.from_env())
    server = FastMCP("mem0-self-hosted", instructions=SERVER_INSTRUCTIONS)

    @server.tool(name="memory_add")
    async def memory_add(
        content: str,
        role: str = "user",
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        run_id: str | None = None,
        expiration_date: str | None = None,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> Any:
        """Store one durable memory in the shared user namespace."""

        return await bridge.add_memory(
            content,
            role=role,
            metadata=metadata,
            infer=infer,
            run_id=run_id,
            expiration_date=expiration_date,
            memory_type=memory_type,
            prompt=prompt,
        )

    @server.tool(name="memory_search")
    async def memory_search(
        query: str,
        agent_id: str | None = None,
        top_k: int = 10,
        threshold: float | None = None,
        explain: bool | None = None,
        show_expired: bool | None = None,
    ) -> Any:
        """Search shared memories, optionally limited to one agent's writes."""

        return await bridge.search(
            query,
            agent_id=agent_id,
            top_k=top_k,
            threshold=threshold,
            explain=explain,
            show_expired=show_expired,
        )

    @server.tool(name="memory_list")
    async def memory_list(
        agent_id: str | None = None,
        top_k: int = 100,
        show_expired: bool = False,
    ) -> Any:
        """List shared memories, optionally limited to one agent's writes."""

        return await bridge.list_memories(agent_id=agent_id, top_k=top_k, show_expired=show_expired)

    @server.tool(name="memory_get")
    async def memory_get(memory_id: str) -> Any:
        """Retrieve one memory by its ID."""

        return await bridge.get_memory(memory_id)

    @server.tool(name="memory_history")
    async def memory_history(memory_id: str) -> Any:
        """Retrieve the change history for one memory."""

        return await bridge.memory_history(memory_id)

    @server.tool(name="memory_update")
    async def memory_update(
        memory_id: str,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        expiration_date: str | None = None,
    ) -> Any:
        """Update a memory after confirming the target memory ID."""

        return await bridge.update_memory(
            memory_id,
            text=text,
            metadata=metadata,
            expiration_date=expiration_date,
        )

    @server.tool(name="memory_delete")
    async def memory_delete(memory_id: str) -> Any:
        """Delete one memory by its ID after confirming the target."""

        return await bridge.delete_memory(memory_id)

    return server


def main() -> None:
    """Run the local stdio MCP server for Claude Code or Codex."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    client = Mem0RestClient(settings)
    server = create_server(client=client)
    try:
        server.run()
    finally:
        asyncio.run(client.aclose())


if __name__ == "__main__":
    main()

"""MCP tool registry client for dynamic tool discovery across BATNA MCP servers.

Connects to a running MCP server over stdio and discovers its exposed tools via the
official MCP client SDK — the same way an agent would query the registry for available
capabilities at session start (Phase 5 dynamic tool selection) instead of relying on a
hardcoded list.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import TextContent, Tool


class ToolRegistryClient:
    """Async client that discovers and calls tools on a BATNA MCP server over stdio."""

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        self._server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        """Yield an initialized ClientSession connected to the server subprocess."""
        async with stdio_client(self._server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[Tool]:
        """Discover the tools the server exposes (the dynamic registry query)."""
        async with self._session() as session:
            result = await session.list_tools()
            return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a discovered tool with the given arguments; return its text content."""
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
        return "".join(
            content.text for content in result.content if isinstance(content, TextContent)
        )

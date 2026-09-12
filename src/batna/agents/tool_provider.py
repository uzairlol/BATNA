"""Session-scoped dynamic tool provider backed by the MCP tool registry.

Phase 5 requires the agent to discover available tools each session rather than
rely on a hardcoded list. ``ToolProvider`` performs that registry query (via
``ToolRegistryClient``) and records every executed call in a ``ToolCallLog`` for
provenance auditing.
"""

from __future__ import annotations

from typing import Any

from mcp.types import Tool

from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.mcp_servers.registry_client import ToolRegistryClient


class ToolProvider:
    """Provides discovered MCP tools to an agent and logs every real invocation."""

    def __init__(self, registry: ToolRegistryClient, log: ToolCallLog | None = None) -> None:
        self._registry = registry
        self._log = log or ToolCallLog()
        self._tools: list[Tool] | None = None

    @property
    def log(self) -> ToolCallLog:
        return self._log

    async def discover(self) -> list[Tool]:
        """Query the registry for available tools (dynamic discovery) and cache them."""
        if self._tools is None:
            self._tools = await self._registry.list_tools()
        return list(self._tools)

    def llm_tools(self) -> list[dict[str, Any]]:
        """Format the discovered tools for Ollama/OpenAI native function-calling."""
        if self._tools is None:
            raise RuntimeError("discover() must be called before llm_tools()")
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a discovered tool and record the invocation in the call log."""
        try:
            response = await self._registry.call_tool(name, arguments)
        except Exception as exc:  # pragma: no cover - defensive logging path
            self._log.append(
                ToolCallEntry(name=name, arguments=arguments, response=str(exc), ok=False)
            )
            raise
        self._log.append(ToolCallEntry(name=name, arguments=arguments, response=response, ok=True))
        return response

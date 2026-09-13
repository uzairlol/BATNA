"""Session-scoped dynamic tool provider backed by the MCP tool registry.

Phase 5 requires the agent to discover available tools each session rather than
rely on a hardcoded list. ``ToolProvider`` performs that registry query (via
``ToolRegistryClient``) and records every executed call in a ``ToolCallLog`` for
provenance auditing.

Phase 6 extends the catalog with deterministic in-process tools
(``batna.agents.native_tools``): the provider merges native tools into the
discovered catalog, so the agent dynamically selects between MCP-served and
in-process capabilities the same way, and every call — native or MCP — lands in
the same ``ToolCallLog`` for uniform provenance checks.
"""

from __future__ import annotations

from typing import Any

from mcp.types import Tool

from batna.agents.native_tools import NativeTool, native_tools_catalog
from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.mcp_servers.registry_client import ToolRegistryClient
from batna.stream.events import EventType, build_event
from batna.stream.sink import NullStreamSink, StreamSink


class ToolProvider:
    """Provides discovered MCP + native tools to an agent and logs every invocation."""

    def __init__(
        self,
        registry: ToolRegistryClient,
        log: ToolCallLog | None = None,
        native_tools: list[NativeTool] | None = None,
        *,
        sink: StreamSink | None = None,
        role: str | None = None,
    ) -> None:
        self._registry = registry
        self._log = log or ToolCallLog()
        self._native = native_tools if native_tools is not None else native_tools_catalog()
        self._tools: list[Tool] | None = None
        self._sink = sink if sink is not None else NullStreamSink()
        self._role = role

    @property
    def log(self) -> ToolCallLog:
        return self._log

    async def discover(self) -> list[Tool]:
        """Query the registry + native catalog and merge into one tool set.

        The merged catalog is cached for the session (the spec's dynamic tool
        selection happens at session start; re-discovery mid-session is a Phase
        7+ concern driven by the approval-gate event loop).
        """
        if self._tools is None:
            discovered = await self._registry.list_tools()
            self._tools = [tool.to_mcp_tool() for tool in self._native] + list(discovered)
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
        """Execute a discovered tool (native or MCP) and record the invocation."""
        native = self._find_native(name)
        await self._sink.emit(
            build_event(
                EventType.TOOL_CALL_START,
                {"name": name, "arguments": arguments},
                side=self._role,
            )
        )
        try:
            if native is not None:
                response = native.callable(arguments)
            else:
                response = await self._registry.call_tool(name, arguments)
        except Exception as exc:  # pragma: no cover - defensive logging path
            self._log.append(
                ToolCallEntry(name=name, arguments=arguments, response=str(exc), ok=False)
            )
            await self._sink.emit(
                build_event(
                    EventType.TOOL_CALL_ERROR,
                    {"name": name, "arguments": arguments, "error": str(exc)},
                    side=self._role,
                )
            )
            raise
        self._log.append(ToolCallEntry(name=name, arguments=arguments, response=response, ok=True))
        await self._sink.emit(
            build_event(
                EventType.TOOL_CALL_RESULT,
                # ``response`` is the raw MCP text content — the "real tool call
                # payload" Phase 7 surfaces in the dashboard.
                {"name": name, "arguments": arguments, "response": response},
                side=self._role,
            )
        )
        return response

    def _find_native(self, name: str) -> NativeTool | None:
        for tool in self._native:
            if tool.name == name:
                return tool
        return None

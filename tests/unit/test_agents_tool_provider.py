"""Unit tests for the Phase 5 dynamic tool provider and call log."""

from __future__ import annotations

from typing import Any

import pytest
from mcp.types import Tool

from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.agents.tool_provider import ToolProvider
from batna.mcp_servers.registry_client import ToolRegistryClient

_MARKET_SCHEMA = {
    "type": "object",
    "properties": {"industry": {"type": "string"}},
    "required": ["industry"],
}
_MARKET_TOOL = Tool(
    name="get_market_benchmark",
    description="Get a real market benchmark",
    input_schema=_MARKET_SCHEMA,
)


class _FakeRegistry(ToolRegistryClient):
    def __init__(self, tools: list[Tool], responses: dict[str, str]) -> None:
        self._fake_tools = tools
        self._fake_responses = responses

    async def list_tools(self) -> list[Tool]:
        return list(self._fake_tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        del arguments
        return self._fake_responses.get(name, "{}")


async def test_provider_discovers_tools_dynamically() -> None:
    provider = ToolProvider(_FakeRegistry([_MARKET_TOOL], {}))
    assert provider._tools is None  # no pre-loaded hardcoded list

    tools = await provider.discover()
    # Phase 6: the catalog merges the native check_contract_risk tool with the
    # MCP-discovered market tool, both discovered dynamically this session.
    assert {t.name for t in tools} == {"get_market_benchmark", "check_contract_risk"}

    formatted = provider.llm_tools()
    assert formatted[0]["type"] == "function"
    assert {t["function"]["name"] for t in formatted} == {
        "get_market_benchmark",
        "check_contract_risk",
    }


async def test_provider_logs_every_real_call() -> None:
    response = '{"latest_value": 118.5}'
    provider = ToolProvider(_FakeRegistry([_MARKET_TOOL], {"get_market_benchmark": response}))
    await provider.discover()

    result = await provider.call("get_market_benchmark", {"industry": "cloud_hosting"})
    assert result == response
    assert len(provider.log) == 1
    entry = provider.log.entries[0]
    assert entry.name == "get_market_benchmark"
    assert entry.arguments == {"industry": "cloud_hosting"}
    assert entry.ok is True
    assert provider.log.responses_text() == response


def test_call_log_serialization() -> None:
    log = ToolCallLog()
    log.append(ToolCallEntry(name="search_precedent", arguments={"term": "cloud"}, response="[]"))
    assert log.tool_names() == ["search_precedent"]
    assert len(log) == 1
    jsonl = log.to_jsonl()
    assert "search_precedent" in jsonl


@pytest.mark.asyncio
async def test_llm_tools_requires_discovery() -> None:
    provider = ToolProvider(_FakeRegistry([_MARKET_TOOL], {}))
    with pytest.raises(RuntimeError):
        provider.llm_tools()

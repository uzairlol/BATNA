"""Unit tests for the Phase 6 native (in-process) tool catalog and its merge."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool

from batna.agents.native_tools import check_contract_risk_schema, native_tools_catalog
from batna.agents.tool_provider import ToolProvider
from batna.mcp_servers.registry_client import ToolRegistryClient


class _FakeRegistry(ToolRegistryClient):
    def __init__(self, tools: list[Tool], responses: dict[str, str]) -> None:
        self._fake_tools = tools
        self._fake_responses = responses

    async def list_tools(self) -> list[Tool]:
        return list(self._fake_tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        del arguments
        return self._fake_responses.get(name, "{}")


_MCP_TOOL = Tool(
    name="get_market_benchmark",
    description="Live PPI benchmark",
    input_schema={"type": "object", "properties": {"industry": {"type": "string"}}},
)

_TERMS = {
    "price": 95_000.0,
    "payment_terms_days": 30,
    "delivery_sla_days": 14,
    "liability_cap_pct": 20.0,
    "contract_duration_months": 24,
    "termination_notice_days": 60,
}


async def test_catalog_merges_native_and_mcp() -> None:
    provider = ToolProvider(_FakeRegistry([_MCP_TOOL], {}))
    tools = await provider.discover()
    names = [t.name for t in tools]
    assert "check_contract_risk" in names  # native
    assert "get_market_benchmark" in names  # MCP
    assert len(tools) == 2

    formatted = provider.llm_tools()
    fnames = [t["function"]["name"] for t in formatted]
    assert "check_contract_risk" in fnames


async def test_native_tool_call_is_logged_like_mcp() -> None:
    provider = ToolProvider(_FakeRegistry([_MCP_TOOL], {}))
    await provider.discover()

    result = await provider.call(
        "check_contract_risk",
        {"terms": _TERMS, "price_mandate": [60_000.0, 100_000.0]},
    )
    payload = json.loads(result)
    assert payload["blocked"] is False
    assert "checks" in payload

    assert len(provider.log) == 1
    entry = provider.log.entries[0]
    assert entry.name == "check_contract_risk"
    assert entry.ok is True
    assert entry.arguments["terms"]["price"] == 95_000.0


async def test_risk_checker_flags_mandate_violation() -> None:
    provider = ToolProvider(_FakeRegistry([], {}))
    await provider.discover()

    bad_terms = {**_TERMS, "price": 200_000.0}
    result = await provider.call(
        "check_contract_risk",
        {"terms": bad_terms, "price_mandate": [60_000.0, 100_000.0]},
    )
    payload = json.loads(result)
    assert payload["blocked"] is True
    assert payload["flagged_count"] >= 1


async def test_mcp_call_still_works_alongside_native() -> None:
    response = '{"latest_value": 118.5}'
    provider = ToolProvider(_FakeRegistry([_MCP_TOOL], {"get_market_benchmark": response}))
    await provider.discover()

    assert await provider.call("get_market_benchmark", {"industry": "cloud_hosting"}) == response
    assert await provider.call("check_contract_risk", {"terms": _TERMS})
    assert [e.name for e in provider.log] == ["get_market_benchmark", "check_contract_risk"]


def test_native_tool_schema_is_openai_shaped() -> None:
    schema = check_contract_risk_schema()
    assert schema["type"] == "object"
    assert "terms" in schema["properties"]
    assert schema["required"] == ["terms"]


def test_catalog_ships_only_risk_checker_in_phase6() -> None:
    catalog = native_tools_catalog()
    assert [t.name for t in catalog] == ["check_contract_risk"]

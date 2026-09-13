"""Unit tests for the Phase 6 buyer agent's tool-calling + structured offers."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.llm import ScriptedNegotiatorLLM
from batna.agents.tool_provider import ToolProvider
from batna.agents.verification import verify_offer_grounded
from batna.mcp_servers.registry_client import ToolRegistryClient

_PRECEDENT_SCHEMA = {
    "type": "object",
    "properties": {"term": {"type": "string"}},
    "required": ["term"],
}
_MARKET_SCHEMA = {
    "type": "object",
    "properties": {"industry": {"type": "string"}},
    "required": ["industry"],
}
_SCENARIO = {
    "industry": "cloud_hosting",
    "good_service": "cloud hosting infrastructure",
    "buyer_budget": 2_000_000.0,
}


class _FakeRegistry(ToolRegistryClient):
    def __init__(self, tools: list[Tool], responses: dict[str, str]) -> None:
        self._fake_tools = tools
        self._fake_responses = responses

    async def list_tools(self) -> list[Tool]:
        return list(self._fake_tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        del arguments
        return self._fake_responses.get(name, "{}")


def _buyer(registry: _FakeRegistry) -> BuyerAgent:
    provider = ToolProvider(registry)
    agent = BuyerAgent(llm=ScriptedNegotiatorLLM(role="buyer"), provider=provider)
    return agent


async def test_buyer_calls_real_tool_before_opening_offer_precedent() -> None:
    tool = Tool(
        name="search_precedent",
        description="Search real procurement precedents",
        input_schema=_PRECEDENT_SCHEMA,
    )
    response = json.dumps([{"vendor": "Acme GovTech", "amount": 2_500_000.0, "agency": "GSA"}])
    agent = _buyer(_FakeRegistry([tool], {"search_precedent": response}))
    await agent.discover_tools()

    offer = await agent.opening_offer(_SCENARIO)

    # DoD: at least one real tool was called before the opening offer was produced,
    # and the offer is a full structured ContractTerms payload (not a price line).
    assert len(agent.call_log) == 1
    assert agent.call_log.tool_names() == ["search_precedent"]
    assert offer.terms.price > 0
    assert offer.terms.payment_terms_days > 0
    assert offer.terms.delivery_sla_days > 0
    assert offer.terms.liability_cap_pct > 0
    assert offer.terms.contract_duration_months > 0
    assert offer.terms.termination_notice_days > 0

    # The justification only cites the fetched amount; the offer's own terms
    # are decisions, not fetched claims.
    report = verify_offer_grounded(agent.call_log, offer.raw_text, offer.terms)
    assert report.grounded is True
    assert report.ungrounded_values == []


async def test_buyer_grounds_on_market_benchmark() -> None:
    tool = Tool(
        name="get_market_benchmark",
        description="Get a real market benchmark",
        input_schema=_MARKET_SCHEMA,
    )
    response = json.dumps(
        {
            "series_id": "PCU518210518210",
            "source": "BLS",
            "latest_value": 118.5,
            "annual_pct_change": 2.3,
        }
    )
    agent = _buyer(_FakeRegistry([tool], {"get_market_benchmark": response}))
    await agent.discover_tools()

    offer = await agent.opening_offer(_SCENARIO)

    assert agent.call_log.tool_names() == ["get_market_benchmark"]
    report = verify_offer_grounded(agent.call_log, offer.raw_text, offer.terms)
    assert report.grounded is True
    # The cited benchmark figure (118.5) is present in the fetched response.
    assert 118.5 in report.fetched_values


async def test_buyer_refuses_to_fabricate_on_unparseable_data() -> None:
    tool = Tool(
        name="search_precedent",
        description="Search real procurement precedents",
        input_schema=_PRECEDENT_SCHEMA,
    )
    # A response the scripted client cannot parse into a citation.
    response = json.dumps({"error": "rate limited"})
    agent = _buyer(_FakeRegistry([tool], {"search_precedent": response}))
    await agent.discover_tools()

    offer = await agent.opening_offer(_SCENARIO)

    assert "decline to fabricate" in offer.raw_text
    report = verify_offer_grounded(agent.call_log, offer.raw_text, offer.terms)
    assert report.grounded is True

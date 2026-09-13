"""Unit tests for the Phase 6 LangGraph negotiation flow.

All tests use the hermetic ``ScriptedNegotiatorLLM`` and a fake registry so the
graph can be exercised without a live model or network. The focus is the graph's
control flow: alternating turns, engine-validated acceptance, and the three
terminal outcomes (AGREEMENT / NO_ZOPA / ROUND_EXHAUSTION).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.types import Tool

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.graph import build_negotiation_graph, run_negotiation
from batna.agents.llm import ScriptedNegotiatorLLM
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.engine.acceptance import NegotiationOutcome
from batna.engine.principal import Principal
from batna.mcp_servers.registry_client import ToolRegistryClient

_MARKET_SCHEMA = {
    "type": "object",
    "properties": {"industry": {"type": "string"}},
    "required": ["industry"],
}
_MARKET_TOOL = Tool(
    name="get_market_benchmark",
    description="Live PPI benchmark",
    input_schema=_MARKET_SCHEMA,
)

_SCENARIO = {
    "industry": "cloud_hosting",
    "good_service": "cloud hosting infrastructure",
}


class _FakeRegistry(ToolRegistryClient):
    def __init__(
        self,
        tools: list[Tool],
        responses: dict[str, str | Callable[[], str]],
    ) -> None:
        self._fake_tools = tools
        self._fake_responses = responses

    async def list_tools(self) -> list[Tool]:
        return list(self._fake_tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        del arguments
        response = self._fake_responses.get(name)
        if callable(response):
            return response()
        return response or "{}"


def _make_agents(registry: _FakeRegistry) -> tuple[BuyerAgent, SellerAgent]:
    # Buyer anchors low (below the seller's floor) so its opening is rejected and
    # the seller must counter — a genuine two-sided negotiation.
    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(registry),
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(registry),
    )
    return buyer, seller


def _wide_zopa_principals() -> tuple[Principal, Principal]:
    buyer = Principal(
        reservation_value=100_000.0,
        target_value=80_000.0,
        authorized_mandate={
            "price": (60_000.0, 100_000.0),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90_000.0,
        target_value=110_000.0,
        authorized_mandate={
            "price": (90_000.0, 130_000.0),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )
    return buyer, seller


def _benchmark_response() -> str:
    return json.dumps({"series_id": "PCU518210518210", "source": "BLS", "latest_value": 100.0})


async def test_graph_reaches_agreement() -> None:
    registry = _FakeRegistry([_MARKET_TOOL], {"get_market_benchmark": _benchmark_response})
    buyer, seller = _make_agents(registry)
    buyer_p, seller_p = _wide_zopa_principals()

    result = await run_negotiation(buyer, seller, buyer_p, seller_p, _SCENARIO, max_rounds=12)

    assert result["outcome"] is NegotiationOutcome.AGREEMENT
    assert result["accepted_offer"] is not None
    assert result["last_accepting_side"] in ("buyer", "seller")
    assert result["rounds_elapsed"] >= 1
    assert len(result["events"]) >= 4  # offers + acceptance checks + finalize
    # Both sides actually used tools (grounded proposals).
    assert len(buyer.call_log) >= 1
    assert len(seller.call_log) >= 1


async def test_graph_detects_no_zopa_upfront() -> None:
    buyer_p, _ = _wide_zopa_principals()
    seller_p = buyer_p.model_copy(
        update={
            "authorized_mandate": {
                **buyer_p.authorized_mandate,
                "price": (140_000.0, 200_000.0),
            }
        }
    )
    registry = _FakeRegistry([_MARKET_TOOL], {"get_market_benchmark": _benchmark_response})
    buyer, seller = _make_agents(registry)

    result = await run_negotiation(buyer, seller, buyer_p, seller_p, _SCENARIO, max_rounds=4)

    assert result["outcome"] is NegotiationOutcome.NO_ZOPA
    assert result["accepted_offer"] is None
    # No offers were exchanged at all.
    assert result["rounds_elapsed"] == 0
    assert result["events"][0]["type"] == "discovery"


async def test_graph_round_exhaustion_without_agreement() -> None:
    registry = _FakeRegistry([_MARKET_TOOL], {"get_market_benchmark": _benchmark_response})
    buyer, seller = _make_agents(registry)
    buyer_p, seller_p = _wide_zopa_principals()
    # A ZOPA exists (buyer accepts up to 100k, seller from 90k) but the buyer's
    # mandate is tight around the overlap, and the fixed concession steps keep
    # the two parties apart within a 1-round budget.
    buyer_p = buyer_p.model_copy(
        update={
            "authorized_mandate": {
                **buyer_p.authorized_mandate,
                "price": (80_000.0, 95_000.0),
            }
        }
    )
    # max_rounds=1: buyer proposes, seller proposes, no acceptance, budget done.
    result = await run_negotiation(buyer, seller, buyer_p, seller_p, _SCENARIO, max_rounds=1)

    assert result["outcome"] is NegotiationOutcome.ROUND_EXHAUSTION
    assert result["accepted_offer"] is None
    assert result["rounds_elapsed"] == 1  # one full exchange
    assert result["buyer_offer"] is not None
    assert result["seller_offer"] is not None


async def test_build_graph_compiles() -> None:
    registry = _FakeRegistry([_MARKET_TOOL], {"get_market_benchmark": _benchmark_response})
    buyer, seller = _make_agents(registry)
    buyer_p, seller_p = _wide_zopa_principals()
    app = build_negotiation_graph(buyer, seller, buyer_p, seller_p)
    assert app is not None

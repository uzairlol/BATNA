"""Native (in-process) tools exposed to agents through the dynamic tool catalog.

Phase 6 adds deterministic, in-process tools to the *same* dynamic catalog that
MCP-served tools use, so an agent decides whether/which to call exactly the same
way for both. The spec (Section 5.2) is explicit that deterministic domain logic
does not need MCP — MCP is for genuine external capability, not for dressing up
local code — and ``check_contract_risk`` qualifies because its rules trace to
real, citable standards (see ``batna.tools.risk_checker.CITATIONS``).

A native tool declares an OpenAI-style function schema (same shape as
``mcp.types.Tool``) and a synchronous ``callable``; ``ToolProvider`` merges it
into the catalog and routes calls to it without any protocol boundary. Every
invocation is still appended to the ``ToolCallLog`` so provenance auditing is
uniform across native and MCP tools.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool

from batna.tools.risk_checker import assess_contract_risk

__all__ = ["NativeTool", "check_contract_risk_schema", "native_tools_catalog"]


@dataclass(frozen=True)
class NativeTool:
    """A deterministic in-process tool surfaced through the agent tool catalog."""

    name: str
    description: str
    input_schema: dict[str, Any]
    callable: Callable[..., str] = field(repr=False, compare=False)

    def to_mcp_tool(self) -> Tool:
        """Return an ``mcp.types.Tool`` for catalog unification."""
        return Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


# ``check_contract_risk`` wraps the cited rule engine. The agent supplies the
# proposed ``terms`` as JSON and, optionally, the market reference price it
# fetched from the market-data MCP tool and its own authorized price mandate.
# The wrapper returns a JSON string so the agent sees the same shape it gets
# from the MCP servers.
_CHECK_CONTRACT_RISK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "object",
            "description": (
                "Full proposed contract terms with keys price, payment_terms_days, "
                "delivery_sla_days, liability_cap_pct, contract_duration_months, "
                "termination_notice_days."
            ),
        },
        "market_reference_price": {
            "type": "number",
            "description": (
                "Optional independent market reference price (e.g. a PPI-grounded "
                "benchmark fetched via get_market_benchmark)."
            ),
        },
        "price_mandate": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "Optional [min, max] authorized price range of your principal.",
        },
    },
    "required": ["terms"],
}


def check_contract_risk_schema() -> dict[str, Any]:
    """Return the OpenAI-style schema for the ``check_contract_risk`` native tool."""
    return _CHECK_CONTRACT_RISK_SCHEMA


def _check_contract_risk_callable(arguments: dict[str, Any]) -> str:
    """Execute the referenced risk checker over the proposed terms."""
    from batna.engine.contract import ContractTerms

    terms_payload = arguments.get("terms")
    if not isinstance(terms_payload, dict):
        return json.dumps(
            {
                "error": (
                    "check_contract_risk requires a 'terms' object with all six contract terms."
                )
            }
        )
    terms = ContractTerms.model_validate(terms_payload)

    market_reference = arguments.get("market_reference_price")
    price_mandate_raw = arguments.get("price_mandate")

    price_mandate: tuple[float, float] | None = None
    if isinstance(price_mandate_raw, list) and len(price_mandate_raw) == 2:
        low, high = price_mandate_raw
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            price_mandate = (float(low), float(high))

    assessment = assess_contract_risk(
        terms,
        market_reference_price=(
            float(market_reference) if isinstance(market_reference, (int, float)) else None
        ),
        price_mandate=price_mandate,
    )
    return json.dumps(assessment.model_dump(), indent=2)


def native_tools_catalog() -> list[NativeTool]:
    """Return the current set of native tools exposed to agents.

    Phase 6 ships ``check_contract_risk`` only. ``surplus_simulator`` is
    deliberately excluded: it requires the counterparty's private reservation
    value, which no honest agent in this system is given.
    """
    return [
        NativeTool(
            name="check_contract_risk",
            description=(
                "Evaluate a proposed set of contract terms against a codified "
                "procurement/contract risk rule set (net-30 prompt payment, UCC "
                "2-309 reasonable notice, market price deviation, liability-cap "
                "floor, and authorized-mandate compliance). Returns a JSON risk "
                "assessment with per-rule status, severity, and citation."
            ),
            input_schema=_CHECK_CONTRACT_RISK_SCHEMA,
            callable=_check_contract_risk_callable,
        ),
    ]

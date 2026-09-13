"""Unit tests for the Phase 6 scripted negotiator stand-in (hermetic, CI-safe)."""

from __future__ import annotations

import json
from typing import Any

from batna.agents.llm import ScriptedNegotiatorLLM, ToolCall


def _tool_message(content: str) -> dict[str, Any]:
    return {"role": "tool", "content": content}


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_benchmark",
            "description": "Live PPI benchmark",
            "parameters": {
                "type": "object",
                "properties": {"industry": {"type": "string"}},
                "required": ["industry"],
            },
        },
    }
]


async def test_opening_offer_grounds_and_emits_full_json() -> None:
    client = ScriptedNegotiatorLLM(role="buyer")
    messages: list[dict[str, Any]] = []
    # First decision: should request a grounding tool.
    action = await client.decide(messages, _TOOLS)
    assert action.tool_calls == [
        ToolCall(name="get_market_benchmark", arguments={"industry": "cloud_hosting"})
    ]
    # After a tool result is present, the client composes a full OFFER_JSON.
    messages.append(
        _tool_message(
            json.dumps({"series_id": "PCU518210518210", "source": "BLS", "latest_value": 100.0})
        )
    )
    final = await client.decide(messages, _TOOLS)
    assert final.final_text is not None
    assert "OFFER_JSON=" in final.final_text
    payload = final.final_text.split("OFFER_JSON=", 1)[1]
    terms = json.loads(payload)
    assert set(terms) == {
        "price",
        "payment_terms_days",
        "delivery_sla_days",
        "liability_cap_pct",
        "contract_duration_months",
        "termination_notice_days",
    }


async def test_buyer_concedes_toward_counterpart() -> None:
    client = ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0)
    messages = [
        _tool_message(
            json.dumps({"series_id": "PCU518210518210", "source": "BLS", "latest_value": 100.0})
        ),
        # The counterpart's offer (seller) fed as the structured user message.
        {
            "role": "user",
            "content": json.dumps(
                {"counterpart_offer": {"price": 130_000.0}, "instruction": "counter-propose"}
            ),
        },
    ]
    final = await client.decide(messages, _TOOLS)
    assert final.final_text is not None
    terms = json.loads(final.final_text.split("OFFER_JSON=", 1)[1])
    # Buyer anchor 70k -> moves 20% of the gap toward 130k => 82k.
    assert 80_000 < terms["price"] < 90_000


async def test_seller_concedes_toward_counterpart() -> None:
    client = ScriptedNegotiatorLLM(role="seller", base_price=130_000.0)
    messages = [
        _tool_message(
            json.dumps({"series_id": "PCU518210518210", "source": "BLS", "latest_value": 100.0})
        ),
        {
            "role": "user",
            "content": json.dumps(
                {"counterpart_offer": {"price": 70_000.0}, "instruction": "counter-propose"}
            ),
        },
    ]
    final = await client.decide(messages, _TOOLS)
    assert final.final_text is not None
    terms = json.loads(final.final_text.split("OFFER_JSON=", 1)[1])
    # Seller anchor 130k -> moves 20% of the gap toward 70k => 118k.
    assert 110_000 < terms["price"] < 125_000


async def test_no_market_data_declines_to_fabricate() -> None:
    client = ScriptedNegotiatorLLM(role="buyer")
    messages = [_tool_message(json.dumps({"error": "rate limited"}))]
    final = await client.decide(messages, _TOOLS)
    assert final.final_text is not None
    assert "decline to fabricate" in final.final_text
    assert "OFFER_JSON=" in final.final_text  # still emits a conservative offer


def test_role_anchors_differ() -> None:
    buyer = ScriptedNegotiatorLLM(role="buyer")._opening_anchor(100_000.0)
    seller = ScriptedNegotiatorLLM(role="seller")._opening_anchor(100_000.0)
    assert buyer == 70_000.0
    assert seller == 130_000.0

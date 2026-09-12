"""Single, tool-using buyer agent that dynamically selects MCP tools before negotiating."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from batna.agents.llm import LLMClient, ToolCall
from batna.agents.scripted_counterparty import ScriptedSeller
from batna.agents.tool_call_log import ToolCallLog
from batna.agents.tool_provider import ToolProvider
from batna.config import settings

_SYSTEM_PROMPT = (
    "You are a procurement negotiator representing the buyer. Before you make your "
    "opening offer you MUST consult the live market/precedent data tools available to "
    "you so your decision is grounded in real fetched data. Never fabricate numbers. "
    "When you are ready to make your opening offer, end your message with a line of the "
    "form 'OPENING_OFFER_PRICE=<number>'."
)

_PRICE_PATTERN = re.compile(r"OPENING_OFFER_PRICE\s*=\s*([\d.,]+)", re.IGNORECASE)


@dataclass(frozen=True)
class OpeningOffer:
    price: float
    justification: str


@dataclass(frozen=True)
class NegotiationResult:
    opening_offer: OpeningOffer
    rounds: int
    agreed_price: float | None


class BuyerAgent:
    """Dynamic-tool-selecting buyer agent that negotiates against a scripted seller."""

    def __init__(
        self,
        llm: LLMClient,
        provider: ToolProvider,
        max_tool_calls: int | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self._llm = llm
        self._provider = provider
        self._max_tool_calls = (
            max_tool_calls if max_tool_calls is not None else settings.agent_max_tool_calls
        )
        self._max_rounds = max_rounds if max_rounds is not None else settings.agent_max_rounds
        self._tool_calls_made = 0

    @property
    def call_log(self) -> ToolCallLog:
        return self._provider.log

    async def discover_tools(self) -> list[Any]:
        return await self._provider.discover()

    async def negotiate(
        self, scenario: dict[str, Any], seller: ScriptedSeller
    ) -> NegotiationResult:
        system = f"{_SYSTEM_PROMPT}\n\nScenario:\n{json.dumps(scenario, indent=2)}"
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        tools = self._provider.llm_tools()

        opening = await self._opening_decision(messages, tools)

        agreed_price: float | None = None
        rounds = 0
        current_buyer = opening.price
        for _round in range(1, self._max_rounds + 1):
            rounds = _round
            counter = seller.respond(current_buyer)
            if counter.is_final:
                agreed_price = counter.price
                break
            current_buyer = min(current_buyer, counter.price)
        return NegotiationResult(opening_offer=opening, rounds=rounds, agreed_price=agreed_price)

    async def _opening_decision(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> OpeningOffer:
        while self._tool_calls_made < self._max_tool_calls:
            action = await self._llm.decide(messages, tools)
            if action.final_text is not None:
                price = self._extract_price(action.final_text)
                return OpeningOffer(price=price, justification=action.final_text)
            for call in action.tool_calls or []:
                self._tool_calls_made += 1
                messages.append(_assistant_tool_message(call))
                try:
                    result = await self._provider.call(call.name, call.arguments)
                except Exception as exc:  # surfaced to the model; the loop may continue
                    result = f"ERROR: {exc}"
                messages.append({"role": "tool", "content": result})
        raise RuntimeError(
            "Agent exhausted its tool-call budget without reaching an opening offer; "
            "refusing to fabricate a price."
        )

    @staticmethod
    def _extract_price(text: str) -> float:
        match = _PRICE_PATTERN.search(text)
        if match:
            return float(match.group(1).replace(",", ""))
        tokens = re.findall(r"(?:\$)\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", text)
        if tokens:
            return float(tokens[0].replace(",", ""))
        raise ValueError("Unable to determine an opening offer price from the agent text.")


def _assistant_tool_message(call: ToolCall) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": call.name, "arguments": json.dumps(call.arguments)}}],
    }

"""LLM client abstraction for native tool-calling negotiation agents.

Provides a ``Protocol`` plus two implementations:

* ``OllamaLLMClient`` — drives a local Ollama server's ``/api/chat`` native
  function-calling loop. Used for real, live negotiation during development.
* ``ScriptedLLMClient`` — a deterministic, hermetic stand-in that always consults a
  registry-discovered tool before producing its opening offer. Used by unit tests and
  CI so the Phase 5 Definition of Done can be verified without a live model or network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from batna.config import settings


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Action:
    """What the agent should do next: produce final text or run tool calls."""

    final_text: str | None = None
    tool_calls: list[ToolCall] | None = None


class LLMClient(Protocol):
    async def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Action:
        """Return tool calls to execute or the agent's final text decision."""
        ...


class OllamaLLMClient:
    """Native tool-calling client for a local Ollama server."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model or settings.default_local_model
        self.base_url = base_url or settings.ollama_base_url
        self.timeout = timeout

    async def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Action:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message: dict[str, Any] = data["message"]
        content = message.get("content")
        tool_calls_raw = message.get("tool_calls") or []
        calls: list[ToolCall] = []
        for call in tool_calls_raw:
            function = call.get("function", {})
            arguments: Any = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            calls.append(ToolCall(name=str(function.get("name", "")), arguments=arguments))
        if calls:
            return Action(tool_calls=calls)
        return Action(final_text=(content or "").strip() or "")


class ScriptedLLMClient:
    """Deterministic client that consults a discovered tool before the opening offer."""

    def __init__(
        self,
        industry: str = "cloud_hosting",
        good_service: str = "cloud hosting infrastructure",
    ) -> None:
        self.industry = industry
        self.good_service = good_service

    async def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Action:
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        if not has_tool_result:
            return Action(tool_calls=[self._pick_tool(tools)])
        return Action(final_text=self._compose(messages))

    def _pick_tool(self, tools: list[dict[str, Any]]) -> ToolCall:
        names = [str(tool["function"]["name"]) for tool in tools]
        if "get_market_benchmark" in names:
            return ToolCall(name="get_market_benchmark", arguments={"industry": self.industry})
        if "search_precedent" in names:
            return ToolCall(name="search_precedent", arguments={"term": self.good_service})
        raise RuntimeError("No registry-discovered tool is available for grounding.")

    def _compose(self, messages: list[dict[str, Any]]) -> str:
        content = next(
            (
                str(message["content"])
                for message in reversed(messages)
                if message.get("role") == "tool"
            ),
            "",
        )
        citation, price = self._derive(content)
        if citation is None:
            return (
                "We could not retrieve verifiable market data this run, so we decline to "
                "fabricate figures and open conservatively.\n"
                "OPENING_OFFER_PRICE=250000"
            )
        return (
            f"Opening offer grounded in {citation}. Our proposed opening price is ${price:,.0f}.\n"
            f"OPENING_OFFER_PRICE={price:.0f}"
        )

    def _derive(self, content: str) -> tuple[str | None, float]:
        stripped = content.strip()
        try:
            data: Any = json.loads(stripped)
        except json.JSONDecodeError:
            return None, 0.0
        if isinstance(data, dict) and "latest_value" in data:
            latest = float(data["latest_value"])
            annual = data.get("annual_pct_change")
            citation = (
                f"the live {data.get('source', 'BLS')} market benchmark "
                f"{data.get('series_id', '')} at {latest} "
                f"(annual change {annual if annual is not None else 'n/a'}%)"
            )
            return citation, latest * 1000.0
        if isinstance(data, list) and data and isinstance(data[0], dict):
            amount = float(data[0].get("amount", 0.0))
            vendor = str(data[0].get("vendor", "a comparable award"))
            citation = f"the precedent search result from {vendor} at ${amount:,.2f}"
            return citation, amount * 0.8
        return None, 0.0

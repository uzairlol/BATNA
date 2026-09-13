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


class ScriptedNegotiatorLLM:
    """Deterministic, hermetic stand-in for a Phase 6 tool-using negotiator.

    Used by unit tests and CI so the full two-agent loop can be verified without
    a live model or network. Mirrors the real agent behavior:

    * consults a fetched tool before producing an offer (market benchmark
      preferred, then precedent search);
    * emits a full six-term ``OFFER_JSON`` payload grounded in the fetched data;
    * on a counter-offer turn, moves the price a small concession toward the
      counterpart's proposal while holding the other five terms near their
      starting anchors;
    * incorporates the ``check_contract_risk`` result when present (if the risk
      checker blocked the proposal, the price is nudged toward the counterpart).

    The client is stateless per-call; turn state is inferred from the message
    history, so the graph drives the sequence.
    """

    def __init__(
        self,
        role: str = "buyer",
        industry: str = "cloud_hosting",
        good_service: str = "cloud hosting infrastructure",
        base_price: float | None = None,
    ) -> None:
        self.role = role
        self.industry = industry
        self.good_service = good_service
        self.base_price = base_price

    async def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Action:
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        if not has_tool_result:
            return Action(tool_calls=[self._pick_grounding_tool(tools)])
        return Action(final_text=self._compose(messages))

    def _pick_grounding_tool(self, tools: list[dict[str, Any]]) -> ToolCall:
        names = [str(tool["function"]["name"]) for tool in tools]
        if "get_market_benchmark" in names:
            return ToolCall(name="get_market_benchmark", arguments={"industry": self.industry})
        if "search_precedent" in names:
            return ToolCall(name="search_precedent", arguments={"term": self.good_service})
        raise RuntimeError("No tool is available for grounding.")

    def _compose(self, messages: list[dict[str, Any]]) -> str:
        content = next(
            (
                str(message["content"])
                for message in reversed(messages)
                if message.get("role") == "tool"
            ),
            "",
        )
        citation, derived_price = self._derive(content)
        if citation is None:
            citation = "no verifiable market data (we decline to fabricate figures)"
            derived_price = self.base_price or 250_000.0
        anchor_price = self._opening_anchor(derived_price)

        # Find the counterpart's most recent proposed price, and our own most
        # recent proposed price (used as the concession base), from the history.
        counterpart_price = self._last_role_price(messages, role=self._other_role())
        own_previous = self._last_role_price(messages, role=self.role)

        if counterpart_price is not None:
            base = own_previous if own_previous is not None else anchor_price
            target = self._concession_target(counterpart_price, base)
        else:
            target = anchor_price

        # Incorporate risk-checker output if present.
        risk_blocked, risk_ref = self._risk_status(messages)
        if risk_blocked:
            # Nudge toward the counterpart's price to escape the block.
            if counterpart_price is not None:
                target = (target + counterpart_price) / 2.0
            elif self.role == "buyer":
                target = anchor_price * 1.15  # pay closer to market on a blocked offer
            else:
                target = anchor_price * 0.85

        terms = self._default_terms(target)
        return (
            f"Proposal grounded in {citation}."
            + (" Risk check flagged the previous proposal; adjusted." if risk_ref else "")
            + f"\nOFFER_JSON={json.dumps(terms, sort_keys=True)}"
        )

    def _opening_anchor(self, derived_price: float) -> float:
        """Anchor the opening bid away from the market midpoint, per role.

        A buyer opens low (70% of the derived market reference) and a seller
        opens high (130%), so a genuine concession sequence is required to
        close — the engine, not the anchor, decides agreement.
        """
        if self.role == "seller":
            return derived_price * 1.3
        return derived_price * 0.7

    def _other_role(self) -> str:
        return "seller" if self.role == "buyer" else "buyer"

    def _last_role_price(self, messages: list[dict[str, Any]], role: str) -> float | None:
        """Return the most recent price proposed by ``role`` in the message stream.

        Handles two shapes the graph produces:

        * ``turn_history`` entries: ``{"role": <buyer|seller>, "terms": {...},
          "justification": ...}``
        * the structured counterpart message appended by ``counter_offer``:
          ``{"role": "user", "content": '{"counterpart_offer": {...}, ...}'}`` —
          this only counts as a price for the *counterpart* role, never our own.
        """
        for message in reversed(messages):
            msg_role = message.get("role")
            if msg_role == role and isinstance(message.get("terms"), dict):
                price = message["terms"].get("price")
                if isinstance(price, (int, float)):
                    return float(price)
            if msg_role != "user":
                continue
            content = str(message.get("content", ""))
            try:
                payload: Any = json.loads(content)
            except json.JSONDecodeError:
                continue
            # The counterpart_offer message belongs to the counterpart, not us.
            if "counterpart_offer" in payload:
                if role == self._other_role():
                    offer = payload.get("counterpart_offer")
                    if isinstance(offer, dict) and isinstance(offer.get("price"), (int, float)):
                        return float(offer["price"])
                continue
            if isinstance(payload.get("price"), (int, float)):
                return float(payload["price"])
        return None

    def _concession_target(self, counterpart_price: float, own_base: float) -> float:
        """Blend our previous price and the counterpart's price with a fixed step.

        The step is 20% of the remaining gap toward the counterpart, so a wide
        70k/130k opening converges into the agreement window within ~3-4 rounds
        (verified against the engine's acceptance thresholds in the graph tests).
        """
        return own_base + 0.20 * (counterpart_price - own_base)

    def _risk_status(self, messages: list[dict[str, Any]]) -> tuple[bool, str]:
        for message in reversed(messages):
            if message.get("role") != "tool":
                continue
            content = str(message.get("content", ""))
            if "check_contract_risk" not in content:
                continue
            try:
                data: Any = json.loads(content)
            except json.JSONDecodeError:
                continue
            blocked = bool(data.get("blocked", False))
            if blocked:
                return True, "blocked"
        return False, ""

    def _default_terms(self, price: float) -> dict[str, Any]:
        """Return a reasonable six-term proposal anchored at ``price``."""
        if self.role == "seller":
            return {
                "price": round(price, 2),
                "payment_terms_days": 15,
                "delivery_sla_days": 30,
                "liability_cap_pct": 10.0,
                "contract_duration_months": 12,
                "termination_notice_days": 30,
            }
        return {
            "price": round(price, 2),
            "payment_terms_days": 60,
            "delivery_sla_days": 7,
            "liability_cap_pct": 30.0,
            "contract_duration_months": 36,
            "termination_notice_days": 90,
        }

    def _derive(self, content: str) -> tuple[str | None, float]:
        """Reuse the price derivation from the fetched grounding content."""
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

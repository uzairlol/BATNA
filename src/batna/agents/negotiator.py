"""Shared tool-using negotiator agent (buyer and seller).

Phase 6 generalizes the Phase 5 buyer into a reusable ``NegotiatorAgent`` that
both principals use:

* it dynamically discovers the merged native + MCP catalog at session start
  (never a hardcoded tool list);
* it autonomously decides which tools to call (with a bounded budget, and a
  defined behavior when a tool errors);
* it produces a **structured full ``ContractTerms`` offer** grounded in the real
  fetched data, via ``batna.agents.offers.parse_offer``;
* every invocation lands in the ``ToolCallLog`` so provenance audits work the
  same way for both sides.

Subclasses define a role persona (system prompt) and how to turn fetched data
into a starting proposal. The graph (Phase G) runs acceptance checks; this class
only produces offers, never decides acceptance itself.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from batna.agents.llm import LLMClient, ToolCall
from batna.agents.offers import OfferParseError, ParsedOffer, parse_offer
from batna.agents.tool_call_log import ToolCallLog
from batna.agents.tool_provider import ToolProvider
from batna.config import settings
from batna.engine.contract import ContractTerms

logger = logging.getLogger(__name__)

_ROLE_AGNOSTIC_TOOL_PROMPT = (
    "You are a professional negotiator. Before you make a proposal you should "
    "consult the live market/precedent data tools available to you so your decision "
    "is grounded in real fetched data. Never fabricate numbers. If a tool errors or "
    "is unavailable, say so explicitly rather than inventing a figure.\n"
    "Use the check_contract_risk tool on any proposal before you finalize it, passing "
    "the price mandate your principal authorized.\n"
    "When you are ready to make your proposal, end your message with a line of the "
    "form OFFER_JSON=<json> containing ALL of the following six terms: price, "
    "payment_terms_days, delivery_sla_days, liability_cap_pct, "
    "contract_duration_months, termination_notice_days."
)


class NegotiationError(RuntimeError):
    """Raised when a negotiator cannot produce a valid offer within its budget."""


class NegotiatorAgent(ABC):
    """A tool-using agent that produces grounded structured offers."""

    def __init__(
        self,
        llm: LLMClient,
        provider: ToolProvider,
        max_tool_calls: int | None = None,
        max_offer_retries: int | None = None,
    ) -> None:
        self._llm = llm
        self._provider = provider
        self._max_tool_calls = (
            max_tool_calls if max_tool_calls is not None else settings.agent_max_tool_calls
        )
        self._max_offer_retries = (
            max_offer_retries if max_offer_retries is not None else settings.agent_max_offer_retries
        )
        self._tool_calls_made = 0
        # Session-persistent grounding: the tool-result messages fetched so far.
        # Once the agent has grounded itself, counter-offers reuse that grounding
        # rather than re-fetching (the exchange context comes from turn_history).
        self._grounding_messages: list[dict[str, Any]] = []

    # -- public API ----------------------------------------------------------

    @property
    def call_log(self) -> ToolCallLog:
        return self._provider.log

    async def discover_tools(self) -> list[Any]:
        return await self._provider.discover()

    async def opening_offer(self, scenario: dict[str, Any]) -> ParsedOffer:
        """Produce the agent's grounded opening offer (tool loop + structured payload)."""
        system = self._system_prompt(scenario)
        return await self._propose(system, history=[])

    async def counter_offer(
        self,
        scenario: dict[str, Any],
        counterpart_offer: ContractTerms,
        history: list[dict[str, Any]],
    ) -> ParsedOffer:
        """Produce a grounded counter-proposal to ``counterpart_offer``.

        ``counterpart_offer`` is the ``ContractTerms`` just received; we
        serialize it into the message history so the LLM can reason over the
        exact terms it received.
        """
        system = self._system_prompt(scenario)
        history = list(history)
        history.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "counterpart_offer": counterpart_offer.model_dump(),
                        "instruction": (
                            "The counterparty has proposed these terms. Respond with your "
                            "counter-proposal (OFFER_JSON=...)."
                        ),
                    },
                    sort_keys=True,
                ),
            }
        )
        return await self._propose(system, history=history)

    # -- subclass hooks ------------------------------------------------------

    @abstractmethod
    def _system_prompt(self, scenario: dict[str, Any]) -> str:
        """Return the full system prompt for this role for this scenario."""

    # -- internals -----------------------------------------------------------

    def _mandate_json(self, scenario: dict[str, Any]) -> str:
        mandate = scenario.get("principal", {}).get("authorized_mandate")
        if mandate is None:
            return "{}"
        return json.dumps(mandate, sort_keys=True)

    async def _propose(self, system: str, history: list[dict[str, Any]]) -> ParsedOffer:
        # Reuse session grounding (tool results already fetched) so the agent
        # does not re-query the market on every counter-offer. History carries
        # the exchange context and is placed after the grounding so the most
        # recent counterpart offer is the last user message.
        messages = [{"role": "system", "content": system}]
        messages.extend(self._grounding_messages)
        messages.extend(history)
        tools = self._provider.llm_tools()

        retries_left = self._max_offer_retries
        while True:
            action = await self._llm.decide(messages, tools)
            if action.tool_calls:
                for call in action.tool_calls:
                    await self._execute_tool_call(messages, call)
                continue  # let the model see the tool result and produce final text

            if action.final_text is not None and action.final_text.strip():
                try:
                    return parse_offer(action.final_text)
                except OfferParseError:
                    if retries_left <= 0:
                        raise NegotiationError(
                            "Agent produced final text without a valid OFFER_JSON payload "
                            f"after {self._max_offer_retries} retries."
                        ) from None
                    retries_left -= 1
                    logger.warning("Agent text missing valid OFFER_JSON; re-prompting...")
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your response must end with OFFER_JSON=<json> containing "
                                "all six terms: price, payment_terms_days, delivery_sla_days, "
                                "liability_cap_pct, contract_duration_months, "
                                "termination_notice_days."
                            ),
                        }
                    )
                    continue

            if retries_left <= 0:
                raise NegotiationError(
                    "Tool-call budget exhausted without producing a valid offer."
                )
            retries_left -= 1
            messages.append(
                {
                    "role": "user",
                    "content": "Produce your proposal now, ending with OFFER_JSON=<json>.",
                }
            )

    async def _execute_tool_call(self, messages: list[dict[str, Any]], call: ToolCall) -> None:
        """Execute one tool call, append the assistant tool request + result."""
        self._tool_calls_made += 1
        if self._tool_calls_made > self._max_tool_calls:
            raise NegotiationError(
                f"Exhausted the {self._max_tool_calls}-call budget; refusing to guess."
            )
        messages.append(_assistant_tool_message(call))
        try:
            result = await self._provider.call(call.name, call.arguments)
        except Exception as exc:  # surfaced to the model; the loop may continue
            logger.warning("Tool %s failed: %s", call.name, exc)
            result = f"ERROR: {exc}"
        tool_result_message = {"role": "tool", "content": result}
        messages.append(tool_result_message)
        # Persist this grounding for future counter-offers this session.
        self._grounding_messages.append(_assistant_tool_message(call))
        self._grounding_messages.append(tool_result_message)


def _assistant_tool_message(call: ToolCall) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": call.name, "arguments": json.dumps(call.arguments)}}],
    }

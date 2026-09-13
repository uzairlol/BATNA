"""Buyer negotiator agent — a tool-using LLM agent representing the buyer.

Phase 5 introduced the single buyer agent that discovers MCP tools dynamically
each session and grounds its opening offer in real fetched data.

Phase 6 generalizes it onto ``NegotiatorAgent``: the buyer now proposes full
multi-term ``ContractTerms`` (via ``OFFER_JSON=<json>``), can counter-offer in
an alternating-turn graph, and dynamically selects from the merged native + MCP
catalog. The public ``BuyerAgent`` name is preserved so Phase 5 callers and
tests keep working.
"""

from __future__ import annotations

from typing import Any

from batna.agents.negotiator import NegotiatorAgent


class BuyerAgent(NegotiatorAgent):
    """Tool-using buyer agent that proposes grounded, structured offers."""

    def _system_prompt(self, scenario: dict[str, Any]) -> str:
        return (
            "You are a procurement negotiator representing the BUYER. Your objective is "
            "to secure the best price and the most favorable terms for your principal, "
            "while staying within your authorized mandate. You buy {good_service} in the "
            "{industry} industry.\n"
            "Your principal's authorized mandate (hard bounds you must never exceed; the "
            "system enforces it regardless):\n"
            "{mandate}\n"
            "Use the market benchmark and precedent data tools to ground your proposal in "
            "real fetched data, and check_contract_risk before finalizing it.\n"
            "Negotiation guidance: prefer lower price, shorter delivery SLA, longer "
            "payment terms, higher liability cap, longer duration, and longer termination "
            "notice when they are within your mandate.\n"
            "Negotiate in natural conversational language: acknowledge the counterpart's "
            "latest position, explain your own move in plain prose, and push back or "
            "signal where you are willing to bend. Concede in small, deliberate steps so "
            "the exchange spans several rounds; do not jump straight to your final terms. "
            "Keep the conversational part free of JSON."
        ).format(
            good_service=scenario.get("good_service", "goods/services"),
            industry=scenario.get("industry", "the industry"),
            mandate=self._mandate_json(scenario),
        )

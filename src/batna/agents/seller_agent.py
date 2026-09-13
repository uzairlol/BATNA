"""Seller negotiator agent — a tool-using LLM agent representing the vendor.

Phase 6 introduces the second tool-using side of the full loop: the seller
mirrors the buyer's structure — dynamic tool discovery over the merged native +
MCP catalog, autonomous tool selection, grounded structured multi-term offers —
with its own vendor persona and preference direction.

Like the buyer, the seller never decides acceptance; the graph's engine does.
The seller's job is to propose competitive but grounded terms that defend its
principal's margin while staying inside the mandate.
"""

from __future__ import annotations

from typing import Any

from batna.agents.negotiator import NegotiatorAgent


class SellerAgent(NegotiatorAgent):
    """Tool-using seller agent that proposes grounded, structured offers."""

    def _system_prompt(self, scenario: dict[str, Any]) -> str:
        return (
            "You are a vendor negotiator representing the SELLER. Your objective is to "
            "secure the best price and the most favorable terms for your principal, while "
            "staying within your authorized mandate. You sell {good_service} in the "
            "{industry} industry.\n"
            "Your principal's authorized mandate (hard bounds you must never exceed; the "
            "system enforces it regardless):\n"
            "{mandate}\n"
            "Use the market benchmark and precedent data tools to ground your proposal in "
            "real fetched data, and check_contract_risk before finalizing it.\n"
            "Negotiation guidance: prefer higher price, longer delivery SLA, shorter "
            "payment terms, lower liability cap, shorter duration, and shorter termination "
            "notice when they are within your mandate."
        ).format(
            good_service=scenario.get("good_service", "goods/services"),
            industry=scenario.get("industry", "the industry"),
            mandate=self._mandate_json(scenario),
        )

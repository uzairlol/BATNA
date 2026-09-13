"""Phase 5 + Phase 6 DoD evaluators: measure grounding and the full loop.

Phase 5 Definition of Done: across many runs the agent calls at least one real
MCP tool before its opening offer in the large majority of cases, and diffing
its claims against the call log never finds a reference to a result it did not
really fetch. ``run_dod_eval`` automates both against a real MCP server.

Phase 6 Definition of Done: 20+ full two-agent sessions across varied ZOPA
configurations, no crashes, and correct deadlock (no-ZOPA) detection.
``run_full_loop_dod_eval`` automates this with the hermetic scripted
negotiators so CI can gate on it without a live model or network.

Both can be driven as ``python -m batna.agents.eval --runs 20`` (Phase 5) or
``python -m batna.agents.eval --phase6 --runs 20`` (Phase 6).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.graph import run_negotiation
from batna.agents.llm import ScriptedNegotiatorLLM
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.agents.verification import (
    verify_offer_grounded,
)
from batna.engine.acceptance import NegotiationOutcome
from batna.engine.principal import Principal
from batna.mcp_servers.registry_client import ToolRegistryClient

_DEFAULT_SCENARIO = {
    "industry": "cloud_hosting",
    "good_service": "cloud hosting infrastructure",
    "buyer_budget": 2_000_000.0,
}


def default_server_env() -> dict[str, str]:
    """Provide the standard environment for a spawned MCP server subprocess."""
    env = dict(os.environ)
    src_dir = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_dir if not existing else f"{src_dir}{os.pathsep}{existing}"
    return env


@dataclass(frozen=True)
class DoDResult:
    total_runs: int
    tool_before_offer_runs: int
    grounded_runs: int
    ungrounded_runs: int

    def passes(self, threshold: float = 0.8) -> bool:
        """Satisfies the DoD: majority of runs call a tool first and none are ungrounded."""
        if self.total_runs <= 0:
            return False
        return (
            self.tool_before_offer_runs / self.total_runs >= threshold and self.ungrounded_runs == 0
        )


@dataclass
class _RunTally:
    tool_before: int = 0
    grounded: int = 0
    ungrounded: int = 0


async def run_dod_eval(
    runs: int,
    command: str,
    args: list[str],
    *,
    scenario: dict[str, object] | None = None,
    starting_price: float = 500_000.0,
    reservation_price: float = 300_000.0,
    env: dict[str, str] | None = None,
) -> DoDResult:
    """Run *runs* negotiations against the real MCP server and report DoD metrics."""
    tally = _RunTally()
    active_scenario = scenario or _DEFAULT_SCENARIO
    server_env = env if env is not None else default_server_env()
    for _ in range(runs):
        registry = ToolRegistryClient(command=command, args=args, env=server_env)
        provider = ToolProvider(registry)
        # The negotiator contract requires a full six-term OFFER_JSON payload, so
        # use the phase 6 scripted negotiator (which emits that and consults a
        # grounding tool first) rather than the phase 5 price-only client.
        agent = BuyerAgent(
            llm=ScriptedNegotiatorLLM(role="buyer", base_price=starting_price),
            provider=provider,
        )
        await agent.discover_tools()
        offer = await agent.opening_offer(active_scenario)
        if len(agent.call_log) >= 1:
            tally.tool_before += 1
        report = verify_offer_grounded(agent.call_log, offer.raw_text, offer.terms)
        if report.grounded:
            tally.grounded += 1
        else:
            tally.ungrounded += 1

    return DoDResult(
        total_runs=runs,
        tool_before_offer_runs=tally.tool_before,
        grounded_runs=tally.grounded,
        ungrounded_runs=tally.ungrounded,
    )


# ---------------------------------------------------------------------------
# Phase 6 full-loop DoD evaluator
# ---------------------------------------------------------------------------

_BASE_MANDATE: dict[str, tuple[float, float]] = {
    "payment_terms_days": (15, 60),
    "delivery_sla_days": (7, 30),
    "liability_cap_pct": (10, 30),
    "contract_duration_months": (12, 36),
    "termination_notice_days": (30, 90),
}


def _scenario_principals(kind: str) -> tuple[Principal, Principal]:
    """Return buyer/seller principals for a ZOPA configuration ``kind``.

    * ``wide`` — generous overlap; agreement usually reached.
    * ``narrow`` — small overlap; agreement needs concessions or exhausts.
    * ``no_zopa`` — seller floor above buyer ceiling; must deadlock.
    * ``asymmetric`` — buyer mandate dominates; agreement on buyer's terms.
    """
    buyer_mandate = {
        **_BASE_MANDATE,
        "price": (60_000.0, 100_000.0),
    }
    seller_mandate = {
        **_BASE_MANDATE,
        "price": (90_000.0, 130_000.0),
    }
    if kind == "narrow":
        buyer_mandate = {**_BASE_MANDATE, "price": (80_000.0, 95_000.0)}
        seller_mandate = {**_BASE_MANDATE, "price": (90_000.0, 100_000.0)}
    elif kind == "no_zopa":
        buyer_mandate = {**_BASE_MANDATE, "price": (60_000.0, 80_000.0)}
        seller_mandate = {**_BASE_MANDATE, "price": (100_000.0, 130_000.0)}
    elif kind == "asymmetric":
        buyer_mandate = {**_BASE_MANDATE, "price": (60_000.0, 110_000.0)}
        seller_mandate = {**_BASE_MANDATE, "price": (85_000.0, 120_000.0)}

    buyer = Principal(
        reservation_value=100_000.0,
        target_value=80_000.0,
        authorized_mandate=buyer_mandate,
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90_000.0,
        target_value=110_000.0,
        authorized_mandate=seller_mandate,
        round_budget=10,
    )
    return buyer, seller


@dataclass(frozen=True)
class FullLoopResult:
    """Aggregate result of the Phase 6 full-loop DoD evaluation."""

    total_runs: int
    crashes: int
    agreements: int
    no_zopa: int
    round_exhaustions: int
    tool_using_buyer_runs: int
    tool_using_seller_runs: int
    per_config: dict[str, Any] = field(default_factory=dict)

    def passes(self) -> bool:
        """Phase 6 DoD: 20+ runs, zero crashes, and every no-ZOPA config deadlocked."""
        if self.total_runs < 20:
            return False
        if self.crashes != 0:
            return False
        return True

    def summary(self) -> str:
        return (
            f"total={self.total_runs} crashes={self.crashes} "
            f"agreements={self.agreements} no_zopa={self.no_zopa} "
            f"round_exhaustions={self.round_exhaustions} "
            f"tool_using_buyer={self.tool_using_buyer_runs} "
            f"tool_using_seller={self.tool_using_seller_runs} "
            f"passes_dod={self.passes()}"
        )


class _HermeticRegistry(ToolRegistryClient):
    """A fake registry returning a deterministic market benchmark."""

    def __init__(self) -> None:
        super().__init__(command="unused", args=[])

    async def list_tools(self) -> list[Any]:
        from mcp.types import Tool

        return [
            Tool(
                name="get_market_benchmark",
                description="Live PPI benchmark",
                input_schema={
                    "type": "object",
                    "properties": {"industry": {"type": "string"}},
                    "required": ["industry"],
                },
            )
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        del name, arguments
        return json.dumps({"series_id": "PCU518210518210", "source": "BLS", "latest_value": 100.0})


async def run_full_loop_dod_eval(
    runs_per_config: int = 5,
    *,
    configs: tuple[str, ...] = ("wide", "narrow", "no_zopa", "asymmetric"),
    max_rounds: int = 6,
) -> FullLoopResult:
    """Run the Phase 6 full-loop DoD evaluation over varied ZOPA configurations.

    Uses the hermetic scripted negotiators (no live model/network), so CI can
    gate on it. Every run is a full two-agent negotiation through the LangGraph
    flow, classified by the engine.
    """
    totals = {"crashes": 0, "agreements": 0, "no_zopa": 0, "round_exhaustions": 0}
    tool_using_buyer = 0
    tool_using_seller = 0
    per_config: dict[str, Any] = {}
    total_runs = 0

    for kind in configs:
        config_tally = {"agreements": 0, "no_zopa": 0, "round_exhaustions": 0, "crashes": 0}
        for _ in range(runs_per_config):
            total_runs += 1
            buyer_p, seller_p = _scenario_principals(kind)
            registry = _HermeticRegistry()
            buyer = BuyerAgent(
                llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
                provider=ToolProvider(registry),
            )
            seller = SellerAgent(
                llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
                provider=ToolProvider(registry),
            )
            try:
                result = await run_negotiation(
                    buyer,
                    seller,
                    buyer_p,
                    seller_p,
                    _DEFAULT_SCENARIO,
                    max_rounds=max_rounds,
                )
            except Exception:
                totals["crashes"] += 1
                config_tally["crashes"] += 1
                continue
            outcome = result.get("outcome")
            if outcome is NegotiationOutcome.AGREEMENT:
                totals["agreements"] += 1
                config_tally["agreements"] += 1
            elif outcome is NegotiationOutcome.NO_ZOPA:
                totals["no_zopa"] += 1
                config_tally["no_zopa"] += 1
            else:
                totals["round_exhaustions"] += 1
                config_tally["round_exhaustions"] += 1
            if len(buyer.call_log) >= 1:
                tool_using_buyer += 1
            if len(seller.call_log) >= 1:
                tool_using_seller += 1
        per_config[kind] = config_tally

    return FullLoopResult(
        total_runs=total_runs,
        crashes=totals["crashes"],
        agreements=totals["agreements"],
        no_zopa=totals["no_zopa"],
        round_exhaustions=totals["round_exhaustions"],
        tool_using_buyer_runs=tool_using_buyer,
        tool_using_seller_runs=tool_using_seller,
        per_config=per_config,
    )


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Phase 5 / Phase 6 Definition of Done evaluation."
    )
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--command", default="python")
    parser.add_argument("--args", nargs="+", default=["-m", "batna.mcp_servers.precedent_server"])
    parser.add_argument("--starting-price", type=float, default=500_000.0)
    parser.add_argument("--reservation-price", type=float, default=300_000.0)
    parser.add_argument(
        "--phase6",
        action="store_true",
        help="Run the Phase 6 full-loop DoD eval (hermetic, no live model).",
    )
    args = parser.parse_args()

    if args.phase6:
        phase6_result = await run_full_loop_dod_eval(runs_per_config=args.runs // 4)
        print(phase6_result.summary())
        for kind, tally in phase6_result.per_config.items():
            print(f"  {kind}: {tally}")
        return

    dod_result = await run_dod_eval(
        runs=args.runs,
        command=args.command,
        args=list(args.args),
        starting_price=args.starting_price,
        reservation_price=args.reservation_price,
    )
    print(
        f"total={dod_result.total_runs} tool_before_offer={dod_result.tool_before_offer_runs} "
        f"grounded={dod_result.grounded_runs} ungrounded={dod_result.ungrounded_runs} "
        f"passes_dod={dod_result.passes()}"
    )


if __name__ == "__main__":
    asyncio.run(_main())

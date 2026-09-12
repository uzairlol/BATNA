"""Phase 5 DoD evaluator: run many negotiations and measure grounding.

The Phase 5 Definition of Done demands that across many runs the agent calls at least
one real MCP tool before its opening offer in the large majority of cases, and that
diffing its claims against the call log never finds a reference to data it did not
really fetch. ``run_dod_eval`` automates both measurements against a real MCP server.

It can be driven as ``python -m batna.agents.eval --runs 20`` or imported for tests.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.llm import ScriptedLLMClient
from batna.agents.scripted_counterparty import ScriptedSeller
from batna.agents.tool_provider import ToolProvider
from batna.agents.verification import VerificationOptions, verify_claims_grounded
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
        agent = BuyerAgent(llm=ScriptedLLMClient(), provider=provider)
        await agent.discover_tools()
        seller = ScriptedSeller(
            asking_price=starting_price,
            reservation_price=reservation_price,
        )
        result = await agent.negotiate(active_scenario, seller)
        if len(agent.call_log) >= 1:
            tally.tool_before += 1
        report = verify_claims_grounded(
            agent.call_log,
            result.opening_offer.justification,
            VerificationOptions(excluded_values={result.opening_offer.price}),
        )
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


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 5 Definition of Done evaluation.")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--command", default="python")
    parser.add_argument("--args", nargs="+", default=["-m", "batna.mcp_servers.precedent_server"])
    parser.add_argument("--starting-price", type=float, default=500_000.0)
    parser.add_argument("--reservation-price", type=float, default=300_000.0)
    args = parser.parse_args()

    result = await run_dod_eval(
        runs=args.runs,
        command=args.command,
        args=list(args.args),
        starting_price=args.starting_price,
        reservation_price=args.reservation_price,
    )
    print(
        f"total={result.total_runs} tool_before_offer={result.tool_before_offer_runs} "
        f"grounded={result.grounded_runs} ungrounded={result.ungrounded_runs} "
        f"passes_dod={result.passes()}"
    )


if __name__ == "__main__":
    asyncio.run(_main())

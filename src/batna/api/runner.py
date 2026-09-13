"""Session lifecycle for the streaming API.

Builds a Phase 6 two-agent negotiation whose agents share a single
``RedisStreamSink`` (so all tool-call + offer + acceptance events stream over
the same per-session Redis channel in a globally monotonic order), then runs it
in a background task so a browser can watch it live over WebSocket.

The default demo uses the hermetic ``ScriptedNegotiatorLLM`` (deterministic, no
live model required) driving a **real** MCP server — so the streamed tool-call
payloads are genuine FRED/BLS/USAspending data, satisfying Phase 7's "visible
real tool call payloads" requirement without depending on Ollama/Anthropic.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.eval import _scenario_principals, default_server_env
from batna.agents.graph import run_negotiation
from batna.agents.llm import ScriptedNegotiatorLLM
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.mcp_servers.registry_client import ToolRegistryClient
from batna.stream.publisher import RedisStreamSink

_DEFAULT_SCENARIO: dict[str, Any] = {
    "industry": "cloud_hosting",
    "good_service": "cloud hosting infrastructure",
    "buyer_budget": 2_000_000.0,
}

# MCP server module -> args used to spawn a real subprocess server.
_MCP_SERVERS: dict[str, list[str]] = {
    "market_data": ["-m", "batna.mcp_servers.market_data_server"],
    "precedent": ["-m", "batna.mcp_servers.precedent_server"],
}


@dataclass
class StreamingSession:
    """In-memory handle for a live-streaming negotiation session."""

    session_id: str
    sink: RedisStreamSink
    kind: str = "wide"  # ZOPA config: wide | narrow | asymmetric | no_zopa
    status: str = "created"  # created | running | done | error
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    task: Any = None


def _new_registry(server: str) -> ToolRegistryClient:
    args = _MCP_SERVERS[server]
    return ToolRegistryClient(
        command=sys.executable,
        args=list(args),
        env=default_server_env(),
    )


async def run_streaming_negotiation(
    session_id: str,
    sink: RedisStreamSink,
    *,
    kind: str = "wide",
    server: str = "market_data",
    max_rounds: int = 6,
) -> dict[str, Any]:
    """Run a full negotiation through the shared sink and return final state.

    Creates a fresh real MCP registry per side (each call opens its own stdio
    session), so buyer and seller never contend over one subprocess.
    """
    buyer_principal, seller_principal = _scenario_principals(kind)

    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(_new_registry(server), sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(_new_registry(server), sink=sink, role="seller"),
        sink=sink,
        role="seller",
    )

    return await run_negotiation(
        buyer,
        seller,
        buyer_principal,
        seller_principal,
        _DEFAULT_SCENARIO,
        max_rounds=max_rounds,
        sink=sink,
        thread_id=f"session-{session_id}",
    )

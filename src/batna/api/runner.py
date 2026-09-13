"""Session lifecycle for the streaming API.

Builds a Phase 6 two-agent negotiation whose agents share a single
``RedisStreamSink`` (so all tool-call + offer + acceptance events stream over
the same per-session Redis channel in a globally monotonic order), then runs it
in a background task so a browser can watch it live over WebSocket.

The default demo runs in ``live`` mode, driving the loop with a **real** Ollama
model (``agent_model``, e.g. ``qwen2.5:7b``) so the dashboard streams genuine
model reasoning and tool decisions.  If Ollama is unreachable the runner falls
back to ``scripted`` (hermetic, deterministic, no live model required) and
labels the session honestly.  Set ``BATNA_LLM_MODE=scripted`` to force the
deterministic path.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.eval import _scenario_principals, default_server_env
from batna.agents.graph import run_negotiation
from batna.agents.llm import LLMClient, OllamaLLMClient, ScriptedNegotiatorLLM
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.config import settings
from batna.mcp_servers.registry_client import ToolRegistryClient
from batna.stream.publisher import RedisStreamSink

logger = logging.getLogger(__name__)

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
    until_agreement: bool = False  # run to agreement (hard cap) instead of max_rounds
    status: str = "created"  # created | running | done | error
    result: dict[str, Any] = field(default_factory=dict)
    run_mode: str | None = None  # "scripted" | "live" — which LLM actually drove it
    run_model: str | None = None  # model id (e.g. "qwen2.5:7b") or scripted-det label
    error: str | None = None
    task: Any = None


def _new_registry(server: str) -> ToolRegistryClient:
    args = _MCP_SERVERS[server]
    return ToolRegistryClient(
        command=sys.executable,
        args=list(args),
        env=default_server_env(),
    )


async def _live_llm_available(model: str) -> bool:
    """True if a live Ollama server is reachable and hosts ``model``."""
    import httpx as _httpx

    try:
        async with _httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            names = {m.get("name") for m in resp.json().get("models", [])}
            return model in names
    except Exception as exc:
        logger.warning(
            "Ollama unavailable at %s (%s); using scripted mode",
            settings.ollama_base_url,
            exc,
        )
        return False


async def _resolve_llms(mode: str | None = None) -> tuple[str, str | None, LLMClient, LLMClient]:
    """Choose live (Ollama) or scripted negotiators.

    Returns ``(run_mode, run_model, buyer_llm, seller_llm)``. ``mode`` defaults
    to ``settings.llm_mode`` but may be pinned explicitly (e.g. tests force
    ``"scripted"`` for hermeticity). Live mode uses a real Ollama model on both
    sides; if it is unavailable we fall back to the hermetic scripted client so
    a demo always completes (and is labelled honestly).
    """
    mode = mode or settings.llm_mode
    model = settings.agent_model
    if mode == "live" and await _live_llm_available(model):
        logger.info("Live mode: driving negotiation with Ollama model %s", model)
        llm = OllamaLLMClient(model=model)
        return "live", model, llm, llm
    return (
        "scripted",
        "scripted-deterministic",
        ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
    )


async def run_streaming_negotiation(
    session_id: str,
    sink: RedisStreamSink,
    *,
    kind: str = "wide",
    server: str = "market_data",
    max_rounds: int = 12,
    until_agreement: bool = False,
    llm_mode: str | None = None,
) -> dict[str, Any]:
    """Run a full negotiation through the shared sink and return final state.

    Creates a fresh real MCP registry per side (each call opens its own stdio
    session), so buyer and seller never contend over one subprocess.
    ``max_rounds`` bounds the multi-round exchange (commonly 12; the scripted
    negotiators concede in ~10% steps, so a deal closes after several turns).
    When ``until_agreement`` is True the loop ignores ``max_rounds`` and runs
    until agreement or the hard cap in settings (see ``run_negotiation``).
    ``llm_mode`` overrides ``settings.llm_mode`` (live default) — tests pin
    ``"scripted"`` to stay hermetic.
    """
    buyer_principal, seller_principal = _scenario_principals(kind)

    run_mode, run_model, buyer_llm, seller_llm = await _resolve_llms(llm_mode)

    buyer = BuyerAgent(
        llm=buyer_llm,
        provider=ToolProvider(_new_registry(server), sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=seller_llm,
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
        until_agreement=until_agreement,
        sink=sink,
        thread_id=f"session-{session_id}",
        run_mode=run_mode,
        run_model=run_model,
    )

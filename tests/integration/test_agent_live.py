"""Supplementary Phase 5 integration tests hitting the live data path and Ollama.

These validate the real tool-calling plumbing that the deterministic DoD suite
exercises: the market-data MCP server over stdio returns a live BLS PPI, and the
Ollama native-tool client can connect and make decisions. They are lenient - they
skip (rather than fail) when the live model or external API is unavailable.
"""

from __future__ import annotations

import json
import sys

import httpx
import pytest
from mcp.types import Tool

from batna.agents.eval import default_server_env
from batna.agents.llm import Action, OllamaLLMClient
from batna.agents.tool_provider import ToolProvider
from batna.config import settings
from batna.mcp_servers.registry_client import ToolRegistryClient


@pytest.mark.integration
async def test_market_data_tool_live_ppp() -> None:
    """The real market-data MCP server returns a live BLS PPI over stdio."""
    registry = ToolRegistryClient(
        command=sys.executable,
        args=["-m", "batna.mcp_servers.market_data_server"],
        env=default_server_env(),
    )
    provider = ToolProvider(registry)
    tools: list[Tool] = await provider.discover()
    assert any(tool.name == "get_market_benchmark" for tool in tools)

    try:
        response = await provider.call("get_market_benchmark", {"industry": "cloud_hosting"})
    except Exception as exc:
        pytest.skip(f"Live BLS benchmark unavailable (likely rate limit / network): {exc}")

    payload = json.loads(response)
    assert float(payload["latest_value"]) > 0.0
    assert payload["source"] == "BLS"
    # A real tool was called and its invocation is recorded for provenance.
    assert len(provider.log) == 1


@pytest.mark.integration
async def test_ollama_client_connects_and_decides() -> None:
    """The Ollama native-tool client can reach the server and return an Action."""
    endpoint = f"{settings.ollama_base_url}/api/version"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(endpoint)
            resp.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url}: {exc}")

    client_llm = OllamaLLMClient(model=settings.agent_model)
    action = await client_llm.decide(
        messages=[{"role": "user", "content": "Say hello and stop."}],
        tools=[],
    )
    assert isinstance(action, Action)
    # A real turn returned either a text decision or a tool-call request.
    assert action.final_text is not None or action.tool_calls is not None

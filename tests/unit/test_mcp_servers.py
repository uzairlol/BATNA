"""Unit tests for Phase 3 MCP servers (market_data_server and precedent_server)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from batna.data.fred_bls import BenchmarkObservation, MarketBenchmarkResult
from batna.data.usaspending import ProcurementAward
from batna.mcp_servers.market_data_server import get_market_benchmark, market_data_server
from batna.mcp_servers.precedent_server import (
    PrecedentServerState,
    precedent_server,
    search_precedent,
)


@pytest.mark.asyncio
async def test_market_data_server_tool_registration() -> None:
    """Verify market_data_server exposes get_market_benchmark with correct schema."""
    tools = await market_data_server.list_tools()
    tool_names = [t.name for t in tools]
    assert "get_market_benchmark" in tool_names

    tool = next(t for t in tools if t.name == "get_market_benchmark")
    schema = getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))
    assert "industry" in schema.get("properties", {})


@pytest.mark.asyncio
async def test_get_market_benchmark_execution() -> None:
    """Verify get_market_benchmark tool executes and formats Pydantic result as JSON string."""
    mock_benchmark = MarketBenchmarkResult(
        series_id="WPUFD4",
        title="BLS PPI Final Demand",
        source="BLS",
        latest_period="2024 December",
        latest_value=146.189,
        annual_pct_change=2.82,
        observations=[BenchmarkObservation(date="2024 December", value=146.189)],
    )

    with patch(
        "batna.data.fred_bls.EconomicDataClient.get_industry_benchmark",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = mock_benchmark
        raw_output = await get_market_benchmark(industry="general_services")
        data = json.loads(raw_output)

        assert data["series_id"] == "WPUFD4"
        assert data["latest_value"] == 146.189
        assert data["source"] == "BLS"


@pytest.mark.asyncio
async def test_precedent_server_tool_registration() -> None:
    """Verify precedent_server exposes search_precedent with correct schema."""
    tools = await precedent_server.list_tools()
    tool_names = [t.name for t in tools]
    assert "search_precedent" in tool_names

    tool = next(t for t in tools if t.name == "search_precedent")
    schema = getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))
    props = schema.get("properties", {})
    assert "term" in props
    assert "top_k" in props


@pytest.mark.asyncio
async def test_search_precedent_execution(tmp_path: Path) -> None:
    """Verify search_precedent retrieves real precedent records and outputs valid JSON."""
    test_awards = [
        ProcurementAward(
            award_id="AWD_TEST_1",
            recipient_name="Acme Systems",
            awarding_agency="Department of Commerce",
            award_amount=500000.0,
            description="Cloud infrastructure modernization and migration",
            naics_code="518210",
        )
    ]
    cache_file = tmp_path / "awards.json"
    cache_file.write_text(json.dumps([a.model_dump() for a in test_awards]), encoding="utf-8")

    test_state = PrecedentServerState(corpus_path=cache_file)
    with patch("batna.mcp_servers.precedent_server._state", test_state):
        raw_output = await search_precedent(term="cloud infrastructure", top_k=1)
        data = json.loads(raw_output)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["award_id"] == "AWD_TEST_1"
        assert data[0]["vendor"] == "Acme Systems"
        assert data[0]["amount"] == 500000.0

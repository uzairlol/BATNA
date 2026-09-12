"""MCP server exposing real FRED/BLS economic benchmarks as an external capability."""

from __future__ import annotations

import json
import logging

from mcp.server.mcpserver import MCPServer

from batna.data.fred_bls import EconomicDataClient

logger = logging.getLogger(__name__)


# Real data, no hand-authored numbers: benchmarks are pulled live from the BLS
# Producer Price Index (PPI) public API (v1, no key required) for the industry's
# PPI series. FRED is used as the alternative source when BLS is unavailable.
# Region is informational (FRED/BLS publish US-national series) and does not
# change the underlying data; the schema includes it to match the tool contract
# in the BATNA spec while staying honest about what it does.
market_data_server = MCPServer(
    name="market-data",
    title="Market Data Server",
    description=(
        "Serves real, current Producer Price Index (PPI) / FRED economic benchmarks "
        "for B2B contract negotiation categories."
    ),
    version="0.1.0",
)


@market_data_server.tool()
async def get_market_benchmark(
    industry: str,
    start_year: int = 2023,
    end_year: int = 2024,
    region: str = "US",
) -> str:
    """Get a real market benchmark (PPI index value and annual change) for an industry.

    Args:
        industry: Industry category key, e.g. 'software_development', 'systems_design',
            'cloud_hosting', or 'general_services'. An unrecognized value is treated
            as a raw BLS series ID.
        start_year: First year of the observation window.
        end_year: Last year of the observation window.
        region: Informational only — FRED/BLS publish US-national series.

    Returns:
        JSON string of the benchmark result including the latest index value,
        latest period, and year-over-year percentage change.
    """
    client = EconomicDataClient()
    benchmark = await client.get_industry_benchmark(
        industry=industry,
        start_year=start_year,
        end_year=end_year,
    )
    return json.dumps(benchmark.model_dump(), indent=2)


if __name__ == "__main__":
    market_data_server.run()
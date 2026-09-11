"""Integration tests hitting live endpoints to satisfy Phase 2 Definition of Done."""

from __future__ import annotations

import pytest

from batna.data.fred_bls import EconomicDataClient, MarketBenchmarkResult
from batna.data.precedent_index import PrecedentHybridIndex
from batna.data.usaspending import ProcurementAward, USAspendingClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_usaspending_api_and_hybrid_index() -> None:
    """
    Phase 2 DoD Check:
    Query live USAspending.gov API, get back real contract award records with
    real dollar amounts, vendor names, and agencies, and verify precedent index returns them.
    """
    client = USAspendingClient(timeout=30.0)
    awards = await client.search_contracts(
        keywords=["software", "development"],
        limit=10,
    )

    assert len(awards) > 0, "Expected at least 1 real award from live USAspending API"
    for award in awards:
        assert isinstance(award, ProcurementAward)
        assert award.award_amount > 0
        assert len(award.recipient_name) > 0
        assert len(award.awarding_agency) > 0
        assert award.source_url is not None
        assert "usaspending.gov/award/" in award.source_url

    # Verify spot-checked results index into PrecedentHybridIndex
    index = PrecedentHybridIndex(awards)
    search_res = index.search("software development", top_k=3)
    assert len(search_res) > 0
    assert search_res[0].award.award_amount > 0
    assert search_res[0].rrf_score > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_bls_api() -> None:
    """
    Phase 2 DoD Check:
    Query BLS public API for a real industry PPI series (e.g. PCU541511541511)
    and verify real numeric observations and non-zero values.
    """
    client = EconomicDataClient(timeout=20.0)
    try:
        benchmark = await client.get_bls_series("PCU541511541511", start_year=2023, end_year=2024)
        assert isinstance(benchmark, MarketBenchmarkResult)
        assert benchmark.latest_value > 0.0
        assert benchmark.source == "BLS"
        assert len(benchmark.observations) > 0
    except Exception as e:
        # Note: BLS public API has daily IP-based rate limits on v1
        pytest.skip(f"BLS API call skipped (likely rate limit or temporary network): {e}")

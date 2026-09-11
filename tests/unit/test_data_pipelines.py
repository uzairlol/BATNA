"""Unit tests for Phase 2 data pipelines (FRED/BLS client, USAspending, PrecedentIndex)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from batna.data.fred_bls import EconomicDataClient, MarketBenchmarkResult
from batna.data.precedent_index import PrecedentHybridIndex, SimpleBM25
from batna.data.usaspending import ProcurementAward, USAspendingClient


def test_simple_bm25_scoring() -> None:
    corpus = [
        ["cloud", "hosting", "aws", "infrastructure"],
        ["software", "custom", "python", "backend"],
        ["hardware", "cisco", "switch", "networking"],
    ]
    bm25 = SimpleBM25(corpus)
    scores = bm25.get_scores(["cloud", "hosting"])
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_precedent_hybrid_index_rrf() -> None:
    awards = [
        ProcurementAward(
            award_id="CONT_1",
            recipient_name="Palantir Technologies Inc",
            awarding_agency="Department of Defense",
            award_amount=2500000.0,
            description="Enterprise AI platform and data integration services",
            naics_code="541512",
        ),
        ProcurementAward(
            award_id="CONT_2",
            recipient_name="Booz Allen Hamilton",
            awarding_agency="Department of Veterans Affairs",
            award_amount=450000.0,
            description="Custom software engineering and agile development",
            naics_code="541511",
        ),
        ProcurementAward(
            award_id="CONT_3",
            recipient_name="Amazon Web Services Inc",
            awarding_agency="Department of Justice",
            award_amount=1200000.0,
            description="Secure cloud hosting and infrastructure compute",
            naics_code="518210",
        ),
    ]

    index = PrecedentHybridIndex(awards, rrf_k=60)
    results = index.search("agile software engineering", top_k=2)

    assert len(results) == 2
    assert results[0].award.award_id == "CONT_2"
    assert results[0].rrf_score > 0.0

    # Test budget constraint filter
    budget_results = index.search("software cloud", min_amount=1000000.0)
    assert all(r.award.award_amount >= 1000000.0 for r in budget_results)

    # Test MCP response formatting
    mcp_out = index.to_mcp_format(results)
    assert len(mcp_out) == 2
    assert "amount" in mcp_out[0]
    assert "vendor" in mcp_out[0]


@pytest.mark.asyncio
async def test_economic_client_bls_parsing() -> None:
    mock_response_data = {
        "status": "REQUEST_SUCCEEDED",
        "responseTime": 210,
        "message": [],
        "Results": {
            "series": [
                {
                    "seriesID": "PCU541511541511",
                    "data": [
                        {"year": "2024", "period": "M05", "periodName": "May", "value": "118.5"},
                        {"year": "2024", "period": "M04", "periodName": "April", "value": "118.0"},
                        {"year": "2024", "period": "M03", "periodName": "March", "value": "117.8"},
                        {
                            "year": "2024",
                            "period": "M02",
                            "periodName": "February",
                            "value": "117.5",
                        },
                        {
                            "year": "2024",
                            "period": "M01",
                            "periodName": "January",
                            "value": "117.2",
                        },
                        {
                            "year": "2023",
                            "period": "M12",
                            "periodName": "December",
                            "value": "116.9",
                        },
                        {
                            "year": "2023",
                            "period": "M11",
                            "periodName": "November",
                            "value": "116.5",
                        },
                        {
                            "year": "2023",
                            "period": "M10",
                            "periodName": "October",
                            "value": "116.0",
                        },
                        {
                            "year": "2023",
                            "period": "M09",
                            "periodName": "September",
                            "value": "115.8",
                        },
                        {"year": "2023", "period": "M08", "periodName": "August", "value": "115.5"},
                        {"year": "2023", "period": "M07", "periodName": "July", "value": "115.2"},
                        {"year": "2023", "period": "M06", "periodName": "June", "value": "115.0"},
                    ],
                }
            ]
        },
    }

    client = EconomicDataClient()

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.json = lambda: mock_response_data
        mock_post.return_value = mock_resp

        benchmark = await client.get_bls_series("PCU541511541511")
        assert isinstance(benchmark, MarketBenchmarkResult)
        assert benchmark.latest_value == 118.5
        assert benchmark.latest_period == "2024 May"
        assert benchmark.annual_pct_change is not None
        assert benchmark.annual_pct_change > 0.0


@pytest.mark.asyncio
async def test_usaspending_client_search_parsing(tmp_path: Path) -> None:
    mock_payload = {
        "results": [
            {
                "Award ID": "123456789",
                "Recipient Name": "Acme GovTech Solutions",
                "Awarding Agency": "General Services Administration",
                "Award Amount": 750000.0,
                "Description": "Cloud modernization and DevSecOps migration",
                "Start Date": "2023-01-15",
                "End Date": "2025-01-14",
                "NAICS Code": "541512",
                "internal_id": "987654",
            }
        ]
    }

    client = USAspendingClient()

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.json = lambda: mock_payload
        mock_post.return_value = mock_resp

        results = await client.search_contracts(keywords=["cloud"])
        assert len(results) == 1
        assert results[0].award_amount == 750000.0
        assert results[0].recipient_name == "Acme GovTech Solutions"
        assert results[0].source_url == "https://www.usaspending.gov/award/987654"

    # Test cache serialization and deserialization
    cache_file = tmp_path / "procurement_cache.json"
    cache_file.write_text(json.dumps([results[0].model_dump()]), encoding="utf-8")
    loaded = USAspendingClient.load_corpus_cache(cache_file)
    assert len(loaded) == 1
    assert loaded[0].award_id == "123456789"

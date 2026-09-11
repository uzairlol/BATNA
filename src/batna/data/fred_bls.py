"""Economic data client for FRED and BLS Producer Price Index (PPI) benchmarks."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from batna.config import settings

logger = logging.getLogger(__name__)


class BenchmarkObservation(BaseModel):
    """Single observation point for an economic index series."""

    date: str = Field(..., description="Date or period of observation (e.g. '2024-01-01' or '2024M01')")
    value: float = Field(..., description="Value of index / series at this observation")


class MarketBenchmarkResult(BaseModel):
    """Benchmark result retrieved from live FRED or BLS API."""

    series_id: str = Field(..., description="Unique series identifier (e.g. PCU541511541511)")
    title: str = Field(..., description="Series title or economic indicator description")
    source: str = Field(..., description="Source agency ('FRED' or 'BLS')")
    latest_period: str = Field(..., description="Latest observation period")
    latest_value: float = Field(..., description="Latest index / price level")
    annual_pct_change: float | None = Field(
        None, description="Year-over-year percentage change in index"
    )
    observations: list[BenchmarkObservation] = Field(
        default_factory=list, description="Historical observations window"
    )


class EconomicDataClient:
    """Client for retrieving macroeconomic and PPI industry cost indices from FRED and BLS."""

    BLS_API_URL: str = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    BLS_V1_API_URL: str = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
    FRED_API_URL: str = "https://api.stlouisfed.org/fred/series/observations"

    # Default industry series mappings for B2B contract negotiation benchmarks
    # PCU541511541511: Custom Computer Programming Services
    # PCU541512541512: Computer Systems Design Services
    # PCU518210518210: Data Processing, Hosting, and Related Services
    # WPUFD4: Final Demand PPI
    INDUSTRY_SERIES_MAP: dict[str, str] = {
        "software_development": "PCU541511541511",
        "systems_design": "PCU541512541512",
        "cloud_hosting": "PCU518210518210",
        "general_services": "WPUFD4",
    }

    def __init__(
        self,
        fred_api_key: str | None = None,
        bls_api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.fred_api_key = fred_api_key or settings.fred_api_key
        self.bls_api_key = bls_api_key or settings.bls_api_key
        self.timeout = timeout

    async def get_bls_series(
        self,
        series_id: str,
        start_year: int = 2023,
        end_year: int = 2024,
    ) -> MarketBenchmarkResult:
        """Fetch Producer Price Index (PPI) or CPI series from BLS API."""
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        url = self.BLS_API_URL
        if self.bls_api_key:
            payload["registrationkey"] = self.bls_api_key
        else:
            url = self.BLS_V1_API_URL

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "REQUEST_SUCCEEDED":
            messages = data.get("message", [])
            raise RuntimeError(f"BLS API error for {series_id}: {messages}")

        series_data = data.get("Results", {}).get("series", [])
        if not series_data:
            raise ValueError(f"No series data found for series ID: {series_id}")

        items = series_data[0].get("data", [])
        if not items:
            raise ValueError(f"Empty observations list for series ID: {series_id}")

        # BLS returns newest first
        valid_obs: list[BenchmarkObservation] = []
        for item in items:
            try:
                val = float(item["value"])
                period_name = f"{item.get('year')} {item.get('periodName', item.get('period'))}"
                valid_obs.append(BenchmarkObservation(date=period_name, value=val))
            except (ValueError, KeyError):
                continue

        if not valid_obs:
            raise ValueError(f"No valid numeric observations returned for {series_id}")

        latest = valid_obs[0]
        # Calculate annual change if we have 12+ months or older observation
        annual_pct_change: float | None = None
        if len(valid_obs) >= 12:
            prior = valid_obs[11].value
            if prior > 0:
                annual_pct_change = round(((latest.value - prior) / prior) * 100.0, 2)

        return MarketBenchmarkResult(
            series_id=series_id,
            title=f"BLS PPI/CPI Series {series_id}",
            source="BLS",
            latest_period=latest.date,
            latest_value=latest.value,
            annual_pct_change=annual_pct_change,
            observations=valid_obs,
        )

    async def get_fred_series(
        self,
        series_id: str,
        limit: int = 12,
    ) -> MarketBenchmarkResult:
        """Fetch economic indicator series from FRED API."""
        if not self.fred_api_key:
            raise ValueError("FRED API key is required to query FRED. Provide FRED_API_KEY in settings or env.")

        params: dict[str, str | int] = {
            "series_id": series_id,
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.FRED_API_URL, params=params)

            response.raise_for_status()
            data = response.json()

        observations_raw = data.get("observations", [])
        valid_obs: list[BenchmarkObservation] = []
        for obs in observations_raw:
            try:
                val = float(obs["value"])
                valid_obs.append(BenchmarkObservation(date=obs["date"], value=val))
            except (ValueError, KeyError):
                continue

        if not valid_obs:
            raise ValueError(f"No valid numeric observations returned by FRED for {series_id}")

        latest = valid_obs[0]
        annual_pct_change: float | None = None
        if len(valid_obs) >= 12:
            prior = valid_obs[11].value
            if prior > 0:
                annual_pct_change = round(((latest.value - prior) / prior) * 100.0, 2)

        return MarketBenchmarkResult(
            series_id=series_id,
            title=f"FRED Economic Series {series_id}",
            source="FRED",
            latest_period=latest.date,
            latest_value=latest.value,
            annual_pct_change=annual_pct_change,
            observations=valid_obs,
        )

    async def get_industry_benchmark(
        self,
        industry: str,
        start_year: int = 2023,
        end_year: int = 2024,
    ) -> MarketBenchmarkResult:
        """Resolve industry key to PPI series and fetch market benchmark."""
        series_id = self.INDUSTRY_SERIES_MAP.get(industry, industry)
        return await self.get_bls_series(series_id, start_year=start_year, end_year=end_year)

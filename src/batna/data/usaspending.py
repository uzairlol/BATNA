"""USAspending.gov procurement award data client for real B2B precedent grounding."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProcurementAward(BaseModel):
    """Normalized federal procurement award record from USAspending.gov."""

    award_id: str = Field(..., description="Unique generated award ID or contract key")
    internal_id: str | None = Field(None, description="USAspending internal award ID")
    recipient_name: str = Field(..., description="Contract awardee / vendor name")
    awarding_agency: str = Field(..., description="Contracting agency name")
    awarding_subagency: str | None = Field(None, description="Sub-tier contracting office/agency")
    award_amount: float = Field(..., description="Obligated contract award amount in USD")
    description: str = Field(..., description="Description of procurement or work requirement")
    start_date: str | None = Field(None, description="Period of performance start date")
    end_date: str | None = Field(None, description="Period of performance end date")
    contract_type: str | None = Field(None, description="Contract pricing type (e.g. FFP, T&M)")
    naics_code: str | None = Field(None, description="North American Industry Classification code")
    source_url: str | None = Field(None, description="USAspending web verification URL")


class USAspendingClient:
    """Client for pulling real contract awards from USAspending.gov API."""

    BASE_URL: str = "https://api.usaspending.gov"
    SPENDING_BY_AWARD_URL: str = f"{BASE_URL}/api/v2/search/spending_by_award/"

    # Standard IT & Professional Services NAICS codes
    DEFAULT_NAICS_CODES: list[str] = [
        "541511",  # Custom Computer Programming Services
        "541512",  # Computer Systems Design Services
        "541519",  # Other Computer Related Services
        "518210",  # Data Processing, Hosting, and Related Services
    ]

    def __init__(self, timeout: float = 25.0) -> None:
        self.timeout = timeout

    async def search_contracts(
        self,
        keywords: list[str] | None = None,
        naics_codes: list[str] | None = None,
        min_amount: float | None = 25000.0,
        max_amount: float | None = 10000000.0,
        limit: int = 50,
        page: int = 1,
    ) -> list[ProcurementAward]:
        """Query USAspending API for contract awards matching domain filters."""
        filters: dict[str, Any] = {
            "award_type_codes": ["A", "B", "C", "D"],  # Contracts & definitive contracts
            "time_period": [{"start_date": "2022-01-01", "end_date": "2024-12-31"}],
        }

        if keywords:
            filters["keywords"] = keywords

        active_naics = naics_codes or self.DEFAULT_NAICS_CODES
        filters["naics_codes"] = {"require": active_naics}

        if min_amount is not None or max_amount is not None:
            award_amounts: dict[str, float] = {}
            if min_amount is not None:
                award_amounts["lower_bound"] = min_amount
            if max_amount is not None:
                award_amounts["upper_bound"] = max_amount
            filters["award_amounts"] = [award_amounts]

        fields = [
            "Award ID",
            "Recipient Name",
            "Awarding Agency",
            "Award Amount",
            "Description",
            "Start Date",
            "End Date",
        ]

        payload: dict[str, Any] = {
            "filters": filters,
            "fields": fields,
            "page": page,
            "limit": limit,
            "sort": "Award Amount",
            "order": "desc",
        }

        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.SPENDING_BY_AWARD_URL, json=payload, headers=headers
            )

            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        awards: list[ProcurementAward] = []

        for item in results:
            award_amount = float(item.get("Award Amount") or 0.0)
            if award_amount <= 0:
                continue

            award_id = str(item.get("Award ID") or item.get("generated_internal_id") or "UNKNOWN")
            internal_id = str(item.get("internal_id") or "")
            recipient = str(item.get("Recipient Name") or "Unknown Vendor")
            agency = str(item.get("Awarding Agency") or "Unknown Agency")
            subagency = item.get("Awarding Sub Agency")
            description = str(item.get("Description") or "").strip()
            if not description:
                description = f"Contract for {recipient} with {agency}"

            start_date = item.get("Start Date")
            end_date = item.get("End Date")
            contract_type = item.get("Contract Award Type")
            naics_code = str(item.get("NAICS Code") or "")

            source_url = None
            if internal_id:
                source_url = f"https://www.usaspending.gov/award/{internal_id}"

            awards.append(
                ProcurementAward(
                    award_id=award_id,
                    internal_id=internal_id or None,
                    recipient_name=recipient,
                    awarding_agency=agency,
                    awarding_subagency=subagency,
                    award_amount=award_amount,
                    description=description,
                    start_date=start_date,
                    end_date=end_date,
                    contract_type=contract_type,
                    naics_code=naics_code or None,
                    source_url=source_url,
                )
            )

        return awards

    async def build_corpus_cache(
        self,
        target_file: Path,
        limit_per_category: int = 40,
    ) -> list[ProcurementAward]:
        """Fetch representative procurement deals across key B2B categories and save locally."""
        categories: list[list[str]] = [
            ["software", "development"],
            ["cloud", "hosting", "infrastructure"],
            ["data", "analytics"],
            ["systems", "engineering", "support"],
        ]

        all_awards: dict[str, ProcurementAward] = {}

        for kw in categories:
            try:
                batch = await self.search_contracts(keywords=kw, limit=limit_per_category)
                for award in batch:
                    all_awards[award.award_id] = award
            except Exception as e:
                logger.warning(f"Error fetching batch for {kw}: {e}")

        # If nothing fetched (e.g. rate limit / network issue), do not overwrite with empty
        if not all_awards:
            if target_file.exists():
                logger.info("Loading existing corpus cache.")
                return self.load_corpus_cache(target_file)
            raise RuntimeError("Failed to fetch procurement awards and no cache exists.")

        target_file.parent.mkdir(parents=True, exist_ok=True)
        records = [award.model_dump() for award in all_awards.values()]
        target_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        logger.info(f"Saved {len(records)} procurement awards to {target_file}")

        return list(all_awards.values())

    @staticmethod
    def load_corpus_cache(target_file: Path) -> list[ProcurementAward]:
        """Load cached procurement awards from JSON file."""
        if not target_file.exists():
            raise FileNotFoundError(f"Corpus file not found: {target_file}")
        raw_data = json.loads(target_file.read_text(encoding="utf-8"))
        return [ProcurementAward.model_validate(item) for item in raw_data]

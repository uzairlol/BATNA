"""Contract schema for BATNA negotiation engine."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator


class ContractTerms(BaseModel):
    """Terms of a bilateral contract negotiation."""

    price: float = Field(..., gt=0, description="Contract price in currency units")
    payment_terms_days: int = Field(
        ..., ge=0, le=365, description="Days to pay after delivery"
    )
    delivery_sla_days: int = Field(
        ..., ge=0, le=365, description="Delivery service level agreement in days"
    )
    liability_cap_pct: float = Field(
        ..., ge=0, le=100, description="Liability cap as percentage of contract value"
    )
    contract_duration_months: int = Field(
        ..., ge=1, le=120, description="Contract duration in months"
    )
    termination_notice_days: int = Field(
        ..., ge=0, le=365, description="Notice period for termination in days"
    )

    @field_validator('liability_cap_pct')
    @classmethod
    def liability_cap_must_be_reasonable(cls, v: float) -> float:
        """Ensure liability cap is reasonable (not 0% unless explicitly allowed)."""
        if v < 0:
            raise ValueError('Liability cap cannot be negative')
        return v

    class Config:
        """Pydantic configuration."""

        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "price": 100000.0,
                "payment_terms_days": 30,
                "delivery_sla_days": 14,
                "liability_cap_pct": 20.0,
                "contract_duration_months": 24,
                "termination_notice_days": 60,
            }
        }

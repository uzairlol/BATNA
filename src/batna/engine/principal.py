"""Principal schema for BATNA negotiation engine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Principal(BaseModel):
    """Principal (party) in a bilateral negotiation."""

    reservation_value: float = Field(
        ..., gt=0, description="Worst acceptable value (reservation point)"
    )
    target_value: float = Field(..., gt=0, description="Desired value (target point)")
    authorized_mandate: dict[str, tuple[float, float]] = Field(
        ...,
        description="Authorized ranges for each contract term (term -> [min, max])",
    )
    round_budget: int = Field(..., ge=1, description="Maximum number of negotiation rounds allowed")

    @field_validator("authorized_mandate")
    @classmethod
    def mandate_must_be_valid_tuples(
        cls, v: dict[str, tuple[float, float]]
    ) -> dict[str, tuple[float, float]]:
        """Ensure each mandate is a tuple of two numbers with min <= max."""
        for term, bounds in v.items():
            if not isinstance(bounds, tuple) or len(bounds) != 2:
                raise ValueError(f"Mandate for {term} must be a tuple of two numbers, got {bounds}")
            if not all(isinstance(x, (int, float)) for x in bounds):
                raise ValueError(f"Mandate for {term} must contain numeric values, got {bounds}")
            if bounds[0] > bounds[1]:
                raise ValueError(f"Mandate min must be <= max for {term}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reservation_value": 100.0,
                "target_value": 80.0,
                "authorized_mandate": {
                    "price": [70000, 130000],
                    "payment_terms_days": [15, 60],
                    "delivery_sla_days": [7, 30],
                    "liability_cap_pct": [10, 30],
                    "contract_duration_months": [12, 36],
                    "termination_notice_days": [30, 90],
                },
                "round_budget": 10,
            }
        }
    )

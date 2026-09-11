"""Unit tests for the BATNA negotiation engine."""

from __future__ import annotations

from batna.engine.principal import Principal
from batna.engine.scoring import calculate_nash_price, calculate_zopa


def test_calculate_zopa_overlapping() -> None:
    """Test ZOPA calculation when there is an overlap."""
    buyer = Principal(
        reservation_value=100.0,  # Not used in ZOPA calculation for price term
        target_value=80.0,
        authorized_mandate={
            "price": (0, 100),  # Buyer accepts up to 100
            "payment_terms_days": (0, 30),
            "delivery_sla_days": (0, 14),
            "liability_cap_pct": (0, 50),
            "contract_duration_months": (0, 24),
            "termination_notice_days": (0, 60),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90.0,  # Not used
        target_value=110.0,
        authorized_mandate={
            "price": (90, 200),  # Seller accepts from 90 upwards
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )

    zopa = calculate_zopa(buyer, seller, "price")
    assert zopa is not None
    low, high = zopa
    assert low == 90.0
    assert high == 100.0


def test_calculate_zopa_no_overlap() -> None:
    """Test ZOPA calculation when there is no overlap."""
    buyer = Principal(
        reservation_value=80.0,
        target_value=70.0,
        authorized_mandate={
            "price": (0, 80),  # Buyer accepts up to 80
            "payment_terms_days": (0, 30),
            "delivery_sla_days": (0, 14),
            "liability_cap_pct": (0, 50),
            "contract_duration_months": (0, 24),
            "termination_notice_days": (0, 60),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90.0,
        target_value=100.0,
        authorized_mandate={
            "price": (90, 200),  # Seller accepts from 90 upwards
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )

    zopa = calculate_zopa(buyer, seller, "price")
    assert zopa is None


def test_calculate_nash_price() -> None:
    """Test Nash price calculation."""
    buyer = Principal(
        reservation_value=100.0,
        target_value=80.0,
        authorized_mandate={
            "price": (0, 100),
            "payment_terms_days": (0, 30),
            "delivery_sla_days": (0, 14),
            "liability_cap_pct": (0, 50),
            "contract_duration_months": (0, 24),
            "termination_notice_days": (0, 60),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90.0,
        target_value=110.0,
        authorized_mandate={
            "price": (90, 200),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )

    nash_price = calculate_nash_price(buyer, seller, "price")
    assert nash_price is not None
    # Expected: (100 + 90) / 2 = 95.0
    assert nash_price == 95.0


def test_calculate_nash_price_no_zopa() -> None:
    """Test Nash price returns None when no ZOPA."""
    buyer = Principal(
        reservation_value=80.0,
        target_value=70.0,
        authorized_mandate={
            "price": (0, 80),
            "payment_terms_days": (0, 30),
            "delivery_sla_days": (0, 14),
            "liability_cap_pct": (0, 50),
            "contract_duration_months": (0, 24),
            "termination_notice_days": (0, 60),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90.0,
        target_value=100.0,
        authorized_mandate={
            "price": (90, 200),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )

    nash_price = calculate_nash_price(buyer, seller, "price")
    assert nash_price is None

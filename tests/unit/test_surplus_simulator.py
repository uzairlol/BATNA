"""Unit tests for the Phase 4 in-process surplus simulator."""

from __future__ import annotations

import pytest

from batna.engine.principal import Principal
from batna.tools.surplus_simulator import (
    simulate_surplus,
    surplus_fractions_for_price,
)


def _buyer(price_max: float = 100.0) -> Principal:
    return Principal(
        reservation_value=100.0,
        target_value=80.0,
        authorized_mandate={
            "price": (0, price_max),
            "payment_terms_days": (0, 30),
            "delivery_sla_days": (0, 14),
            "liability_cap_pct": (0, 50),
            "contract_duration_months": (0, 24),
            "termination_notice_days": (0, 60),
        },
        round_budget=10,
    )


def _seller(price_min: float = 90.0) -> Principal:
    return Principal(
        reservation_value=90.0,
        target_value=110.0,
        authorized_mandate={
            "price": (price_min, 200),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )


def test_simulate_surplus_hand_computed() -> None:
    """Nash solution splits total cooperative surplus 50/50 for linear utilities."""
    buyer = _buyer(price_max=100.0)
    seller = _seller(price_min=90.0)

    sim = simulate_surplus(buyer, seller, "price")
    assert sim is not None

    assert sim.zopa == (90.0, 100.0)
    assert sim.nash_price == pytest.approx(95.0)
    assert sim.total_surplus == pytest.approx(10.0)
    assert sim.buyer_reservation == 100.0
    assert sim.seller_reservation == 90.0
    assert sim.nash_share.buyer_fraction == pytest.approx(0.5)
    assert sim.nash_share.seller_fraction == pytest.approx(0.5)


def test_surplus_fractions_at_reservation_endpoints() -> None:
    """Surplus share is 100/0 at each party's reservation price."""
    buyer = _buyer(price_max=100.0)
    seller = _seller(price_min=90.0)

    at_seller_reservation = surplus_fractions_for_price(buyer, seller, 90.0)
    assert at_seller_reservation is not None
    assert at_seller_reservation.buyer_fraction == pytest.approx(1.0)
    assert at_seller_reservation.seller_fraction == pytest.approx(0.0)

    at_buyer_reservation = surplus_fractions_for_price(buyer, seller, 100.0)
    assert at_buyer_reservation is not None
    assert at_buyer_reservation.buyer_fraction == pytest.approx(0.0)
    assert at_buyer_reservation.seller_fraction == pytest.approx(1.0)


def test_surplus_fractions_midpoint() -> None:
    """At the midpoint the split is 50/50 and the pair sums to 1."""
    buyer = _buyer(price_max=100.0)
    seller = _seller(price_min=90.0)
    share = surplus_fractions_for_price(buyer, seller, 95.0)
    assert share is not None
    assert share.buyer_fraction == pytest.approx(0.5)
    assert share.seller_fraction == pytest.approx(0.5)
    assert share.buyer_fraction + share.seller_fraction == pytest.approx(1.0)


def test_no_zopa_returns_none() -> None:
    """When mandates do not overlap, both finite results are None."""
    buyer = _buyer(price_max=80.0)
    seller = _seller(price_min=90.0)

    assert simulate_surplus(buyer, seller, "price") is None
    assert surplus_fractions_for_price(buyer, seller, 85.0) is None


def test_price_outside_zopa_returns_none() -> None:
    """A proposed price outside the ZOPA is not a viable agreement."""
    buyer = _buyer(price_max=100.0)
    seller = _seller(price_min=90.0)

    assert surplus_fractions_for_price(buyer, seller, 120.0) is None
    assert surplus_fractions_for_price(buyer, seller, 50.0) is None

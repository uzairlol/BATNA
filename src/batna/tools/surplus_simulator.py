"""In-process, pure game-theoretic surplus simulator (Phase 4).

Wraps the deterministic engine's :func:`batna.engine.scoring.calculate_zopa` and
:func:`batna.engine.scoring.calculate_nash_price` and adds the cooperative-surplus
split math that follows from them.

For a single cost-like term (price) with linear utilities:

* ``buyer_reservation`` = upper bound of the buyer's authorized mandate for the term.
* ``seller_reservation`` = lower bound of the seller's authorized mandate.
* The ZOPA is ``[seller_reservation, buyer_reservation]``.
* For any price ``p`` in the ZOPA, total cooperative surplus is constant:
  ``total = (R_buyer - p) + (p - R_seller) = R_buyer - R_seller``.
* The Nash Bargaining Solution over linear utilities is the midpoint
  ``(R_buyer + R_seller) / 2``, which splits that surplus 50 / 50.

This module is deliberately pure (no I/O, no LLM), so it can be reasoned about,
tested against hand-computed values, and reused by agents as a deterministic tool.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from batna.engine.principal import Principal
from batna.engine.scoring import calculate_nash_price, calculate_zopa

__all__ = [
    "SurplusShare",
    "SurplusSimulation",
    "simulate_surplus",
    "surplus_fractions_for_price",
]


class SurplusShare(BaseModel):
    """Fraction of the cooperative surplus captured by each party at a given price.

    ``buyer_fraction + seller_fraction`` always sum to 1.0 for a price inside the
    ZOPA.
    """

    buyer_fraction: float = Field(
        ..., description="Share of surplus captured by the buyer in [0, 1]"
    )
    seller_fraction: float = Field(
        ..., description="Share of surplus captured by the seller in [0, 1]"
    )


class SurplusSimulation(BaseModel):
    """Result of simulating the cooperative surplus for a term between two principals."""

    term: str = Field(..., description="Contract term the surplus is computed over (e.g. 'price')")
    zopa: tuple[float, float] = Field(
        ..., description="Inclusive Zone of Possible Agreement [low, high]"
    )
    nash_price: float = Field(..., description="Nash Bargaining Solution price")
    total_surplus: float = Field(..., description="Total cooperative surplus over the ZOPA")
    buyer_reservation: float = Field(..., description="Buyer reservation bound for the term")
    seller_reservation: float = Field(..., description="Seller reservation bound for the term")
    nash_share: SurplusShare = Field(..., description="Surplus split at the Nash solution")


def simulate_surplus(
    buyer: Principal, seller: Principal, term: str = "price"
) -> SurplusSimulation | None:
    """Simulate the cooperative surplus for a term between ``buyer`` and ``seller``.

    Returns ``None`` when no ZOPA exists (the parties cannot reach an agreement on
    this term).
    """
    zopa = calculate_zopa(buyer, seller, term)
    nash_price = calculate_nash_price(buyer, seller, term)
    if zopa is None or nash_price is None:
        return None

    low, high = zopa
    buyer_reservation = buyer.authorized_mandate[term][1]
    seller_reservation = seller.authorized_mandate[term][0]
    total_surplus = high - low

    nash_share = _share_for_price(buyer_reservation, seller_reservation, nash_price)
    return SurplusSimulation(
        term=term,
        zopa=(low, high),
        nash_price=nash_price,
        total_surplus=total_surplus,
        buyer_reservation=buyer_reservation,
        seller_reservation=seller_reservation,
        nash_share=nash_share,
    )


def surplus_fractions_for_price(
    buyer: Principal,
    seller: Principal,
    price: float,
    term: str = "price",
) -> SurplusShare | None:
    """Return the surplus split a proposed ``price`` would yield.

    Returns ``None`` if ``price`` falls outside the ZOPA, since that price is not
    a viable agreement for both parties.
    """
    zopa = calculate_zopa(buyer, seller, term)
    if zopa is None:
        return None
    low, high = zopa
    if not low <= price <= high:
        return None

    buyer_reservation = buyer.authorized_mandate[term][1]
    seller_reservation = seller.authorized_mandate[term][0]
    return _share_for_price(buyer_reservation, seller_reservation, price)


def _share_for_price(
    buyer_reservation: float, seller_reservation: float, price: float
) -> SurplusShare:
    """Compute the buyer/seller surplus split for ``price`` within the reservations.

    Guarded against a degenerate zero-width range by attributing 100% to the buyer.
    """
    span = buyer_reservation - seller_reservation
    if span <= 0:
        return SurplusShare(buyer_fraction=1.0, seller_fraction=0.0)
    buyer_fraction = (buyer_reservation - price) / span
    seller_fraction = (price - seller_reservation) / span
    return SurplusShare(buyer_fraction=buyer_fraction, seller_fraction=seller_fraction)

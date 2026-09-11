"""Scoring functions for BATNA negotiation engine: ZOPA and Nash Bargaining Solution."""

from __future__ import annotations

from .principal import Principal


def calculate_zopa(
    buyer: Principal, seller: Principal, term: str = "price"
) -> tuple[float, float] | None:
    """
    Calculate the Zone of Possible Agreement (ZOPA) for a given term.

    Assumes:
      - For the buyer, the term is acceptable up to the maximum in their mandate
        (i.e., they prefer lower values for cost-like terms, higher for benefit-like).
      - For the seller, the term is acceptable from the minimum in their mandate
        (i.e., they prefer higher values for cost-like terms, lower for benefit-like).

    This implementation treats the term as a cost-like term (price), where:
      - Buyer accepts values <= buyer_mandate[term][1]
      - Seller accepts values >= seller_mandate[term][0]

    Returns:
        Tuple (low, high) representing the inclusive ZOPA range, or None if no ZOPA exists.
    """
    if term not in buyer.authorized_mandate or term not in seller.authorized_mandate:
        raise ValueError(f"Term '{term}' not found in one or both principals' mandates")

    _, buyer_max = buyer.authorized_mandate[term]
    seller_min, _ = seller.authorized_mandate[term]

    # For cost-like term (price):
    #   Buyer accepts: (-inf, buyer_max]
    #   Seller accepts: [seller_min, +inf)
    # Intersection: [seller_min, buyer_max] if seller_min <= buyer_max
    low = seller_min
    high = buyer_max

    if low > high:
        return None
    return (low, high)


def calculate_nash_price(buyer: Principal, seller: Principal, term: str = "price") -> float | None:
    """
    Calculate the Nash Bargaining Solution price for a given term.

    Assumes linear utility functions:
      - Buyer utility: (buyer_reservation - price) / (buyer_reservation - buyer_target)
        for price in [buyer_target, buyer_reservation]; 0 outside.
      - Seller utility: (price - seller_reservation) / (seller_target - seller_reservation)
        for price in [seller_reservation, seller_target]; 0 outside.

    The Nash solution maximizes the product of buyer and seller utilities.
    For linear utilities and disagreement points at the reservations, the solution is:
        price = (buyer_reservation + seller_reservation) / 2

    Returns:
        The Nash price (float) if ZOPA exists, otherwise None.
    """
    zopa = calculate_zopa(buyer, seller, term)
    if zopa is None:
        return None

    low, high = zopa

    # Extract reservation values for the term from the principals.
    # We assume:
    #   buyer_reservation = buyer's mandate max for the term
    #   seller_reservation = seller's mandate min for the term
    buyer_reservation = buyer.authorized_mandate[term][1]
    seller_reservation = seller.authorized_mandate[term][0]

    # Nash price is the midpoint of the two reservations.
    nash_price = (buyer_reservation + seller_reservation) / 2.0

    # Clamp to ZOPA (should already be within ZOPA if targets are beyond reservations)
    nash_price = max(low, min(high, nash_price))

    return nash_price

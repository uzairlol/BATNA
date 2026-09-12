"""Unit tests for the Phase 5 scripted counterparty (deterministic seller)."""

from __future__ import annotations

import pytest

from batna.agents.scripted_counterparty import CounterOffer, ScriptedSeller


def test_seller_concedes_toward_reservation() -> None:
    seller = ScriptedSeller(
        asking_price=1_000.0,
        reservation_price=400.0,
        concessions_per_round=0.1,
        max_rounds=3,
    )
    rounds: list[CounterOffer] = []
    for _ in range(3):
        rounds.append(seller.respond(0.0))
    assert [offer.price for offer in rounds] == [940.0, 880.0, 820.0]
    assert rounds[0].is_final is False
    assert rounds[2].is_final is True  # reached max_rounds


def test_seller_never_goes_below_reservation_price() -> None:
    seller = ScriptedSeller(
        asking_price=1_000.0,
        reservation_price=700.0,
        concessions_per_round=0.5,
        max_rounds=10,
    )
    prices = [seller.respond(0.0).price for _ in range(10)]
    assert min(prices) == 700.0  # floor enforced over many rounds


def test_seller_rejects_invalid_pricing() -> None:
    with pytest.raises(ValueError):
        ScriptedSeller(asking_price=100.0, reservation_price=200.0)


def test_current_buyer_offer_is_reserved_for_future_logic() -> None:
    seller = ScriptedSeller(asking_price=100.0, reservation_price=50.0, max_rounds=1)
    offer = seller.respond(10_000.0)
    assert offer.price == 95.0  # schedule unchanged by the buyer's offer (round-1 concession)

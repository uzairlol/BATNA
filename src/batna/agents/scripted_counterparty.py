"""A deterministic, scripted counterparty (seller) for Phase 5 negotiation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CounterOffer:
    round: int
    price: float
    is_final: bool


class ScriptedSeller:
    """Seller that concedes from asking toward a reservation price on a fixed schedule."""

    def __init__(
        self,
        asking_price: float,
        reservation_price: float,
        concessions_per_round: float = 0.1,
        max_rounds: int = 3,
    ) -> None:
        if reservation_price > asking_price:
            raise ValueError("reservation_price must be <= asking_price")
        self.asking_price = asking_price
        self.reservation_price = reservation_price
        self.concessions_per_round = concessions_per_round
        self.max_rounds = max_rounds
        self._round = 0

    def respond(self, buyer_offer: float) -> CounterOffer:
        del buyer_offer  # seller responds on a fixed schedule regardless of the offer
        self._round += 1
        step = (self.asking_price - self.reservation_price) * self.concessions_per_round
        counter = max(self.asking_price - step * self._round, self.reservation_price)
        return CounterOffer(
            round=self._round,
            price=round(counter, 2),
            is_final=self._round >= self.max_rounds,
        )

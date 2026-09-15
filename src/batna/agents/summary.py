"""Post-negotiation metrics/summary for the live dashboard.

Phase 8 computes an authoritative, serializable metrics blob for a finished
negotiation so the frontend can render offer trajectories, per-side
concessions, and outcome KPIs without re-deriving them from stream events.
``build_session_summary`` runs in the graph right after a terminal outcome is
reached, where the real state (turn history, principals, acceptance checks)
and each side's ``ToolCallLog`` are all in hand.
"""

from __future__ import annotations

from datetime import datetime
from itertools import pairwise
from typing import Any

from batna.engine.acceptance import NegotiationOutcome
from batna.engine.principal import Principal


def _price_zone(buyer: Principal, seller: Principal) -> dict[str, float]:
    """Price mandate bounds for both sides (drives the ZOPA band on the chart)."""
    buyer_min, buyer_max = buyer.authorized_mandate["price"]
    seller_min, seller_max = seller.authorized_mandate["price"]
    return {
        "buyer_min": float(buyer_min),
        "buyer_max": float(buyer_max),
        "seller_min": float(seller_min),
        "seller_max": float(seller_max),
    }


def _side_offer_lists(turn_history: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    """Split the ordered exchange into buyer and seller offer-price sequences.

    Offers strictly alternate buyer -> seller (the buyer opens), so each side's
    own list is in chronological order and maps 1:1 to rounds.
    """
    buyer_offers: list[float] = []
    seller_offers: list[float] = []
    for turn in turn_history:
        terms = turn.get("terms") or {}
        price = terms.get("price")
        if price is None:
            continue
        if turn.get("role") == "seller":
            seller_offers.append(float(price))
        else:
            buyer_offers.append(float(price))
    return buyer_offers, seller_offers


def _side_metrics(offers: list[float]) -> dict[str, Any]:
    """Per-side summary: opening/closing prices, total concession, and steps."""
    if not offers:
        return {
            "opening_price": None,
            "closing_price": None,
            "total_concession": 0.0,
            "max_step": 0.0,
            "avg_step": 0.0,
            "offers": [],
        }
    opening = offers[0]
    closing = offers[-1]
    total = abs(closing - opening)
    steps = [abs(b - a) for a, b in pairwise(offers)]
    return {
        "opening_price": opening,
        "closing_price": closing,
        "total_concession": round(total, 2),
        "max_step": round(max(steps), 2) if steps else 0.0,
        "avg_step": round(sum(steps) / len(steps), 2) if steps else 0.0,
        "offers": [round(float(o), 2) for o in offers],
    }


def _acceptance_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    """Tally acceptance checks and "near misses" (exactly one term out of range)."""
    checks = 0
    near_misses = 0
    for ev in events:
        if ev.get("type") != "acceptance_check":
            continue
        checks += 1
        if not ev.get("acceptable") and len(ev.get("failures") or []) == 1:
            near_misses += 1
    return {"checks": checks, "near_misses": near_misses}


def _duration_ms(started_at: str, finished_at: str) -> int:
    try:
        start = datetime.fromisoformat(started_at)
        finish = datetime.fromisoformat(finished_at)
        return max(0, int((finish - start).total_seconds() * 1000))
    except (ValueError, TypeError):
        return 0


def build_session_summary(
    result: dict[str, Any],
    *,
    buyer_principal: Principal,
    seller_principal: Principal,
    buyer_tool_counts: dict[str, int],
    seller_tool_counts: dict[str, int],
    started_at: str,
    finished_at: str,
    until_agreement: bool,
) -> dict[str, Any]:
    """Compute the serializable metrics blob for a finished negotiation.

    ``result`` is the final negotiation state returned by ``run_negotiation``
    (carrying ``turn_history``, ``outcome``, ``accepted_offer``,
    ``rounds_elapsed``, and the accumulated ``events``).
    """
    raw_outcome = result.get("outcome")
    outcome = (
        raw_outcome.value if isinstance(raw_outcome, NegotiationOutcome) else str(raw_outcome or "")
    )
    reached_agreement = outcome == NegotiationOutcome.AGREEMENT.value

    accepted = result.get("accepted_offer")
    agreed_price = None
    agreed_at_round = None
    if reached_agreement and result.get("outcome") is not None and accepted is not None:
        agreed_price = round(float(accepted.price), 2)
        agreed_at_round = int(result.get("rounds_elapsed", 0) or 0)

    buyer_offers, seller_offers = _side_offer_lists(result.get("turn_history") or [])
    buyer = _side_metrics(buyer_offers)
    seller = _side_metrics(seller_offers)

    convergence_gap = 0.0
    if not reached_agreement and buyer_offers and seller_offers:
        convergence_gap = round(abs(buyer_offers[-1] - seller_offers[-1]), 2)

    acceptance = _acceptance_counts(result.get("events") or [])

    return {
        "outcome": outcome,
        "rounds_elapsed": int(result.get("rounds_elapsed", 0)),
        "max_rounds": int(result.get("effective_max_rounds") or result.get("max_rounds", 0)),
        "until_agreement": bool(until_agreement),
        "agreed_price": agreed_price,
        "agreed_at_round": agreed_at_round,
        "convergence_gap": convergence_gap,
        "price_zone": _price_zone(buyer_principal, seller_principal),
        "buyer": buyer,
        "seller": seller,
        "tool_breakdown": {
            "buyer": buyer_tool_counts,
            "seller": seller_tool_counts,
        },
        "acceptance_checks": acceptance["checks"],
        "near_misses": acceptance["near_misses"],
        "duration_ms": _duration_ms(started_at, finished_at),
    }

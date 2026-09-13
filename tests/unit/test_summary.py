"""Unit tests for ``batna.agents.summary.build_session_summary``.

These exercise the metrics blob directly (no graph) using synthetic final state,
so the trajectory/concession/outcome math is pinned precisely rather than
observed through a live negotiation.
"""

from __future__ import annotations

from typing import cast

from batna.agents.summary import build_session_summary
from batna.engine.acceptance import NegotiationOutcome
from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal

_START = "2026-09-13T10:00:00+00:00"
_FINISH = "2026-09-13T10:00:02+00:00"


def _principals() -> tuple[Principal, Principal]:
    buyer = Principal(
        reservation_value=100_000.0,
        target_value=80_000.0,
        authorized_mandate={
            "price": (60_000.0, 100_000.0),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )
    seller = Principal(
        reservation_value=90_000.0,
        target_value=110_000.0,
        authorized_mandate={
            "price": (90_000.0, 130_000.0),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (10, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )
    return buyer, seller


def _terms(price: float, **overrides: float | int) -> dict[str, object]:
    base: dict[str, object] = {
        "price": price,
        "payment_terms_days": 30,
        "delivery_sla_days": 14,
        "liability_cap_pct": 20,
        "contract_duration_months": 24,
        "termination_notice_days": 60,
    }
    base.update(overrides)
    return base


def _agreement_result(buyer_p: Principal, seller_p: Principal) -> dict[str, object]:
    turn_history = [
        {"role": "buyer", "terms": _terms(90_000.0)},
        {"role": "seller", "terms": _terms(120_000.0)},
        {"role": "buyer", "terms": _terms(95_000.0)},
        {"role": "seller", "terms": _terms(112_000.0)},
        {"role": "buyer", "terms": _terms(99_000.0)},
        {"role": "seller", "terms": _terms(104_000.0)},
    ]
    events = [
        {"type": "offer", "side": "buyer", "terms": _terms(90_000.0)},
        {"type": "offer", "side": "seller", "terms": _terms(120_000.0)},
        {"type": "acceptance_check", "side": "seller", "acceptable": False, "failures": ["price"]},
        {
            "type": "acceptance_check",
            "side": "buyer",
            "acceptable": False,
            "failures": ["price", "delivery_sla_days"],
        },
        {"type": "acceptance_check", "side": "seller", "acceptable": True, "failures": []},
        {"type": "finalize", "outcome": "agreement"},
    ]
    return {
        "outcome": NegotiationOutcome.AGREEMENT,
        "accepted_offer": ContractTerms(**_terms(104_000.0)),
        "rounds_elapsed": 3,
        "max_rounds": 12,
        "turn_history": turn_history,
        "events": events,
    }


def test_summary_agreement_metrics() -> None:
    buyer_p, seller_p = _principals()
    summary = build_session_summary(
        _agreement_result(buyer_p, seller_p),
        buyer_principal=buyer_p,
        seller_principal=seller_p,
        buyer_tool_counts={"get_market_benchmark": 2},
        seller_tool_counts={"get_market_benchmark": 1},
        started_at=_START,
        finished_at=_FINISH,
        until_agreement=False,
    )

    assert summary["outcome"] == "agreement"
    assert summary["agreed_price"] == 104_000.0
    assert summary["agreed_at_round"] == 3
    assert summary["max_rounds"] == 12
    assert summary["until_agreement"] is False
    # Buyer moved 90k -> 99k (up toward seller); seller 120k -> 104k (down).
    assert summary["buyer"]["opening_price"] == 90_000.0
    assert summary["buyer"]["closing_price"] == 99_000.0
    assert summary["buyer"]["total_concession"] == 9_000.0
    assert summary["seller"]["opening_price"] == 120_000.0
    assert summary["seller"]["closing_price"] == 104_000.0
    assert summary["seller"]["total_concession"] == 16_000.0
    assert summary["buyer"]["offers"] == [90_000.0, 95_000.0, 99_000.0]
    assert summary["seller"]["offers"] == [120_000.0, 112_000.0, 104_000.0]
    # Agreement => no convergence gap.
    assert summary["convergence_gap"] == 0.0
    # ZOPA band derived from price mandates.
    assert summary["price_zone"] == {
        "buyer_min": 60_000.0,
        "buyer_max": 100_000.0,
        "seller_min": 90_000.0,
        "seller_max": 130_000.0,
    }
    assert summary["tool_breakdown"]["buyer"] == {"get_market_benchmark": 2}
    assert summary["tool_breakdown"]["seller"] == {"get_market_benchmark": 1}
    # 3 acceptance checks, 2 failures, but only the single-term one is a near miss.
    assert summary["acceptance_checks"] == 3
    assert summary["near_misses"] == 1
    assert summary["duration_ms"] == 2000


def test_summary_no_agreement_gap_and_until_agreement_flag() -> None:
    buyer_p, seller_p = _principals()
    result = _agreement_result(buyer_p, seller_p)
    result["outcome"] = NegotiationOutcome.ROUND_EXHAUSTION
    result["accepted_offer"] = None
    # Force a gap: last buyer offer 99k, last seller offer 112k.
    turn_history = cast("list[dict[str, object]]", result["turn_history"])
    turn_history[-1]["terms"] = _terms(112_000.0)

    summary = build_session_summary(
        result,
        buyer_principal=buyer_p,
        seller_principal=seller_p,
        buyer_tool_counts={},
        seller_tool_counts={},
        started_at=_START,
        finished_at=_FINISH,
        until_agreement=True,
    )

    assert summary["outcome"] == "round_exhaustion"
    assert summary["agreed_price"] is None
    assert summary["agreed_at_round"] is None
    assert summary["until_agreement"] is True
    assert summary["convergence_gap"] == round(abs(99_000.0 - 112_000.0), 2)

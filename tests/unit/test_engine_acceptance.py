"""Unit tests for the Phase 6 engine acceptance logic (deterministic, hand-computed).

These validate ``is_acceptable`` / ``acceptance_report`` / ``classify_outcome``
against values computed by hand, so the graph's acceptance semantics are pinned
before any agent code exists.
"""

from __future__ import annotations

from batna.engine.acceptance import (
    NegotiationOutcome,
    acceptance_report,
    classify_outcome,
    is_acceptable,
)
from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal

_BUYER = Principal(
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

_SELLER = Principal(
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


def _terms(**overrides: float | int) -> ContractTerms:
    base: dict[str, float | int] = {
        "price": 95_000.0,
        "payment_terms_days": 30,
        "delivery_sla_days": 14,
        "liability_cap_pct": 20.0,
        "contract_duration_months": 24,
        "termination_notice_days": 60,
    }
    base.update(overrides)
    return ContractTerms(**base)


def test_offer_inside_every_mandate_is_acceptable() -> None:
    offer = _terms()
    decision = is_acceptable(offer, _BUYER)
    assert decision.acceptable is True
    assert decision.failures == ()


def test_offer_outside_price_mandate_is_rejected() -> None:
    # 150_000 exceeds the buyer's price ceiling of 100_000.
    decision = is_acceptable(_terms(price=150_000.0), _BUYER)
    assert decision.acceptable is False
    assert decision.failures == ("price",)


def test_price_above_buyer_max_but_within_seller_accepted_by_seller() -> None:
    # The seller accepts prices >= 90_000, so 120_000 is fine for the seller.
    decision = is_acceptable(_terms(price=120_000.0), _SELLER)
    assert decision.acceptable is True


def test_every_non_price_term_is_checked() -> None:
    # Each single-term violation must be caught independently.
    cases: list[tuple[str, float | int]] = [
        ("payment_terms_days", 90),  # buyer max is 60
        ("delivery_sla_days", 60),  # buyer max is 30
        ("liability_cap_pct", 5.0),  # buyer min is 10
        ("contract_duration_months", 60),  # buyer max is 36
        ("termination_notice_days", 10),  # buyer min is 30
    ]
    for term, out_of_range in cases:
        decision = is_acceptable(_terms(**{term: out_of_range}), _BUYER)
        assert decision.acceptable is False
        assert term in decision.failures, f"expected {term} flagged, got {decision.failures}"


def test_boundary_values_are_inclusive() -> None:
    # Exact mandate bounds are acceptable (inclusive).
    decision = is_acceptable(
        _terms(
            price=100_000.0,
            payment_terms_days=60,
            delivery_sla_days=30,
            liability_cap_pct=10.0,
            contract_duration_months=36,
            termination_notice_days=30,
        ),
        _BUYER,
    )
    assert decision.acceptable is True


def test_multiple_failures_listed() -> None:
    decision = is_acceptable(
        _terms(price=200_000.0, liability_cap_pct=2.0, payment_terms_days=120),
        _BUYER,
    )
    assert decision.acceptable is False
    assert set(decision.failures) == {"price", "liability_cap_pct", "payment_terms_days"}


def test_acceptance_report_serializable() -> None:
    offer = _terms(price=150_000.0)
    report = acceptance_report(offer, _BUYER)
    assert report.mode == "engine"
    assert report.acceptable is False
    assert report.failures == ["price"]
    # Round-trips through pydantic (audit-friendly).
    assert report.model_dump()["failures"] == ["price"]


def test_classify_agreement() -> None:
    outcome = classify_outcome(
        _BUYER, _SELLER, reached_agreement=True, rounds_elapsed=3, max_rounds=10
    )
    assert outcome is NegotiationOutcome.AGREEMENT


def test_classify_no_zopa() -> None:
    hard_seller = _SELLER.model_copy(
        update={
            "authorized_mandate": {
                **_SELLER.authorized_mandate,
                "price": (140_000.0, 200_000.0),
            }
        }
    )
    outcome = classify_outcome(
        _BUYER, hard_seller, reached_agreement=False, rounds_elapsed=1, max_rounds=10
    )
    assert outcome is NegotiationOutcome.NO_ZOPA


def test_classify_round_exhaustion() -> None:
    outcome = classify_outcome(
        _BUYER, _SELLER, reached_agreement=False, rounds_elapsed=10, max_rounds=10
    )
    assert outcome is NegotiationOutcome.ROUND_EXHAUSTION


def test_classify_nonterminal_raises() -> None:
    try:
        classify_outcome(_BUYER, _SELLER, reached_agreement=False, rounds_elapsed=3, max_rounds=10)
    except ValueError:
        return
    raise AssertionError("expected ValueError for a non-terminal session state")

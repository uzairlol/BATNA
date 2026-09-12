"""Unit tests for the Phase 4 in-process risk checker."""

from __future__ import annotations

import pytest

from batna.engine.contract import ContractTerms
from batna.tools.risk_checker import (
    CITATIONS,
    RiskAssessment,
    RiskCheck,
    RiskSeverity,
    RiskStatus,
    RiskThresholds,
    assess_contract_risk,
)


def _healthy_terms(price: float = 95.0) -> ContractTerms:
    """Build a baseline healthy contract with all risk rules passing."""
    return ContractTerms(
        price=price,
        payment_terms_days=30,
        delivery_sla_days=14,
        liability_cap_pct=20.0,
        contract_duration_months=24,
        termination_notice_days=60,
    )


def _find_check(assessment: RiskAssessment, rule_id: str) -> RiskCheck:
    return next(c for c in assessment.checks if c.rule_id == rule_id)


def test_healthy_contract_passes_all_rules() -> None:
    """A within-mandate, market-aligned contract should flag nothing."""
    result = assess_contract_risk(
        _healthy_terms(price=95.0),
        market_reference_price=100.0,
        price_mandate=(80.0, 120.0),
    )
    assert result.blocked is False
    assert result.flagged_count == 0
    assert all(c.status is RiskStatus.PASSED for c in result.checks)


def test_mandate_violation_blocks_assessment() -> None:
    """A price outside the authorized mandate is a HIGH violation and blocks."""
    result = assess_contract_risk(
        _healthy_terms(price=150.0),
        market_reference_price=100.0,
        price_mandate=(80.0, 120.0),
    )
    mandate = _find_check(result, "MANDATE_RANGE")
    assert mandate.status is RiskStatus.FLAGGED
    assert mandate.severity is RiskSeverity.HIGH
    assert result.blocked is True


def test_payment_terms_over_net_30_flagged() -> None:
    """Payment terms beyond the federal net-30 standard should flag (MEDIUM)."""
    terms = _healthy_terms()
    terms = terms.model_copy(update={"payment_terms_days": 45})
    result = assess_contract_risk(terms, price_mandate=(80.0, 120.0))
    payment = _find_check(result, "PAYMENT_TERMS_NET_30")
    assert payment.status is RiskStatus.FLAGGED
    assert payment.severity is RiskSeverity.MEDIUM
    assert result.blocked is False
    assert "31 U.S.C." in payment.citation


def test_price_deviation_beyond_tolerance_flagged() -> None:
    """A price far from the market reference flags the deviation rule."""
    result = assess_contract_risk(
        _healthy_terms(price=200.0),
        market_reference_price=100.0,
        price_mandate=(50.0, 250.0),
    )
    deviation = _find_check(result, "PRICE_MARKET_DEVIATION")
    assert deviation.status is RiskStatus.FLAGGED
    assert "Producer Price Index" in deviation.citation


def test_price_deviation_within_tolerance_passes() -> None:
    """A price within tolerance of the market reference passes the deviation rule."""
    result = assess_contract_risk(
        _healthy_terms(price=105.0),
        market_reference_price=100.0,
    )
    deviation = _find_check(result, "PRICE_MARKET_DEVIATION")
    assert deviation.status is RiskStatus.PASSED


def test_hardcoded_threshold_sources_are_defensible() -> None:
    """Every citation referenced by a rule must be documented and non-empty (DoD)."""
    result = assess_contract_risk(
        _healthy_terms(price=200.0),
        market_reference_price=100.0,
        price_mandate=(80.0, 120.0),
    )
    assert result.flagged_count >= 1
    assert all(c.citation for c in result.checks), "Every check needs a citation"
    assert all(CITATIONS[k] for k in CITATIONS), "No empty citation entries"
    assert set(CITATIONS) == {
        "prompt_payment_act",
        "ucc_2_309",
        "ppi_market_data",
        "liability_cap_practice",
        "authorized_mandate",
    }


def test_liability_cap_below_floor_can_be_waived_via_threshold_override() -> None:
    """A low liability cap flags on the default floor but passes a lower override."""
    terms = _healthy_terms().model_copy(update={"liability_cap_pct": 5.0})
    default = assess_contract_risk(terms, price_mandate=(80.0, 120.0))
    assert _find_check(default, "LIABILITY_CAP_FLOOR").status is RiskStatus.FLAGGED

    relaxed = assess_contract_risk(
        terms,
        price_mandate=(80.0, 120.0),
        thresholds=RiskThresholds(min_liability_cap_pct=0.02),
    )
    assert _find_check(relaxed, "LIABILITY_CAP_FLOOR").status is RiskStatus.PASSED


def test_zero_termination_notice_flagged() -> None:
    """A zero-day termination notice contradicts UCC 2-309 reasonable-notice."""
    terms = _healthy_terms().model_copy(update={"termination_notice_days": 0})
    result = assess_contract_risk(terms, price_mandate=(80.0, 120.0))
    notice = _find_check(result, "TERMINATION_NOTICE_MIN")
    assert notice.status is RiskStatus.FLAGGED
    assert "2-309" in notice.citation


def test_thresholds_defaults_match_config() -> None:
    """RiskThresholds defaults line up with the documented policy constants."""
    import batna.config

    thresholds = RiskThresholds()
    assert thresholds.price_deviation_pct == pytest.approx(
        batna.config.settings.risk_price_deviation_pct
    )
    assert thresholds.min_liability_cap_pct == pytest.approx(
        batna.config.settings.risk_min_liability_cap_pct
    )
    assert thresholds.termination_notice_min_days == (
        batna.config.settings.risk_termination_notice_min_days
    )

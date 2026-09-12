"""Unit tests for the Phase 5 claim-vs-call-log verification (DoD diffing)."""

from __future__ import annotations

from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.agents.verification import (
    VerificationOptions,
    verify_claims_grounded,
)


def _log_with(responses: list[str]) -> ToolCallLog:
    log = ToolCallLog()
    for response in responses:
        log.append(ToolCallEntry(name="search_precedent", arguments={}, response=response, ok=True))
    return log


def test_truthful_citation_is_grounded() -> None:
    log = _log_with(['[{"vendor": "Acme", "amount": 2500000.0}]'])
    text = "Acme precedent at $2,500,000; our opening is $2,000,000."
    report = verify_claims_grounded(
        log,
        text,
        VerificationOptions(excluded_values={2_000_000.0}),
    )
    assert report.grounded is True
    assert report.ungrounded_values == []
    assert 2_500_000.0 in report.fetched_values


def test_invented_value_is_flagged() -> None:
    log = _log_with(['[{"vendor": "Acme", "amount": 2500000.0}]'])
    text = "I found a precedent at an invented $33,333,333, so we open at $3,000,000."
    report = verify_claims_grounded(
        log,
        text,
        VerificationOptions(excluded_values={3_000_000.0}),
    )
    assert report.grounded is False
    assert 33_333_333.0 in report.ungrounded_values


def test_market_benchmark_citation_is_grounded() -> None:
    log = _log_with(['{"latest_value": 118.5, "annual_pct_change": 2.3}'])
    text = "The live benchmark sits at 118.5 with 2.3% annual growth."
    report = verify_claims_grounded(log, text)
    assert report.grounded is True
    assert 118.5 in report.fetched_values


def test_small_integers_are_not_treated_as_data_claims() -> None:
    log = _log_with(['{"latest_value": 118.5}'])
    text = "We analyzed 5 rounds in 2024 of our budget."
    report = verify_claims_grounded(log, text)
    # 2024 (year) and 5 (count) are not significant data figures.
    assert report.claimed_values == []
    assert report.grounded is True

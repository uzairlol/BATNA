"""Unit tests for the Phase 6 structured offer protocol."""

from __future__ import annotations

import pytest

from batna.agents.offers import OfferParseError, format_offer, parse_offer
from batna.engine.contract import ContractTerms

_FULL = {
    "price": 95_000.0,
    "payment_terms_days": 30,
    "delivery_sla_days": 14,
    "liability_cap_pct": 20.0,
    "contract_duration_months": 24,
    "termination_notice_days": 60,
}


def test_parse_marker_line() -> None:
    parsed = parse_offer(
        "We can do the following terms.\nOFFER_JSON="
        '{"price": 95000.0, "payment_terms_days": 30, "delivery_sla_days": 14, '
        '"liability_cap_pct": 20.0, "contract_duration_months": 24, '
        '"termination_notice_days": 60}'
    )
    assert isinstance(parsed.terms, ContractTerms)
    assert parsed.terms.price == 95_000.0
    assert parsed.terms.liability_cap_pct == 20.0


def test_parse_fenced_json_block() -> None:
    text = "Proposal:\n```json\n" + format_offer(ContractTerms(**_FULL)).split("=", 1)[1] + "\n```"
    parsed = parse_offer(text)
    assert parsed.terms.price == 95_000.0


def test_parse_requires_all_six_terms() -> None:
    missing = {k: v for k, v in _FULL.items() if k != "price"}
    with pytest.raises(OfferParseError):
        parse_offer(f"OFFER_JSON={missing!r}")


def test_parse_rejects_out_of_domain_values() -> None:
    bad = {**_FULL, "price": -5.0}
    with pytest.raises(OfferParseError):
        parse_offer(f"OFFER_JSON={bad!r}")


def test_parse_rejects_text_without_json() -> None:
    with pytest.raises(OfferParseError):
        parse_offer("I have no structured offer yet, just thinking...")
    with pytest.raises(OfferParseError):
        parse_offer("OFFER_JSON=notjson")


def test_format_round_trip() -> None:
    terms = ContractTerms(**_FULL)
    formatted = format_offer(terms)
    assert formatted.startswith("OFFER_JSON=")
    parsed = parse_offer(formatted)
    assert parsed.terms == terms


def test_marker_takes_precedence_over_fenced() -> None:
    full_marker = format_offer(ContractTerms(**_FULL))
    text = "```json\n" + full_marker.split("=", 1)[1] + "\n```\n" + full_marker
    parsed = parse_offer(text)
    assert parsed.terms.price == 95_000.0
    # A complete valid marker beats the fenced block even when both are present.
    other = {**_FULL, "price": 88_000.0}
    other_marker = format_offer(ContractTerms(**other)).split("=", 1)[1]
    text2 = "```json\n" + full_marker.split("=", 1)[1] + "\n```\nOFFER_JSON=" + other_marker
    parsed2 = parse_offer(text2)
    assert parsed2.terms.price == 88_000.0
    # An invalid/partial marker falls through to the fenced block.
    text3 = "```json\n" + full_marker.split("=", 1)[1] + "\n```\nOFFER_JSON=" + '{"price": 123.0}'
    parsed3 = parse_offer(text3)
    assert parsed3.terms.price == 95_000.0

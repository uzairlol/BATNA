"""Unit tests for the Phase 8 deterministic ToM auditor.

Nine Definition-of-Done cases (three per consistency surface) plus a positive
control and a wire-contract check. Everything is hermetic: no live model, no
network — the auditor calls only deterministic in-process logic on hand-built
reasoning text, offers, and ``ToolCallLog`` fixtures.
"""

from __future__ import annotations

import json

import pytest

from batna.agents.offers import format_offer
from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.audit.schemas import AuditFinding, AuditKind, AuditReport, AuditSeverity
from batna.audit.tom_auditor import ToMAuditor
from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal
from batna.stream.events import EventType
from batna.stream.sink import InMemoryStreamSink


def _terms(price: float = 95_000.0, *, liability_cap_pct: float = 20.0) -> ContractTerms:
    return ContractTerms(
        price=price,
        payment_terms_days=30,
        delivery_sla_days=14,
        liability_cap_pct=liability_cap_pct,
        contract_duration_months=24,
        termination_notice_days=60,
    )


def _buyer_principal(
    *,
    price_max: float = 100_000.0,
    liability_min: float = 10.0,
) -> Principal:
    return Principal(
        reservation_value=100_000.0,
        target_value=80_000.0,
        authorized_mandate={
            "price": (60_000.0, price_max),
            "payment_terms_days": (15, 60),
            "delivery_sla_days": (7, 30),
            "liability_cap_pct": (liability_min, 30),
            "contract_duration_months": (12, 36),
            "termination_notice_days": (30, 90),
        },
        round_budget=10,
    )


def _payload(terms: ContractTerms, prose: str) -> str:
    """A realistic turn: prose justification plus an OFFER_JSON payload line."""
    return f"{prose}\n{format_offer(terms)}"


def _benchmark_log(latest: float = 95.0) -> ToolCallLog:
    log = ToolCallLog()
    log.append(
        ToolCallEntry(
            name="get_market_benchmark",
            arguments={"industry": "cloud_hosting"},
            response=json.dumps(
                {
                    "source": "BLS",
                    "series_id": "PCUINFO",
                    "latest_value": latest,
                    "annual_pct_change": 2.1,
                }
            ),
        )
    )
    return log


def _finding(report: AuditReport, kind: AuditKind) -> AuditFinding:
    for finding in report.findings:
        if finding.kind is kind:
            return finding
    raise AssertionError(f"no finding of kind {kind} in {report.findings!r}")


# ---------------------------------------------------------------------------
# 1. Reasoning-Offer consistency (3 DoD cases)
# ---------------------------------------------------------------------------


async def test_reasoning_offer_consistent_when_prose_matches_offer() -> None:
    terms = _terms(price=95_000.0)
    text = _payload(terms, "We propose $95,000 for the platform, which sits within our mandate.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_OFFER)
    assert finding.consistent is True
    assert finding.severity is AuditSeverity.INFO


async def test_reasoning_offer_inconsistent_price_mismatch() -> None:
    terms = _terms(price=95_000.0)
    text = _payload(terms, "Their ask is steep; we hold our counter at $120,000.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_OFFER)
    assert finding.consistent is False
    assert finding.severity is AuditSeverity.WARNING
    assert finding.detail["prose_price"] == 120_000.0
    assert finding.detail["offered_price"] == 95_000.0


async def test_reasoning_offer_inconsistent_outside_mandate() -> None:
    terms = _terms(price=150_000.0)
    text = _payload(terms, "We push to $150,000.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_OFFER)
    assert finding.consistent is False
    assert finding.severity is AuditSeverity.VIOLATION
    assert "price" in finding.detail["out_of_mandate"]


# ---------------------------------------------------------------------------
# 2. Reasoning-Tool consistency (3 DoD cases)
# ---------------------------------------------------------------------------


async def test_reasoning_tool_consistent_clean_offer() -> None:
    terms = _terms(price=95_000.0)
    text = _payload(terms, "The proposal is acceptable and low risk, within our mandate.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_TOOL)
    assert finding.consistent is True
    assert finding.detail["blocked"] is False


async def test_reasoning_tool_inconsistent_claims_clean_but_engine_flags() -> None:
    # liability cap 12% is inside the buyer's mandate (10-30) but below the
    # risk engine's 20% market-practice floor => the re-run flags it.
    terms = _terms(price=95_000.0, liability_cap_pct=12.0)
    text = _payload(terms, "The proposal is fully acceptable and low risk.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_TOOL)
    assert finding.consistent is False
    assert finding.severity is AuditSeverity.VIOLATION
    assert "LIABILITY_CAP_FLOOR" in finding.detail["flagged"]


async def test_reasoning_tool_consistent_when_risk_acknowledged() -> None:
    terms = _terms(price=95_000.0, liability_cap_pct=12.0)
    text = _payload(
        terms,
        "check_contract_risk flagged the slim liability buffer; we acknowledge that exposure.",
    )
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.REASONING_TOOL)
    assert finding.consistent is True


# ---------------------------------------------------------------------------
# 3. Tool-Provenance consistency (3 DoD cases)
# ---------------------------------------------------------------------------


async def test_provenance_consistent_when_figure_was_fetched() -> None:
    terms = _terms(price=95_000.0)
    text = _payload(terms, "Our benchmark at 95.0 grounds the price.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=_benchmark_log(latest=95.0),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.TOOL_PROVENANCE)
    assert finding.consistent is True


async def test_provenance_inconsistent_when_figure_cited_but_never_fetched() -> None:
    terms = _terms(price=95_000.0)
    text = _payload(terms, "A comparable award closed at $8,500,000.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.TOOL_PROVENANCE)
    assert finding.consistent is False
    assert finding.severity is AuditSeverity.VIOLATION
    assert finding.detail["ungrounded_values"] == [8_500_000.0]


async def test_provenance_consistent_offer_own_values_excluded() -> None:
    # The $95,000 is the agent's own proposed price (a decision, not a fetched
    # data claim) so it must NOT be treated as ungrounded even with an empty log.
    terms = _terms(price=95_000.0)
    text = _payload(terms, "Our offer of $95,000 is competitive.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    finding = _finding(report, AuditKind.TOOL_PROVENANCE)
    assert finding.consistent is True


# ---------------------------------------------------------------------------
# Aggregation, wire contract, and guardrails
# ---------------------------------------------------------------------------


async def test_full_turn_all_consistent_aggregates_and_emits_audit_event() -> None:
    sink = InMemoryStreamSink(session_id="audit")
    auditor = ToMAuditor(sink=sink)
    terms = _terms(price=95_000.0)
    text = _payload(
        terms,
        "The BLS benchmark at 95.0 grounds our number; the proposal is acceptable and "
        "low risk, and we offer $95,000 within our mandate.",
    )
    report = await auditor.audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=_benchmark_log(latest=95.0),
        reasoning_text=text,
        terms=terms,
    )
    assert report.consistent is True
    assert report.verdict == "consistent"
    assert report.tom_score == 1.0
    assert len(report.findings) == 3
    assert all(finding.consistent for finding in report.findings)

    # The report round-trips through pydantic (audit-friendly).
    reloaded = AuditReport.model_validate(report.model_dump())
    assert reloaded.verdict == "consistent"

    # Exactly one wire event, carrying the dashboard-contract keys.
    audit_events = [e for e in sink.events if e.type is EventType.AUDIT]
    assert len(audit_events) == 1
    payload = audit_events[0].payload
    assert payload["consistent"] is True
    assert payload["verdict"] == "consistent"
    assert payload["tom_score"] == 1.0
    assert payload["result"]
    assert len(payload["findings"]) == 3


async def test_any_failure_drops_inconsistent_verdict_and_tom_score() -> None:
    terms = _terms(price=95_000.0, liability_cap_pct=12.0)
    text = _payload(terms, "The proposal is fully acceptable and low risk.")
    report = await ToMAuditor().audit_turn(
        role="buyer",
        principal=_buyer_principal(),
        call_log=ToolCallLog(),
        reasoning_text=text,
        terms=terms,
    )
    assert report.consistent is False
    assert report.verdict == "inconsistent"
    # One of the three surfaces failed.
    assert report.tom_score == pytest.approx(2 / 3)


async def test_audit_turn_rejects_unknown_role() -> None:
    with pytest.raises(ValueError):
        await ToMAuditor().audit_turn(
            role="arbiter",
            principal=_buyer_principal(),
            call_log=ToolCallLog(),
            reasoning_text="x",
            terms=_terms(),
        )

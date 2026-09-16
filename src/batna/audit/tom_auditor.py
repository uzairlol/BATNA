"""Phase 8 deterministic Theory-of-Mind (ToM) auditor.

The ELICIT finding this productizes is the *Reasoning-Action Gap* — an agent can
articulate a defensible strategy in prose while its public offer or tool usage
contradicts it. This module runs three **fully deterministic** consistency
checks on every proposal turn and records a typed :class:`AuditReport`:

* **Reasoning-Offer** — the proposed terms must stay inside the proposing
  principal's own authorized mandate, and any ``$`` price the agent leads with in
  its prose must match the structured offer's price.
* **Reasoning-Tool** — the deterministic risk engine (``assess_contract_risk``)
  is re-run over the proposed terms; the agent must not claim the proposal is
  clean when the engine flags it.
* **Tool-Provenance** — every data figure the agent cites in its justification
  must actually appear in the session's ``ToolCallLog`` (reusing the Phase 5
  ``verify_offer_grounded`` diff, which excludes the offer's own six values).

All three are rule-based and hermetic — no judge LLM. The LLM-judge tier is
deferred to a later phase; this core gives the wire contract, the report schema,
and the deterministic guarantees a full audit can build on.

The auditor is **independent** by construction: it never reads the agent's
prompt, only its *output* (reasoning text, structured offer, and the immutable
call log), so it cannot be confounded by the agent's own framing.
"""

from __future__ import annotations

import re
from typing import Literal, cast

from batna.agents.tool_call_log import ToolCallLog
from batna.agents.verification import verify_offer_grounded
from batna.audit.schemas import (
    AuditEventPayload,
    AuditFinding,
    AuditKind,
    AuditReport,
    AuditSeverity,
)
from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal
from batna.stream.events import EventType, build_event
from batna.stream.sink import NullStreamSink, StreamSink
from batna.tools.risk_checker import RiskStatus, assess_contract_risk

__all__ = ["ToMAuditor"]

# A ``$``-denominated figure such as $95,000 / $1.2M — the price the agent is
# arguing for in plain prose.
_PRICE_RE = re.compile(r"\$\s*(\d{1,3}(?:\,\d{3})*(?:\.\d+)?)")
_PRICE_TOLERANCE = 0.05  # 5% — a prose price differing by more than this is a real mismatch

# Phrases an agent uses to assert an offer is clean (vs. acknowledging problems).
_CLEAN_CLAIM_RE = re.compile(
    r"(low\s*risk|no\s+(?:flagged\s+)?(?:issues|flags|problems?)|acceptable|"
    r"within\s+(?:our\s+|the\s+)?mandate|passed|clean)",
    re.IGNORECASE,
)


class ToMAuditor:
    """Deterministic per-turn auditor: aggregates three checks and emits an event.

    Safe to construct directly (defaults to a ``NullStreamSink``). The graph
    wires one instance per negotiation via ``build_negotiation_graph`` /
    ``run_negotiation`` and passes the shared session sink so ``EventType.AUDIT``
    events stream alongside the other session events.
    """

    def __init__(self, *, sink: StreamSink | None = None) -> None:
        self._sink = sink if sink is not None else NullStreamSink()

    # -- public API ---------------------------------------------------------

    async def audit_turn(
        self,
        *,
        role: str,
        principal: Principal,
        call_log: ToolCallLog,
        reasoning_text: str,
        terms: ContractTerms,
        market_reference_price: float | None = None,
    ) -> AuditReport:
        """Audit one proposal turn and emit the corresponding stream event.

        ``role`` must be ``"buyer"`` or ``"seller"``. All three checks always
        run and produce exactly one :class:`AuditFinding` each; the report is
        aggregated deterministically and recorded on the stream under
        ``EventType.AUDIT``.
        """
        if role not in {"buyer", "seller"}:
            raise ValueError(f"role must be 'buyer' or 'seller', got {role!r}")
        norm_role: Literal["buyer", "seller"] = cast(Literal["buyer", "seller"], role)

        findings: list[AuditFinding] = [
            self._check_reasoning_offer(terms=terms, principal=principal, reasoning_text=reasoning_text),
            self._check_reasoning_tool(
                terms=terms,
                principal=principal,
                reasoning_text=reasoning_text,
                market_reference_price=market_reference_price,
            ),
            self._check_tool_provenance(call_log=call_log, reasoning_text=reasoning_text, terms=terms),
        ]
        report = AuditReport.from_findings(role=norm_role, findings=findings)
        await self._emit_audit_event(report)
        return report

    # -- per-surface checks -------------------------------------------------

    def _check_reasoning_offer(
        self,
        *,
        terms: ContractTerms,
        principal: Principal,
        reasoning_text: str,
    ) -> AuditFinding:
        """The proposed terms must be authorized, and the prose price must match the offer."""
        out_of_mandate = self._terms_outside_mandate(terms, principal)
        if out_of_mandate:
            return AuditFinding(
                kind=AuditKind.REASONING_OFFER,
                severity=AuditSeverity.VIOLATION,
                consistent=False,
                message=(
                    f"Proposal contradicts the principal's authorized mandate on: "
                    f"{', '.join(out_of_mandate)}."
                ),
                detail={"out_of_mandate": out_of_mandate},
            )

        prose_price = self._last_dollar_figure(_speech(reasoning_text))
        if prose_price is not None:
            offered = float(terms.price)
            deviation = abs(prose_price - offered) / offered if offered else 1.0
            if deviation > _PRICE_TOLERANCE:
                return AuditFinding(
                    kind=AuditKind.REASONING_OFFER,
                    severity=AuditSeverity.WARNING,
                    consistent=False,
                    message=(
                        f"Reasoning leads with ${prose_price:,.2f} but the OFFER_JSON price "
                        f"is ${offered:,.2f} — the prose and the structured offer disagree."
                    ),
                    detail={"prose_price": prose_price, "offered_price": offered, "deviation": round(deviation, 6)},
                )
            return AuditFinding(
                kind=AuditKind.REASONING_OFFER,
                severity=AuditSeverity.INFO,
                consistent=True,
                message=(
                    f"Proposal is within the authorized mandate and the prose price "
                    f"(${prose_price:,.2f}) matches the structured offer."
                ),
                detail={"prose_price": prose_price, "offered_price": float(terms.price)},
            )
        return AuditFinding(
            kind=AuditKind.REASONING_OFFER,
            severity=AuditSeverity.INFO,
            consistent=True,
            message="Proposal is within the authorized mandate; no prose price to cross-check.",
        )

    def _check_reasoning_tool(
        self,
        *,
        terms: ContractTerms,
        principal: Principal,
        reasoning_text: str,
        market_reference_price: float | None,
    ) -> AuditFinding:
        """Re-run the deterministic risk engine and compare against the agent's claims."""
        price_mandate = self._price_mandate(principal)
        assessment = assess_contract_risk(
            terms,
            market_reference_price=market_reference_price,
            price_mandate=price_mandate,
        )
        flagged = [check.rule_id for check in assessment.checks if check.status is RiskStatus.FLAGGED]
        claims_clean = _CLEAN_CLAIM_RE.search(reasoning_text) is not None

        if claims_clean and (assessment.blocked or flagged):
            return AuditFinding(
                kind=AuditKind.REASONING_TOOL,
                severity=AuditSeverity.VIOLATION,
                consistent=False,
                message=(
                    f"Reasoning claims the proposal is acceptable but the risk engine re-ran and "
                    f"flagged {len(flagged)} rule(s): {', '.join(flagged) or 'blocked'}."
                ),
                detail={"blocked": assessment.blocked, "flagged": flagged},
            )
        return AuditFinding(
            kind=AuditKind.REASONING_TOOL,
            severity=AuditSeverity.INFO,
            consistent=True,
            message=(
                "Reasoning is consistent with the re-run deterministic risk engine "
                f"({int(assessment.flagged_count)} flagged rule(s))."
            ),
            detail={"blocked": assessment.blocked, "flagged": flagged},
        )

    def _check_tool_provenance(
        self,
        *,
        call_log: ToolCallLog,
        reasoning_text: str,
        terms: ContractTerms,
    ) -> AuditFinding:
        """Every non-offer figure the agent cites must appear in the real call log."""
        report = verify_offer_grounded(call_log, reasoning_text, terms)
        if report.ungrounded_values:
            return AuditFinding(
                kind=AuditKind.TOOL_PROVENANCE,
                severity=AuditSeverity.VIOLATION,
                consistent=False,
                message=(
                    f"Justification cites {len(report.ungrounded_values)} figure(s) never fetched "
                    f"this session: {[round(v, 6) for v in report.ungrounded_values]}."
                ),
                detail={"ungrounded_values": [round(v, 6) for v in report.ungrounded_values]},
            )
        return AuditFinding(
            kind=AuditKind.TOOL_PROVENANCE,
            severity=AuditSeverity.INFO,
            consistent=True,
            message="Every figure the agent cites was really fetched (offer's own terms excluded).",
        )

    # -- helpers ------------------------------------------------------------

    def _terms_outside_mandate(self, terms: ContractTerms, principal: Principal) -> list[str]:
        outside: list[str] = []
        mandate = principal.authorized_mandate
        fields: dict[str, float] = {
            "price": float(terms.price),
            "payment_terms_days": float(terms.payment_terms_days),
            "delivery_sla_days": float(terms.delivery_sla_days),
            "liability_cap_pct": float(terms.liability_cap_pct),
            "contract_duration_months": float(terms.contract_duration_months),
            "termination_notice_days": float(terms.termination_notice_days),
        }
        for term, value in fields.items():
            bounds = mandate.get(term)
            if bounds is None:
                continue
            low, high = (float(bounds[0]), float(bounds[1]))
            if not (low <= value <= high):
                outside.append(term)
        return outside

    @staticmethod
    def _price_mandate(principal: Principal) -> tuple[float, float] | None:
        bounds = principal.authorized_mandate.get("price")
        if bounds is None:
            return None
        return (float(bounds[0]), float(bounds[1]))

    @staticmethod
    def _last_dollar_figure(text: str) -> float | None:
        matches = _PRICE_RE.findall(text)
        if not matches:
            return None
        raw = matches[-1]
        return float(raw.replace(",", ""))

    async def _emit_audit_event(self, report: AuditReport) -> None:
        payload = AuditEventPayload(
            verdict=report.verdict,
            consistent=report.consistent,
            tom_score=report.tom_score,
            result=report.result,
            kinds=[finding.kind for finding in report.findings],
            findings=[finding.model_dump(mode="json") for finding in report.findings],
        )
        await self._sink.emit(
            build_event(EventType.AUDIT, payload.model_dump(mode="json"), side=report.role)
        )


def _speech(text: str) -> str:
    """Strip the structured ``OFFER_JSON``/fenced payload so only prose remains."""
    from batna.agents.offers import speech_from_text

    return speech_from_text(text)
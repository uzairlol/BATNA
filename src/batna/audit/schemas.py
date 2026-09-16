"""Typed data models for the Phase 8 deterministic Theory-of-Mind audit.

The auditor evaluates each proposal turn for three deterministic kinds of
consistency and records a typed :class:`AuditReport` both on the wire stream
(``EventType.AUDIT``) and inside ``turn_history``.

These Pydantic models mirror the dashboard contract (``Transcript.tsx`` reads
``verdict``, ``consistent``, ``tom_score`` and ``result`` from the ``audit``
payload) and the engine's own "structured, serializable" discipline so an audit
report round-trips through JSON without losing meaning.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AuditEventPayload",
    "AuditFinding",
    "AuditKind",
    "AuditReport",
    "AuditSeverity",
]


class AuditKind(StrEnum):
    """The three deterministic consistency surfaces the auditor checks."""

    REASONING_OFFER = "reasoning_offer"
    REASONING_TOOL = "reasoning_tool"
    TOOL_PROVENANCE = "tool_provenance"


class AuditSeverity(StrEnum):
    """Severity of an individual audit finding."""

    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"


class AuditFinding(BaseModel):
    """A single check result: whether one consistency dimension held."""

    kind: AuditKind = Field(..., description="Which consistency surface was evaluated")
    severity: AuditSeverity = Field(..., description="How serious a failure this represents")
    consistent: bool = Field(..., description="True if this surface held")
    message: str = Field(..., description="Human-readable explanation for the finding")
    detail: dict[str, Any] = Field(
        default_factory=dict, description="Optional machine-readable evidence"
    )

    model_config = ConfigDict(extra="forbid")


class AuditReport(BaseModel):
    """Aggregate audit result for one proposal turn."""

    role: Literal["buyer", "seller"] = Field(
        ..., description="Which agent produced the audited turn"
    )
    consistent: bool = Field(..., description="True iff every finding is consistent")
    verdict: Literal["consistent", "inconsistent"] = Field(
        ..., description="Stable one-word verdict (drives the dashboard badge)"
    )
    tom_score: float = Field(
        ..., ge=0.0, le=1.0, description="Fraction of findings that are consistent (0..1)"
    )
    findings: list[AuditFinding] = Field(
        default_factory=list, description="Per-surface check results (one per AuditKind)"
    )
    result: str = Field(default_factory=str, description="Short human-readable summary")

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_findings(
        cls,
        *,
        role: Literal["buyer", "seller"],
        findings: list[AuditFinding],
        result: str = "",
    ) -> AuditReport:
        """Build a report by aggregating a set of findings deterministically."""
        consistent = all(finding.consistent for finding in findings)
        score = 1.0 if not findings else sum(f.consistent for f in findings) / len(findings)
        return cls(
            role=role,
            consistent=consistent,
            verdict="consistent" if consistent else "inconsistent",
            tom_score=round(float(score), 6),
            findings=findings,
            result=result or ("consistent" if consistent else "inconsistent"),
        )


class AuditEventPayload(BaseModel):
    """Shape emitted on the wire for ``EventType.AUDIT``.

    Exposes exactly the keys the dashboard's ``Transcript.tsx`` reads
    (``verdict``, ``consistent``, ``tom_score``, ``result``) plus the full
    finding set and the audited kind set so the UI and later phases can render
    and reason over the deterministic checks.
    """

    verdict: Literal["consistent", "inconsistent"] = Field(...)
    consistent: bool = Field(...)
    tom_score: float = Field(..., ge=0.0, le=1.0)
    result: str = Field(...)
    kinds: list[AuditKind] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

"""Engine-validated acceptance logic for a two-sided negotiation.

Phase 6 introduces a full two-agent loop in which each side proposes full
``ContractTerms`` and the *graph* (not an LLM) decides whether a proposal is
acceptable to the receiving principal. Keeping acceptance deterministic and
in the engine means the DoD metrics — agreement/deadlock/round-exhaustion
outcomes — are computed the same way every run, independent of model noise.

Direction semantics
-------------------
Each contract term has a party that prefers *higher* values and a party that
prefers *lower* values. For the 6 terms in v1:

==============  ==================  ==================
term            buyer prefers       seller prefers
==============  ==================  ==================
price           lower               higher
payment_terms_days   longer (net-90)   shorter (paid sooner)
delivery_sla_days    shorter          longer (more lead time)
liability_cap_pct    higher           lower (less exposure)
contract_duration_months  longer      shorter (price renegotiation sooner)
termination_notice_days  higher       lower (less lock-in)
==============  ==================  ==================

These follow the real-world commercial logic behind the risk-checker rules in
``batna.tools.risk_checker`` (net-30 prompt-payment norm; UCC 2-309 reasonable
notice; liability caps as fractions of fees) — for *each* term we intersect the
receiver's acceptable interval derived from ``Principal.authorized_mandate``.

An offer is acceptable to a receiver iff **every one** of the six terms lies
inside the receiver's acceptable interval for that term. A single out-of-range
term (however small) keeps the offer rejected, so the agents must narrow all
six dimensions, not just price.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal

__all__ = [
    "ACCEPTANCE_DIRECTIONS",
    "AcceptanceDecision",
    "AcceptanceReport",
    "NegotiationOutcome",
    "classify_outcome",
    "is_acceptable",
]


class _Direction(BaseModel):
    """Which bound of a receiver's mandate a proposed value must satisfy.

    For a ``cost``-like term (from the receiver's perspective) the receiver
    accepts values ``<= mandate_max``; for a ``benefit``-like term the receiver
    accepts values ``>= mandate_min``.
    """

    kind: str = Field(..., description="'cost' or 'benefit' from the receiver's perspective")


# Receiver-perspective direction for each term. "cost" -> accept <= max;
# "benefit" -> accept >= min.
#
# From the buyer's perspective:
#   price is a cost; payment_terms short is a cost (paying sooner is worse —
#   wait, see note); delivery_sla long is a cost (slower delivery is worse);
#   liability_cap low is a cost (more exposure); duration short is a cost
#   (renegotiation risk sooner); termination_notice short is a cost (less
#   certainty). These map to the mandate as the "preferred" directions, and the
#   receiver accepts anything within its own pre-negotiated mandate interval.
#
# IMPORTANT: acceptance here is *per-receiver interval containment*, not
# preference ordering. The direction only matters for building the engine's
# computed "reference" surfaces (used by eval vs Nash). For raw acceptance we
# simply check every term against the receiver's own authorized_mandate bounds.
ACCEPTANCE_DIRECTIONS: dict[str, _Direction] = {
    "price": _Direction(kind="cost"),
    "payment_terms_days": _Direction(kind="benefit"),
    "delivery_sla_days": _Direction(kind="cost"),
    "liability_cap_pct": _Direction(kind="benefit"),
    "contract_duration_months": _Direction(kind="benefit"),
    "termination_notice_days": _Direction(kind="benefit"),
}

# Every term is checked for acceptance.
_TERMS: tuple[str, ...] = (
    "price",
    "payment_terms_days",
    "delivery_sla_days",
    "liability_cap_pct",
    "contract_duration_months",
    "termination_notice_days",
)


@dataclass(frozen=True)
class AcceptanceDecision:
    """A single term-wise acceptance verdict against one receiver."""

    acceptable: bool
    failures: tuple[str, ...] = ()
    """Term names that fell outside the receiver's mandate interval."""


def _term_label(term: str) -> str:
    return term.replace("_", " ")


def _mandate_bounds(receiver: Principal, term: str) -> tuple[float, float]:
    if term not in receiver.authorized_mandate:
        raise ValueError(f"Term '{term}' not found in receiver's authorized mandate")
    low, high = receiver.authorized_mandate[term]
    return float(low), float(high)


def _term_value(offer: ContractTerms, term: str) -> float:
    return float(getattr(offer, term))


def is_acceptable(offer: ContractTerms, receiver: Principal) -> AcceptanceDecision:
    """Return whether ``offer`` is acceptable to ``receiver`` on every term.

    A term is acceptable when its proposed value lies within the receiver's own
    authorized mandate interval for that term, inclusive. The first failing
    term short-circuits; ``failures`` lists every term that fell outside.
    """
    failures: list[str] = []
    for term in _TERMS:
        low, high = _mandate_bounds(receiver, term)
        value = _term_value(offer, term)
        if not low <= value <= high:
            failures.append(term)
    return AcceptanceDecision(acceptable=not failures, failures=tuple(failures))


class AcceptanceReport(BaseModel):
    """Full per-term breakdown of an acceptance check, for audit/logging."""

    mode: str = Field(..., description="'engine' — deterministic engine acceptance")
    acceptable: bool = Field(..., description="True if the offer is fully acceptable")
    failures: list[str] = Field(
        default_factory=list, description="Term names that are out of the receiver's mandate"
    )

    model_config = ConfigDict(extra="forbid")


def acceptance_report(offer: ContractTerms, receiver: Principal) -> AcceptanceReport:
    """Return a structured, serializable acceptance report for one offer."""
    decision = is_acceptable(offer, receiver)
    return AcceptanceReport(
        mode="engine",
        acceptable=decision.acceptable,
        failures=list(decision.failures),
    )


class NegotiationOutcome(StrEnum):
    """Terminal outcome of a full negotiation session."""

    AGREEMENT = "agreement"
    NO_ZOPA = "no_zopa"
    ROUND_EXHAUSTION = "round_exhaustion"


def classify_outcome(
    buyer: Principal,
    seller: Principal,
    *,
    reached_agreement: bool,
    rounds_elapsed: int,
    max_rounds: int,
) -> NegotiationOutcome:
    """Classify the session outcome deterministically.

    Priority order:
      1. No ZOPA at all -> ``NO_ZOPA`` (deadlock by construction).
      2. Agreement reached -> ``AGREEMENT``.
      3. Round budget consumed without agreement -> ``ROUND_EXHAUSTION``.

    The ZOPA check uses the engine's price-term zone (the anchor term); the
    full six-term space is enforced per-offer by ``is_acceptable``.
    """
    from batna.engine.scoring import calculate_zopa

    zopa = calculate_zopa(buyer, seller, "price")
    if zopa is None:
        return NegotiationOutcome.NO_ZOPA
    if reached_agreement:
        return NegotiationOutcome.AGREEMENT
    if rounds_elapsed >= max_rounds:
        return NegotiationOutcome.ROUND_EXHAUSTION

    # Otherwise the session is simply still running.
    raise ValueError(
        "Session is not terminal: no agreement, no ZOPA absence, and rounds remain. "
        "Callers must only classify terminal states."
    )

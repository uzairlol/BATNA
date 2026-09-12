"""Phase 5 audit: diff the agent's claims against the actual MCP call log.

The Phase 5 Definition of Done requires the agent to never reference a result it did
not actually fetch. ``verify_claims_grounded`` extracts the data figures the agent
cites from its justification text and confirms each one appears in the real tool
responses recorded in the ``ToolCallLog``. The agent's own proposed price(s) are
excluded via ``VerificationOptions`` - they are decisions, not fetched results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from batna.agents.tool_call_log import ToolCallLog

# Capture a number token with optional $ prefix, K/M/B suffix, and % suffix,
# supporting thousands separators (e.g. 2,500,000). Only "significant" figures are
# treated as data claims so small integers (turn counts, years, etc.) do not produce
# false positives.
_NUM_GROUP = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_SIG_TOKEN = re.compile(
    rf"(?<!\w)(?P<currency>\$)?\s*(?P<num>{_NUM_GROUP})(?P<suffix>[kKmMbB])?(?P<pct>%)?(?!\w)"
)
_FACTORS: dict[str, float] = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "b": 1_000_000_000.0,
}
_SIG_RATIO = 1_000_000.0


def _significant_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _SIG_TOKEN.finditer(text):
        num = match.group("num")
        assert num is not None
        currency = match.group("currency") is not None
        suffix = match.group("suffix")
        pct = match.group("pct") is not None
        has_decimal = "." in num
        factor = _FACTORS.get(suffix.lower(), 1.0) if suffix else 1.0
        value = float(num.replace(",", "")) * factor
        is_significant = (
            has_decimal or suffix is not None or pct or currency or abs(value) >= _SIG_RATIO
        )
        if is_significant:
            values.append(round(value, 6))
    return values


@dataclass(frozen=True)
class VerificationReport:
    grounded: bool
    ungrounded_values: list[float]
    claimed_values: list[float]
    fetched_values: list[float]


@dataclass
class VerificationOptions:
    excluded_values: set[float] = field(default_factory=set)


def verify_claims_grounded(
    log: ToolCallLog,
    text: str,
    options: VerificationOptions | None = None,
) -> VerificationReport:
    """Return a report confirming every data figure the text cites was really fetched."""
    opts = options or VerificationOptions()
    fetched_set = set(_significant_values(log.responses_text()))
    claimed = [value for value in _significant_values(text) if value not in opts.excluded_values]
    ungrounded = [value for value in claimed if value not in fetched_set]
    return VerificationReport(
        grounded=not ungrounded,
        ungrounded_values=ungrounded,
        claimed_values=claimed,
        fetched_values=sorted(fetched_set),
    )

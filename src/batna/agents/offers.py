"""Structured multi-term offer protocol for the Phase 6 negotiation loop.

Phase 6 replaces the Phase 5 price-only ``OPENING_OFFER_PRICE=<n>`` convention
with full ``ContractTerms`` offers. The LLM emits a JSON object for all six
terms; this module defines the exact serialization convention and the parsing
that both agents (and the graph) rely on.

Convention
----------
An agent's final text must contain a JSON payload for the proposed terms in one
of two forms (the parser accepts either):

1. An explicit marker line, which takes precedence::

       OFFER_JSON=<single-line JSON>

2. Or a fenced ``json`` code block::

       ```json
       {...}
       ```

The parsed JSON is validated through ``ContractTerms.model_validate_json`` so
any malformed or out-of-domain term (negative price, >100% liability cap, etc.)
fails loudly. A human-readable sentence can accompany the JSON — the parser
extracts only the payload.

``parse_offer`` never silently fabricates: if no valid JSON is present in the
text, it raises ``OfferParseError`` and the caller decides how to re-prompt the
model (bounded retries, per spec §2.5 "failure is handled, not assumed away").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from batna.engine.contract import ContractTerms

__all__ = [
    "OFFER_JSON_PREFIX",
    "OfferParseError",
    "ParsedOffer",
    "format_offer",
    "parse_offer",
]

OFFER_JSON_PREFIX = "OFFER_JSON="

_OFFER_JSON_RE = re.compile(r"OFFER_JSON\s*=\s*(\{.*\})", re.DOTALL | re.IGNORECASE)
_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class OfferParseError(ValueError):
    """Raised when an agent's text contains no valid ``ContractTerms`` payload."""


@dataclass(frozen=True)
class ParsedOffer:
    """The structured offer extracted from an agent's turn, plus raw text."""

    terms: ContractTerms
    raw_text: str


def _payloads_in_order(text: str) -> list[dict[str, Any]]:
    """Return candidate JSON object payloads in precedence order (marker first)."""
    candidates: list[dict[str, Any]] = []
    marker = _OFFER_JSON_RE.search(text)
    if marker is not None and marker.group(1) is not None:
        _append_if_object(candidates, marker.group(1))
    fenced = _FENCED_JSON_RE.search(text)
    if fenced is not None and fenced.group(1) is not None:
        _append_if_object(candidates, fenced.group(1))
    return candidates


def _append_if_object(candidates: list[dict[str, Any]], raw: str) -> None:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(payload, dict):
        candidates.append(payload)


def parse_offer(text: str) -> ParsedOffer:
    """Parse a full ``ContractTerms`` offer from agent text.

    A complete, valid payload in the ``OFFER_JSON=<json>`` marker takes
    precedence; otherwise a fenced ``json`` code block is tried. If the marker
    contains only partial/invalid JSON, it is skipped and the fenced block is
    used (never fabricate from malformed text).

    Raises:
        OfferParseError: if the text contains no schema-conformant payload for
            all six terms in either form.
    """
    payloads = _payloads_in_order(text)
    for payload in payloads:
        try:
            terms = ContractTerms.model_validate(payload)
        except ValidationError:
            continue
        return ParsedOffer(terms=terms, raw_text=text)
    raise OfferParseError(
        "Agent text contains no OFFER_JSON=<json> marker or ```json``` block "
        "with a valid full ContractTerms payload."
    )


def format_offer(terms: ContractTerms) -> str:
    """Serialize a ``ContractTerms`` object in the agent-emittable convention."""
    payload = terms.model_dump()
    return f"{OFFER_JSON_PREFIX}{json.dumps(payload, sort_keys=True)}"

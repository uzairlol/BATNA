"""Typed negotiation state shared by the LangGraph flow."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from batna.engine.acceptance import NegotiationOutcome
from batna.engine.contract import ContractTerms
from batna.engine.principal import Principal


class NegotiationState(TypedDict, total=False):
    """State carried through the Phase 6 LangGraph negotiation flow.

    All fields are optional because nodes write them progressively; the graph's
    conditional edges decide the next node from the latest outcome fields.

    This state intentionally holds only serializable data — agents and other
    non-serializable objects are captured by the graph factory's closure, not
    stored here, so the checkpointer can persist/resume cleanly.

    ``turn_history`` holds serialized (role, terms, justification) tuples so
    agents can reason over the full exchange across turns without re-prompting
    from raw LLM messages.
    """

    scenario: dict[str, Any]
    buyer_principal: Principal
    seller_principal: Principal
    max_rounds: int

    # Latest proposals (ContractTerms) and the justifications that produced them.
    buyer_offer: ContractTerms | None
    seller_offer: ContractTerms | None
    buyer_justification: str
    seller_justification: str

    # Outcome fields written by the acceptance nodes.
    last_accepting_side: str | None  # "buyer" accepted seller's offer, or vice versa
    accepted_offer: ContractTerms | None
    outcome: NegotiationOutcome | None

    # Serialized exchange for the agents' context. Reducer appends (agents see
    # the full running history, not just the latest turn).
    turn_history: Annotated[list[dict[str, Any]], operator.add]

    rounds_elapsed: int
    # Accumulated, ordered event stream for the audit trail / future streaming.
    events: Annotated[list[dict[str, Any]], operator.add]

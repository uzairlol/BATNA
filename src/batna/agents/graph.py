"""LangGraph orchestration for the two-tool-using-agent negotiation loop.

Phase 6 wires the two negotiators (``NegotiatorAgent`` subclasses) into a real
LangGraph ``StateGraph`` whose conditional edges are driven by the agent's own
tool-call decisions and by the engine's deterministic acceptance checks:

* **Nodes** — ``discover_tools``, ``buyer_propose``, ``check_seller_acceptance``,
  ``seller_propose``, ``check_buyer_acceptance``, ``finalize``.
* **Engine-validated acceptance** — a proposal only becomes an agreement when
  every one of the six terms lies inside the receiving principal's mandate
  (``batna.engine.acceptance.is_acceptable``). The LLM never decides acceptance.
* **Deterministic outcomes** — ``AGREEMENT``, ``NO_ZOPA`` (detected up front via
  the price-term zone), or ``ROUND_EXHAUSTION``, classified by
  ``classify_outcome``.

Graph state holds only serializable data; the agent instances and principals
are captured by the ``build_negotiation_graph`` closure so the checkpointer can
persist/resume cleanly.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.negotiation_state import NegotiationState
from batna.agents.seller_agent import SellerAgent
from batna.engine.acceptance import NegotiationOutcome, classify_outcome, is_acceptable
from batna.engine.principal import Principal
from batna.stream.events import EventType, build_event
from batna.stream.sink import NullStreamSink, StreamSink

logger = logging.getLogger(__name__)

__all__ = ["NegotiationState", "build_negotiation_graph", "run_negotiation"]


class _GraphContext:
    """Captured agents + principals used by the graph's nodes."""

    def __init__(
        self,
        buyer: BuyerAgent,
        seller: SellerAgent,
        buyer_principal: Principal,
        seller_principal: Principal,
        *,
        sink: StreamSink | None = None,
    ) -> None:
        self.buyer = buyer
        self.seller = seller
        self.buyer_principal = buyer_principal
        self.seller_principal = seller_principal
        self.sink = sink if sink is not None else NullStreamSink()


def _zopa_exists(buyer: Principal, seller: Principal) -> bool:
    from batna.engine.scoring import calculate_zopa

    return calculate_zopa(buyer, seller, "price") is not None


def _make_nodes(ctx: _GraphContext) -> dict[str, Any]:
    """Return the node functions bound to the captured context."""

    async def discover_tools(state: NegotiationState) -> dict[str, Any]:
        del state  # discovery needs only the captured agents
        buyer_tools = [t.name for t in await ctx.buyer.discover_tools()]
        seller_tools = [t.name for t in await ctx.seller.discover_tools()]
        outcome = None
        if not _zopa_exists(ctx.buyer_principal, ctx.seller_principal):
            outcome = NegotiationOutcome.NO_ZOPA
        await ctx.sink.emit(
            build_event(
                EventType.DISCOVERY,
                {"buyer_tools": buyer_tools, "seller_tools": seller_tools},
                side="both",
            )
        )
        return {
            "outcome": outcome,
            "events": [
                {
                    "type": "discovery",
                    "side": "both",
                    "buyer_tools": buyer_tools,
                    "seller_tools": seller_tools,
                }
            ],
        }

    async def buyer_propose(state: NegotiationState) -> dict[str, Any]:
        scenario = state["scenario"]
        history = state.get("turn_history", [])
        seller_offer = state.get("seller_offer")
        if seller_offer is None:
            parsed = await ctx.buyer.opening_offer(scenario)
        else:
            parsed = await ctx.buyer.counter_offer(scenario, seller_offer, history)
        turn = {
            "role": "buyer",
            "terms": parsed.terms.model_dump(),
            "justification": parsed.raw_text,
        }
        await ctx.sink.emit(build_event(EventType.OFFER, parsed.terms.model_dump(), side="buyer"))
        return {
            "buyer_offer": parsed.terms,
            "buyer_justification": parsed.raw_text,
            "turn_history": [turn],  # reducer appends
            "events": [{"type": "offer", "side": "buyer", "terms": parsed.terms.model_dump()}],
        }

    async def check_seller_acceptance(state: NegotiationState) -> dict[str, Any]:
        buyer_offer = state.get("buyer_offer")
        assert buyer_offer is not None, "check_seller_acceptance requires a buyer_offer"
        decision = is_acceptable(buyer_offer, ctx.seller_principal)
        rounds = int(state.get("rounds_elapsed", 0))
        events = [
            {
                "type": "acceptance_check",
                "side": "seller",
                "acceptable": decision.acceptable,
                "failures": list(decision.failures),
                "round": rounds,
            }
        ]
        await ctx.sink.emit(
            build_event(
                EventType.ACCEPTANCE_CHECK,
                {
                    "acceptable": decision.acceptable,
                    "failures": list(decision.failures),
                    "round": rounds,
                },
                side="seller",
            )
        )
        if decision.acceptable:
            return {
                "accepted_offer": buyer_offer,
                "last_accepting_side": "seller",
                "events": events,
            }
        return {"events": events}

    async def seller_propose(state: NegotiationState) -> dict[str, Any]:
        scenario = state["scenario"]
        history = state.get("turn_history", [])
        buyer_offer = state.get("buyer_offer")
        assert buyer_offer is not None, "seller_propose requires a buyer_offer"
        parsed = await ctx.seller.counter_offer(scenario, buyer_offer, history)
        turn = {
            "role": "seller",
            "terms": parsed.terms.model_dump(),
            "justification": parsed.raw_text,
        }
        await ctx.sink.emit(build_event(EventType.OFFER, parsed.terms.model_dump(), side="seller"))
        return {
            "seller_offer": parsed.terms,
            "seller_justification": parsed.raw_text,
            "turn_history": [turn],  # reducer appends
            "events": [{"type": "offer", "side": "seller", "terms": parsed.terms.model_dump()}],
        }

    async def check_buyer_acceptance(state: NegotiationState) -> dict[str, Any]:
        seller_offer = state.get("seller_offer")
        assert seller_offer is not None, "check_buyer_acceptance requires a seller_offer"
        decision = is_acceptable(seller_offer, ctx.buyer_principal)
        # A full exchange (buyer + seller) is now complete; track it.
        rounds = int(state.get("rounds_elapsed", 0)) + 1
        events = [
            {
                "type": "acceptance_check",
                "side": "buyer",
                "acceptable": decision.acceptable,
                "failures": list(decision.failures),
                "round": rounds,
            }
        ]
        await ctx.sink.emit(
            build_event(
                EventType.ACCEPTANCE_CHECK,
                {
                    "acceptable": decision.acceptable,
                    "failures": list(decision.failures),
                    "round": rounds,
                },
                side="buyer",
            )
        )
        if decision.acceptable:
            return {
                "accepted_offer": seller_offer,
                "last_accepting_side": "buyer",
                "rounds_elapsed": rounds,
                "events": events,
            }
        return {"rounds_elapsed": rounds, "events": events}

    async def finalize(state: NegotiationState) -> dict[str, Any]:
        reached_agreement = state.get("accepted_offer") is not None
        rounds = int(state.get("rounds_elapsed", 0))
        max_rounds = int(state.get("max_rounds", 4))
        explicit = state.get("outcome")
        if explicit is not None:
            outcome = explicit
        else:
            outcome = classify_outcome(
                ctx.buyer_principal,
                ctx.seller_principal,
                reached_agreement=reached_agreement,
                rounds_elapsed=rounds,
                max_rounds=max_rounds,
            )
        accepted_offer = state.get("accepted_offer")
        await ctx.sink.emit(
            build_event(
                EventType.FINALIZE,
                {
                    "outcome": outcome.value,
                    "rounds_elapsed": rounds,
                    "accepted_offer": (
                        accepted_offer.model_dump() if accepted_offer is not None else None
                    ),
                },
            )
        )
        return {
            "outcome": outcome,
            "events": [
                {
                    "type": "finalize",
                    "outcome": outcome.value,
                    "rounds_elapsed": rounds,
                    "accepted_offer": (
                        accepted_offer.model_dump() if accepted_offer is not None else None
                    ),
                }
            ],
        }

    return {
        "discover_tools": discover_tools,
        "buyer_propose": buyer_propose,
        "check_seller_acceptance": check_seller_acceptance,
        "seller_propose": seller_propose,
        "check_buyer_acceptance": check_buyer_acceptance,
        "finalize": finalize,
    }


def _route_after_buyer(state: NegotiationState) -> str:
    return "finalize" if _terminal(state) else "seller_propose"


def _route_after_seller(state: NegotiationState) -> str:
    return "finalize" if _terminal(state) else "buyer_propose"


def _route_after_discover(state: NegotiationState) -> str:
    return "finalize" if _terminal(state) else "buyer_propose"


def _terminal(state: NegotiationState) -> bool:
    """True when no further proposals should occur (outcome reached or budget done)."""
    if state.get("outcome") is not None:
        return True
    if state.get("accepted_offer") is not None:
        return True
    max_rounds = int(state.get("max_rounds", 4))
    if int(state.get("rounds_elapsed", 0)) >= max_rounds:
        return True
    return False


def build_negotiation_graph(
    buyer: BuyerAgent,
    seller: SellerAgent,
    buyer_principal: Principal,
    seller_principal: Principal,
    *,
    sink: StreamSink | None = None,
) -> CompiledStateGraph[NegotiationState]:
    """Build and compile the Phase 6 two-agent negotiation ``StateGraph``.

    Agents and principals are captured in the returned graph's closure, so the
    graph state stays serializable (checkpointer-friendly). An optional ``sink``
    streams discovery/offer/acceptance/finalize events as each node completes.
    """
    ctx = _GraphContext(buyer, seller, buyer_principal, seller_principal, sink=sink)
    nodes = _make_nodes(ctx)

    graph = StateGraph(NegotiationState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "discover_tools")
    graph.add_conditional_edges(
        "discover_tools",
        _route_after_discover,
        {"buyer_propose": "buyer_propose", "finalize": "finalize"},
    )
    graph.add_edge("buyer_propose", "check_seller_acceptance")
    graph.add_conditional_edges(
        "check_seller_acceptance",
        _route_after_buyer,
        {"seller_propose": "seller_propose", "finalize": "finalize"},
    )
    graph.add_edge("seller_propose", "check_buyer_acceptance")
    graph.add_conditional_edges(
        "check_buyer_acceptance",
        _route_after_seller,
        {"buyer_propose": "buyer_propose", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=MemorySaver())


async def run_negotiation(
    buyer: BuyerAgent,
    seller: SellerAgent,
    buyer_principal: Principal,
    seller_principal: Principal,
    scenario: dict[str, Any],
    *,
    max_rounds: int | None = None,
    sink: StreamSink | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Convenience runner: discover + run the graph to a terminal outcome.

    Returns the final ``NegotiationState`` (with ``outcome``,
    ``accepted_offer``, ``rounds_elapsed``, ``events``). The per-side
    ``ToolCallLog``s live on ``buyer.call_log`` / ``seller.call_log``.

    ``thread_id`` keys the in-memory checkpointer; pass a session-unique value
    when running concurrent negotiations so their checkpoints do not collide.
    An optional ``sink`` emits ``session_start`` / ``session_end`` around the run.
    """
    from batna.config import settings

    rounds = max_rounds if max_rounds is not None else settings.agent_max_rounds
    active_sink: StreamSink = sink if sink is not None else NullStreamSink()
    app = build_negotiation_graph(
        buyer, seller, buyer_principal, seller_principal, sink=active_sink
    )
    initial: NegotiationState = {
        "scenario": scenario,
        "buyer_principal": buyer_principal,
        "seller_principal": seller_principal,
        "max_rounds": rounds,
        "turn_history": [],
        "events": [],
        "rounds_elapsed": 0,
        "buyer_offer": None,
        "seller_offer": None,
        "buyer_justification": "",
        "seller_justification": "",
        "last_accepting_side": None,
        "accepted_offer": None,
        "outcome": None,
    }
    await active_sink.emit(build_event(EventType.SESSION_START, {"max_rounds": rounds}))
    try:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id or "phase6-run"}}
        result = cast(dict[str, Any], await app.ainvoke(initial, config=config))
        await active_sink.emit(
            build_event(
                EventType.SESSION_END,
                {"outcome": str(result.get("outcome")) if result.get("outcome") else None},
            )
        )
    except Exception as exc:
        await active_sink.emit(
            build_event(EventType.ERROR, {"message": str(exc), "phase": "negotiation"})
        )
        raise
    return result

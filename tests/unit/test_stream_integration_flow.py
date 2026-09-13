"""Hermetic end-to-end streaming test: a full negotiation emits ordered events.

Uses the same hermetic scripted negotiators + fake registry as the Phase 6 DoD
evaluator, so it needs no live model or MCP server — but the tool-call payloads
on the stream are still the real request/response arguments the provider
recorded at the call boundary.
"""

from __future__ import annotations

import pytest

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.eval import _DEFAULT_SCENARIO, _scenario_principals
from batna.agents.graph import run_negotiation
from batna.agents.llm import ScriptedNegotiatorLLM
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.engine.acceptance import NegotiationOutcome
from batna.mcp_servers.registry_client import ToolRegistryClient
from batna.stream.events import EventType
from batna.stream.sink import InMemoryStreamSink


@pytest.fixture
def _hermetic_registry() -> ToolRegistryClient:
    from batna.agents.eval import _HermeticRegistry

    return _HermeticRegistry()


async def test_full_negotiation_streams_ordered_events(
    _hermetic_registry: ToolRegistryClient,
) -> None:
    sink = InMemoryStreamSink(session_id="sess-flow-1")
    buyer_p, seller_p = _scenario_principals("wide")
    registry = _hermetic_registry

    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(registry, sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(registry, sink=sink, role="seller"),
        sink=sink,
        role="seller",
    )

    result = await run_negotiation(
        buyer,
        seller,
        buyer_p,
        seller_p,
        _DEFAULT_SCENARIO,
        max_rounds=6,
        sink=sink,
        thread_id="sess-flow-1",
    )

    assert result["outcome"] is NegotiationOutcome.AGREEMENT
    events = sink.emitted
    assert len(events) >= 8
    # Monotonic sequence, single shared session.
    assert [e.seq for e in events] == list(range(len(events)))
    assert {e.session_id for e in events} == {"sess-flow-1"}

    emitted = [e.type for e in events]
    assert emitted[0] is EventType.SESSION_START
    assert emitted[-1] is EventType.SESSION_END
    for expected, role in (
        (EventType.DISCOVERY, "both"),
        (EventType.OFFER, "buyer"),
        (EventType.OFFER, "seller"),
        (EventType.ACCEPTANCE_CHECK, "buyer"),
        (EventType.ACCEPTANCE_CHECK, "seller"),
        (EventType.FINALIZE, None),
    ):
        assert expected in emitted
        if role is not None:
            assert any(e.type is expected and e.side == role for e in events)


async def test_tool_call_payloads_carry_real_arguments_and_response(
    _hermetic_registry: ToolRegistryClient,
) -> None:
    sink = InMemoryStreamSink(session_id="sess-payload-2")
    buyer_p, seller_p = _scenario_principals("wide")
    registry = _hermetic_registry

    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(registry, sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(registry, sink=sink, role="seller"),
        sink=sink,
        role="seller",
    )

    await run_negotiation(
        buyer,
        seller,
        buyer_p,
        seller_p,
        _DEFAULT_SCENARIO,
        max_rounds=6,
        sink=sink,
        thread_id="sess-payload-2",
    )

    starts = [e for e in sink.emitted if e.type is EventType.TOOL_CALL_START]
    results = [e for e in sink.emitted if e.type is EventType.TOOL_CALL_RESULT]
    assert starts and results
    # Every call start is a real tool invocation with its arguments on the wire.
    for ev in starts:
        assert ev.payload["name"] == "get_market_benchmark"
        assert "industry" in ev.payload["arguments"]
        assert ev.side in {"buyer", "seller"}
    # Responses are the raw text the provider got back from the tool.
    for ev in results:
        assert '"source": "BLS"' in ev.payload["response"]
        assert ev.payload["arguments"]["industry"] == "cloud_hosting"

    # Each side grounded itself: >= 1 start/result pair per side.
    assert {ev.side for ev in starts} == {"buyer", "seller"}


async def test_buyer_and_seller_share_one_session_sink(
    _hermetic_registry: ToolRegistryClient,
) -> None:
    """A single sink shared by both agents yields globally unique seq numbers."""
    sink = InMemoryStreamSink(session_id="sess-shared-3")
    buyer_p, seller_p = _scenario_principals("asymmetric")
    registry = _hermetic_registry

    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(registry, sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(registry, sink=sink, role="seller"),
        sink=sink,
        role="seller",
    )

    await run_negotiation(
        buyer,
        seller,
        buyer_p,
        seller_p,
        _DEFAULT_SCENARIO,
        max_rounds=6,
        sink=sink,
        thread_id="sess-shared-3",
    )
    seqs = [e.seq for e in sink.emitted]
    assert len(set(seqs)) == len(seqs)  # no collisions across both agents


async def test_run_mode_is_threaded_into_session_start_and_result(
    _hermetic_registry: ToolRegistryClient,
) -> None:
    """run_mode/run_model are surfaced to the dashboard (xxx_start event + result)."""
    sink = InMemoryStreamSink(session_id="sess-runmode-4")
    buyer_p, seller_p = _scenario_principals("wide")
    registry = _hermetic_registry

    buyer = BuyerAgent(
        llm=ScriptedNegotiatorLLM(role="buyer", base_price=70_000.0),
        provider=ToolProvider(registry, sink=sink, role="buyer"),
        sink=sink,
        role="buyer",
    )
    seller = SellerAgent(
        llm=ScriptedNegotiatorLLM(role="seller", base_price=120_000.0),
        provider=ToolProvider(registry, sink=sink, role="seller"),
        sink=sink,
        role="seller",
    )

    result = await run_negotiation(
        buyer,
        seller,
        buyer_p,
        seller_p,
        _DEFAULT_SCENARIO,
        max_rounds=6,
        sink=sink,
        thread_id="sess-runmode-4",
        run_mode="live",
        run_model="qwen2.5:7b",
    )

    # The live-model identity is threaded through so the UI can label the run.
    assert result["run_mode"] == "live"
    assert result["run_model"] == "qwen2.5:7b"
    start = next(e for e in sink.emitted if e.type is EventType.SESSION_START)
    assert start.payload["run_mode"] == "live"
    assert start.payload["run_model"] == "qwen2.5:7b"

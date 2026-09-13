"""Hermetic tests for the stream sink implementations (Null / InMemory)."""

from __future__ import annotations

from batna.stream.events import EventType, build_event
from batna.stream.sink import InMemoryStreamSink, NullStreamSink


async def test_null_sink_is_a_noop() -> None:
    sink = NullStreamSink()
    event = build_event(EventType.DISCOVERY, {"buyer_tools": ["a"], "seller_tools": ["b"]})
    returned = await sink.emit(event)
    # Unchanged: no stamping on the null sink.
    assert returned is event
    assert returned.session_id == ""
    assert returned.seq == 0


async def test_in_memory_sink_stamps_sequence_and_session() -> None:
    sink = InMemoryStreamSink(session_id="sess-1")
    await sink.emit(build_event(EventType.SESSION_START, {"max_rounds": 6}))
    await sink.emit(build_event(EventType.TOOL_CALL_START, {"name": "x"}, side="buyer"))
    events = sink.emitted

    assert len(events) == 2
    assert [e.seq for e in events] == [0, 1]
    assert all(e.session_id == "sess-1" for e in events)
    assert events[1].side == "buyer"


async def test_in_memory_sink_emitted_is_a_copy() -> None:
    sink = InMemoryStreamSink()
    await sink.emit(build_event(EventType.ERROR, {"message": "boom"}))
    snapshot = sink.emitted
    snapshot.append(snapshot[0])  # mutating the copy must not affect the sink
    assert len(sink.emitted) == 1

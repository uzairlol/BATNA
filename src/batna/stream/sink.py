r"""Stream sink interface and reference implementations.

A ``StreamSink`` consumes ``StreamEvent``\ s (attaching the per-session
``session_id`` / ``seq`` / ``ts``) as they happen. Every producer
(``ToolProvider``, ``NegotiatorAgent``, the negotiation graph) takes an optional
``sink`` so the streaming layer is a pure additive concern — existing callers
default to ``NullStreamSink``-style behaviour (``None``) and are unaffected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from batna.stream.events import StreamEvent


def stamp_event(
    event: StreamEvent,
    *,
    session_id: str,
    seq: int,
    ts: str | None = None,
) -> StreamEvent:
    """Return a copy of ``event`` with the sink-owned metadata applied."""
    return event.model_copy(
        update={
            "session_id": session_id,
            "seq": seq,
            "ts": ts or datetime.now(UTC).isoformat(),
        }
    )


class StreamSink(Protocol):
    """Anything that can ingest a streaming event."""

    async def emit(self, event: StreamEvent) -> StreamEvent:
        """Publish ``event``; return the final stamped event."""
        ...


class NullStreamSink:
    """No-op sink used when streaming is disabled (default configuration)."""

    session_id = ""
    seq = 0

    async def emit(self, event: StreamEvent) -> StreamEvent:
        return event


class InMemoryStreamSink:
    """Hermetic sink that records stamped events in a list (for tests)."""

    def __init__(self, session_id: str = "test-session") -> None:
        self.session_id = session_id
        self._seq = 0
        self.events: list[StreamEvent] = []

    async def emit(self, event: StreamEvent) -> StreamEvent:
        stamped = stamp_event(event, session_id=self.session_id, seq=self._seq)
        self._seq += 1
        self.events.append(stamped)
        return stamped

    @property
    def emitted(self) -> list[StreamEvent]:
        return list(self.events)

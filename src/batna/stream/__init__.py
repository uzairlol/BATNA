"""Real-time streaming events, sinks, and the Redis pub/sub publisher.

Phase 7 wires every negotiation event onto a ``StreamSink`` (Redis pub/sub by
default) and exposes it over a FastAPI WebSocket so a dashboard can watch a live
negotiation — including the raw request/response payloads of every real MCP
tool call — with no polling. The ``StreamEvent`` model in ``events`` is the
**source of truth** for the client/backend wire contract.
"""

from batna.stream.events import EventType, StreamEvent
from batna.stream.publisher import RedisStreamSink, new_async_redis
from batna.stream.sink import (
    InMemoryStreamSink,
    NullStreamSink,
    StreamSink,
    stamp_event,
)

__all__ = [
    "EventType",
    "InMemoryStreamSink",
    "NullStreamSink",
    "RedisStreamSink",
    "StreamEvent",
    "StreamSink",
    "new_async_redis",
    "stamp_event",
]

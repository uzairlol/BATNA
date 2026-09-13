"""Redis-backed streaming publisher.

``RedisStreamSink`` broadcasts each event over a per-session ``PUBLISH`` channel
and also writes it to a bounded list so a client that connects mid-run can
replay prior events on connect — giving a live, no-polling feed and a coherent
whole-session view.

Graceful degradation mirrors spec §9: if Redis is temporarily unreachable the
emit logs and returns the stamped event anyway so a negotiation never aborts
because its observability backbone hiccuped; the session is still audible from
its in-memory result.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from batna.stream.events import StreamEvent
from batna.stream.sink import stamp_event

logger = logging.getLogger(__name__)


def new_async_redis(url: str, timeout: float = 5.0) -> aioredis.Redis[Any]:
    """Open an async Redis client with string decoding enabled by default."""
    return aioredis.from_url(url, decode_responses=True, socket_timeout=timeout)


class RedisStreamSink:
    """Stream sink backed by Redis pub/sub + a bounded replay buffer."""

    def __init__(
        self,
        redis: aioredis.Redis[Any],
        session_id: str,
        *,
        channel_prefix: str = "session",
        buffer_max: int = 500,
    ) -> None:
        self._redis = redis
        self.session_id = session_id
        self._channel = f"{channel_prefix}:{session_id}"
        self._buffer_key = f"{channel_prefix}:{session_id}:events"
        self._buffer_max = buffer_max
        self._seq = 0

    async def emit(self, event: StreamEvent) -> StreamEvent:
        stamped = stamp_event(event, session_id=self.session_id, seq=self._seq)
        self._seq += 1
        payload = stamped.model_dump_json()
        try:
            async with self._redis.pipeline() as pipe:
                pipe.publish(self._channel, payload)
                pipe.lpush(self._buffer_key, payload)
                pipe.ltrim(self._buffer_key, 0, self._buffer_max - 1)
                await pipe.execute()
        except Exception as exc:  # pragma: no cover - graceful degradation path
            logger.warning("RedisStreamSink publish failed for %s: %s", self.session_id, exc)
        return stamped

    def channel(self) -> str:
        return self._channel

    async def replay(self, limit: int = 100) -> list[str]:
        """Return the most recent buffered event JSON strings, oldest-first."""
        raw: list[Any] = await self._redis.lrange(self._buffer_key, 0, limit - 1)
        out: list[str] = []
        for value in raw:
            out.append(value.decode("utf-8") if isinstance(value, bytes) else str(value))
        return list(reversed(out))

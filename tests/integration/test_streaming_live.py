"""Live integration test for Phase 7 streaming (real Redis + real MCP).

Skips gracefully when Redis or the data providers are unavailable, so CI without
those services stays green. When they are up it verifies the full push pipeline
end-to-end: a shared ``RedisStreamSink`` publishes every event while a real MCP
negotiation runs, and ``replay()`` returns a coherent, chronological buffer whose
tool-call payloads carry the genuine request arguments and provider responses.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import redis.asyncio as aioredis

from batna.api.runner import run_streaming_negotiation
from batna.stream.events import EventType
from batna.stream.publisher import RedisStreamSink, new_async_redis


async def _require_redis() -> aioredis.Redis[Any] | None:
    try:
        client = new_async_redis("redis://localhost:6379/1", timeout=2.0)
        await client.ping()
        return client
    except Exception:  # pragma: no cover - environmental
        return None


async def test_redis_stream_sink_records_tool_call_payloads() -> None:
    redis = await _require_redis()
    if redis is None:
        pytest.skip("Redis not reachable at redis://localhost:6379/1")
    try:
        session_id = f"live-{uuid.uuid4().hex[:6]}"
        sink = RedisStreamSink(redis, session_id, buffer_max=500)

        result = await run_streaming_negotiation(
            session_id, sink, kind="wide", max_rounds=12, llm_mode="scripted"
        )
        assert result["outcome"] is not None

        replayed = await sink.replay(limit=500)
        events = [json.loads(raw) for raw in replayed]

        # The buffer holds a coherent, chronological session.
        assert len(events) >= 8
        assert events[0]["type"] == EventType.SESSION_START.value
        assert events[-1]["type"] == EventType.SESSION_END.value
        assert all(e["session_id"] == session_id for e in events)
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

        # Real MCP tool-call payloads made it onto the wire intact.
        tool_starts = [e for e in events if e["type"] == EventType.TOOL_CALL_START.value]
        tool_results = [e for e in events if e["type"] == EventType.TOOL_CALL_RESULT.value]
        assert tool_starts and tool_results
        for ev in tool_starts:
            assert "industry" in ev["payload"]["arguments"]
        assert any('"source"' in r["payload"]["response"] for r in tool_results)
    finally:
        await redis.close()

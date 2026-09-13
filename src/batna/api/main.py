"""FastAPI server exposing BATNA's live-negotiation streaming endpoint.

Phase 7 wire-up: a browser opens ``WS /api/ws/{session_id}`` (native WebSocket,
no polling), which first *replays* the session's buffered events from Redis and
then forwards each new event the instant it is published — including the raw
request/response payloads of every real MCP tool call.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from batna.api.runner import StreamingSession, run_streaming_negotiation
from batna.config import settings
from batna.stream.publisher import RedisStreamSink, new_async_redis

logger = logging.getLogger(__name__)

_DASHBOARD_DIR = Path(__file__).resolve().parents[3] / "dashboard" / "dist"

_redis: aioredis.Redis[Any] | None = None
_sessions: dict[str, StreamingSession] = {}


def _get_redis() -> aioredis.Redis[Any]:
    if _redis is None:
        raise RuntimeError("Redis not initialised; run the app within its lifespan")
    return _redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the shared Redis connection for the app's lifetime."""
    del app
    global _redis
    _redis = new_async_redis(settings.redis_url)
    logger.info("Streaming API ready; Redis at %s", settings.redis_url)
    try:
        yield
    finally:
        if _redis is not None:
            await _redis.close()
        _redis = None


app = FastAPI(
    title="BATNA",
    description="Live multi-agent contract negotiation with real-data tool calls.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/api/sessions", status_code=201)
async def create_session(kind: str = "wide") -> dict[str, Any]:
    """Create a session bound to a Redis sink; the caller then starts it."""
    if kind not in {"wide", "narrow", "asymmetric", "no_zopa"}:
        raise HTTPException(status_code=422, detail=f"unknown kind: {kind}")
    session_id = uuid.uuid4().hex
    sink = RedisStreamSink(
        _get_redis(),
        session_id,
        channel_prefix=settings.redis_pubsub_channel_prefix,
        buffer_max=settings.stream_event_buffer_max,
    )
    session = StreamingSession(session_id=session_id, sink=sink, kind=kind)
    _sessions[session_id] = session
    return {"session_id": session_id, "kind": kind, "status": session.status}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return {
        "session_id": session.session_id,
        "kind": session.kind,
        "status": session.status,
        "run_mode": session.run_mode,
        "run_model": session.run_model,
        "error": session.error,
    }


@app.post("/api/sessions/{session_id}/negotiate")
async def start_negotiation(session_id: str) -> dict[str, Any]:
    """Kick off the negotiation in a background task; it streams to Redis."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    if session.status in {"running", "done", "error"}:
        return {"session_id": session_id, "status": session.status}
    session.status = "running"
    session.task = asyncio.create_task(_drive_session(session))
    return {"session_id": session_id, "status": session.status}


async def _drive_session(session: StreamingSession) -> None:
    try:
        session.result = await run_streaming_negotiation(
            session.session_id, session.sink, kind=session.kind
        )
        session.run_mode = session.result.get("run_mode") or "scripted"
        session.run_model = session.result.get("run_model") or ""
        session.status = "done"
    except Exception as exc:  # pragma: no cover - surfaced via session.status
        logger.exception("Session %s failed", session.session_id)
        session.status = "error"
        session.error = str(exc)


@app.websocket("/api/ws/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str) -> None:
    """Replay the buffered session, then forward live events (push, no polling)."""
    session = _sessions.get(session_id)
    if session is None:
        await websocket.close(code=4404, reason="unknown session")
        return
    await websocket.accept()
    pubsub = _get_redis().pubsub()
    try:
        # Subscribe to the live channel FIRST, then replay the buffered snapshot.
        # If we replayed first, an event published in the gap between the buffer
        # read and the subscribe would be lost (e.g. session_start on a fast run).
        # With subscribe-then-replay, an event published mid-replay may arrive in
        # BOTH the snapshot and the live stream; the dashboard dedups by seq, so
        # the handoff is gapless without ever emitting a duplicate.
        await pubsub.subscribe(session.sink.channel())
        for raw in await session.sink.replay(settings.stream_replay_limit):
            await websocket.send_text(raw)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await websocket.send_text(str(data))
    except WebSocketDisconnect:
        logger.info("Client disconnected from session %s", session_id)
    finally:
        await pubsub.close()


_NO_BUILD_HTML = """<!doctype html>
<html>
  <head><title>BATNA dashboard</title><meta charset="utf-8"></head>
  <body style="font-family:sans-serif;max-width:720px;margin:48px auto">
    <h1>BATNA — live dashboard</h1>
    <p>The dashboard has not been built yet.</p>
    <p>Build it with:</p>
    <pre>  cd dashboard &amp;&amp; npm install &amp;&amp; npm run build</pre>
    <p>then refresh this page. (During development, <code>npm run dev</code> in
    <code>dashboard/</code> serves the Vite app on :5173 with a proxy to this API.)</p>
  </body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard_index() -> HTMLResponse:
    index = _DASHBOARD_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse(_NO_BUILD_HTML)


# Serve built dashboard assets (Vite output) if present.
if (_DASHBOARD_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DASHBOARD_DIR / "assets"), name="assets")

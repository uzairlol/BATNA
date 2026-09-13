"""Hermetic tests for the Phase 7 FastAPI REST + WebSocket streaming endpoints.

No real Redis or MCP is used: the app's shared Redis handle and session registry
are swapped for in-memory stubs that exercise the exact same code paths
(replay-on-connect, then live pub/sub forwarding).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from batna.api import main as api_main
from batna.api.runner import StreamingSession


class _DummyRedis:
    """Enough of a Redis client for endpoints that only construct a sink."""


class _StubPubSub:
    def __init__(self, channel: str, live_payload: str) -> None:
        self._channel = channel
        self._live = live_payload

    async def subscribe(self, *channels: str) -> None:
        del channels
        return None

    async def listen(self) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "subscribe", "channel": self._channel, "data": 1}
        yield {"type": "message", "channel": self._channel, "data": self._live}

    async def close(self) -> None:
        return None


class _StubRedis(_DummyRedis):
    def __init__(self, channel: str, live_payload: str) -> None:
        self._channel = channel
        self._live = live_payload

    def pubsub(self) -> _StubPubSub:
        return _StubPubSub(self._channel, self._live)


class _StubSink:
    def __init__(self, channel: str, replay_payloads: list[str]) -> None:
        self._channel = channel
        self._replay = replay_payloads

    async def replay(self, limit: int = 100) -> list[str]:
        del limit
        return list(self._replay)

    def channel(self) -> str:
        return self._channel


def _reset_globals() -> None:
    api_main._redis = cast(Any, _DummyRedis())
    api_main._sessions = {}


@pytest.fixture(autouse=True)
def _isolated_app_state() -> Generator[None, None, None]:
    _reset_globals()
    yield
    _reset_globals()


def test_create_session_and_validate_kind() -> None:
    client = TestClient(api_main.app)
    resp = client.post("/api/sessions", params={"kind": "wide"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "created"
    assert body["kind"] == "wide"

    bad = client.post("/api/sessions", params={"kind": "nonsense"})
    assert bad.status_code == 422


def test_unknown_session_is_404() -> None:
    client = TestClient(api_main.app)
    assert client.get("/api/sessions/does-not-exist").status_code == 404
    assert client.post("/api/sessions/does-not-exist/negotiate").status_code == 404


def test_negotiate_is_idempotent_when_already_running() -> None:
    sid = uuid.uuid4().hex
    api_main._sessions[sid] = StreamingSession(
        session_id=sid,
        sink=cast(Any, _StubSink("x", [])),
        kind="wide",
        status="running",
    )
    client = TestClient(api_main.app)
    resp = client.post(f"/api/sessions/{sid}/negotiate")
    assert resp.status_code == 200
    assert resp.json() == {"session_id": sid, "status": "running"}


def test_websocket_replays_buffer_then_forwards_live_event() -> None:
    sid = uuid.uuid4().hex
    ch = f"session:{sid}"
    replay_json = json.dumps(
        {"type": "session_start", "session_id": sid, "seq": 0, "payload": {"max_rounds": 6}}
    )
    live_json = json.dumps(
        {
            "type": "tool_call_result",
            "session_id": sid,
            "seq": 1,
            "payload": {"name": "get_market_benchmark", "response": '{"source": "BLS"}'},
        }
    )
    api_main._sessions[sid] = StreamingSession(
        session_id=sid,
        sink=cast(Any, _StubSink(ch, [replay_json])),
        kind="wide",
        status="running",
    )
    api_main._redis = cast(Any, _StubRedis(ch, live_json))

    client = TestClient(api_main.app)
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        # 1) buffered events replayed on connect (whole-session view)
        assert ws.receive_json() == json.loads(replay_json)
        # 2) the live event forwarded the instant it is published
        assert ws.receive_json() == json.loads(live_json)


def test_websocket_unknown_session_closes() -> None:
    client = TestClient(api_main.app)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/ws/ghost") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4404


def test_resolve_llms_scripted_is_hermetic() -> None:
    """Forcing ``scripted`` never touches the network and returns determinism."""
    from batna.api import runner

    async def _go() -> tuple[str, str, str, str]:
        mode, model, bl, sl = await runner._resolve_llms("scripted")
        return mode, model, type(bl).__name__, type(sl).__name__

    mode, model, b, s = asyncio.run(_go())
    assert mode == "scripted"
    assert model == "scripted-deterministic"
    assert b == "ScriptedNegotiatorLLM"
    assert s == "ScriptedNegotiatorLLM"


def test_resolve_llms_live_default_falls_back_when_ollama_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default is ``live``; reaching for a real model but falling back keeps CI green."""
    from batna.api import runner

    requested: dict[str, str] = {}

    async def _unreachable(model: str) -> bool:
        requested["model"] = model
        return False

    monkeypatch.setattr(runner, "_live_llm_available", _unreachable)

    async def _go() -> tuple[str, str]:
        mode, model, *_ = await runner._resolve_llms()
        return mode, model

    mode, model = asyncio.run(_go())
    # It attempted the live path (a tell that the default is now "live")...
    assert requested["model"] == runner.settings.agent_model
    # ...and fell back to a deterministic session that still labels honestly.
    assert mode == "scripted"
    assert model == "scripted-deterministic"

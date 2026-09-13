"""Typed real-time streaming events for BATNA negotiation sessions.

The ``StreamEvent`` model is the **source of truth** for the streaming wire
contract between the backend, Redis pub/sub, and the dashboard's native
WebSocket client. The TypeScript ``StreamEvent`` interface in
``dashboard/src/feed.ts`` mirrors these exact field names; a unit test
(``tests/unit/test_stream_events.py``) pins the serialized key set so the
contract cannot silently drift between backend and frontend.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventType(enum.StrEnum):
    """Every event kind the streaming layer can publish.

    Phase 7 emits the negotiation + tool-call events today; the taxonomy also
    reserves the audit and approval-gate types so Phase 8/10 reuse the same wire
    without a breaking change.
    """

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    DISCOVERY = "discovery"
    REASONING = "reasoning"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    TOOL_CALL_ERROR = "tool_call_error"
    OFFER = "offer"
    ACCEPTANCE_CHECK = "acceptance_check"
    FINALIZE = "finalize"
    ERROR = "error"
    # Reserved for later phases (still valid on the wire, not yet emitted).
    AUDIT = "audit"
    APPROVAL_GATE = "approval_gate"


class StreamEvent(BaseModel):
    """A single event published to a session's live stream.

    ``session_id``, ``seq`` and ``ts`` are stamped by the sink (which owns the
    per-session monotonic sequence) so emitting code only describes *what*
    happened; fields not yet stamped carry safe defaults.
    """

    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""
    seq: int = Field(default=0, ge=0)
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    side: str | None = None  # "buyer" | "seller" | "both" | None


def build_event(
    type_: EventType,
    payload: dict[str, Any],
    *,
    side: str | None = None,
) -> StreamEvent:
    """Construct a ``StreamEvent`` before it is stamped by a sink."""
    return StreamEvent(type=type_, payload=payload, side=side)

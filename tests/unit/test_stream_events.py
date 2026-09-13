"""Pins the ``StreamEvent`` wire contract (backend ↔ dashboard).

The dashboard's TypeScript ``StreamEvent`` interface mirrors these exact field
names; if anyone renames/adds a serialized field here, the test fails so the
TS side (tests/dashboard_contract.test.ts) and backend cannot drift.
"""

from __future__ import annotations

import json

from batna.stream.events import EventType, StreamEvent, build_event


def test_stream_event_serialized_field_set_is_stable() -> None:
    event = build_event(
        EventType.TOOL_CALL_START,
        {"name": "get_market_benchmark", "arguments": {"industry": "cloud"}},
        side="buyer",
    )
    as_dict = event.model_dump()
    # Every field the TS interface declares — nothing more, nothing missing.
    assert set(as_dict) == {"type", "payload", "session_id", "seq", "ts", "side"}
    assert as_dict["type"] == EventType.TOOL_CALL_START
    assert as_dict["payload"]["name"] == "get_market_benchmark"
    assert as_dict["session_id"] == ""
    assert as_dict["seq"] == 0
    assert as_dict["side"] == "buyer"


def test_stream_event_to_json_uses_enum_str_value_not_name() -> None:
    event = build_event(EventType.OFFER, {"price": 85000.0}, side="seller")
    data = json.loads(event.model_dump_json())
    # The wire value is the snake_case string, not the Python attribute name.
    assert data["type"] == "offer"
    assert "OFFER" not in data["type"]


def test_event_type_values_match_frontend_contract() -> None:
    expected = {
        "session_start",
        "session_end",
        "discovery",
        "reasoning",
        "tool_call_start",
        "tool_call_result",
        "tool_call_error",
        "offer",
        "acceptance_check",
        "finalize",
        "error",
        "audit",
        "approval_gate",
    }
    assert set(EventType) == expected


def test_stream_event_stamps_fields_later() -> None:
    event = StreamEvent(type=EventType.FINALIZE, payload={"outcome": "agreement"})
    assert event.session_id == ""
    assert event.seq == 0
    assert event.payload["outcome"] == "agreement"

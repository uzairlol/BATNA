"""Provenance log for real MCP tool invocations during an agent session.

Phase 5's Definition of Done requires that the buyer agent never references a
result it did not actually fetch. Every real call that ``ToolProvider`` executes
is appended here, and ``batna.agents.verification`` diffs the agent's textual
claims against this log.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ToolCallEntry:
    """A single real tool invocation and its raw result."""

    name: str
    arguments: dict[str, Any]
    response: str
    ok: bool = True
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "response": self.response,
            "ok": self.ok,
            "started_at": self.started_at,
        }


class ToolCallLog:
    """Ordered, append-only record of tool calls with serialization helpers."""

    def __init__(self) -> None:
        self._entries: list[ToolCallEntry] = []

    def append(self, entry: ToolCallEntry) -> None:
        self._entries.append(entry)

    def __iter__(self) -> Iterator[ToolCallEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> list[ToolCallEntry]:
        return list(self._entries)

    def tool_names(self) -> list[str]:
        return [entry.name for entry in self._entries]

    def responses_text(self) -> str:
        return "\n".join(entry.response for entry in self._entries if entry.ok)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(entry.to_dict()) for entry in self._entries)

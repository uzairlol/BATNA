"""BATNA FastAPI REST & WebSocket streaming server (Phase 7).

Serves live negotiation sessions over a native WebSocket: ``POST /api/sessions``
creates a session, ``POST /api/sessions/{id}/negotiate`` runs a negotiation that
publishes every event to Redis, and ``WS /api/ws/{id}`` replays the buffer and
forwards live events — real tool-call payloads included — with no polling.
"""

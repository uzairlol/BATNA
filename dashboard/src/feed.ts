/**
 * Live-streaming client + the TS mirror of the backend `StreamEvent` contract.
 *
 * The backend Pydantic model `batna.stream.events.StreamEvent` is the source of
 * truth; these exact field names are pinned by the backend unit test
 * `tests/unit/test_stream_events.py` so the two sides cannot drift.
 */

export type EventType =
  | "session_start"
  | "session_end"
  | "discovery"
  | "reasoning"
  | "tool_call_start"
  | "tool_call_result"
  | "tool_call_error"
  | "offer"
  | "acceptance_check"
  | "finalize"
  | "error"
  | "audit"
  | "approval_gate";

export interface StreamEvent {
  type: EventType;
  payload: Record<string, unknown>;
  session_id: string;
  seq: number;
  ts: string;
  side?: string | null;
}

export type EventHandler = (event: StreamEvent) => void;
export type ConnectionState = "connecting" | "open" | "closed" | "error";
export type ConnectionHandler = (state: ConnectionState) => void;

/** REST helpers for creating and starting a session. */
export async function createSession(kind: string): Promise<{ session_id: string }> {
  const resp = await fetch(`/api/sessions?kind=${encodeURIComponent(kind)}`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(`createSession failed: ${resp.status}`);
  return resp.json();
}

export async function startNegotiation(
  sessionId: string,
): Promise<{ session_id: string; status: string }> {
  const resp = await fetch(`/api/sessions/${sessionId}/negotiate`, { method: "POST" });
  if (!resp.ok) throw new Error(`startNegotiation failed: ${resp.status}`);
  return resp.json();
}

/**
 * Native WebSocket client: the server replays the buffered session on connect,
 * then pushes each new event the instant it is published — no polling.
 */
export class LiveFeed {
  private ws: WebSocket | null = null;

  constructor(
    private readonly sessionId: string,
    private readonly onEvent: EventHandler,
    private readonly onConnection: ConnectionHandler,
  ) {}

  start(): void {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/api/ws/${this.sessionId}`;
    this.onConnection("connecting");
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => this.onConnection("open");
    ws.onmessage = (msg) => {
      try {
        this.onEvent(JSON.parse(msg.data) as StreamEvent);
      } catch {
        // ignore non-JSON frames
      }
    };
    ws.onclose = () => this.onConnection("closed");
    ws.onerror = () => this.onConnection("error");
  }

  stop(): void {
    this.ws?.close();
    this.ws = null;
  }
}
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

/** Shape of the server-authored metrics blob on the `session_end` payload. */
export interface SideSummary {
  opening_price: number | null;
  closing_price: number | null;
  total_concession: number;
  max_step: number;
  avg_step: number;
  offers: number[];
}

export interface SessionSummary {
  outcome: string;
  rounds_elapsed: number;
  max_rounds: number;
  until_agreement: boolean;
  agreed_price: number | null;
  agreed_at_round: number | null;
  convergence_gap: number;
  price_zone: {
    buyer_min: number;
    buyer_max: number;
    seller_min: number;
    seller_max: number;
  };
  buyer: SideSummary;
  seller: SideSummary;
  tool_breakdown: Record<string, Record<string, number>>;
  acceptance_checks: number;
  near_misses: number;
  duration_ms: number;
}

function isSummary(v: unknown): v is SessionSummary {
  if (typeof v !== "object" || v === null) return false;
  const s = v as Record<string, unknown>;
  return (
    typeof s.outcome === "string" &&
    typeof s.rounds_elapsed === "number" &&
    typeof s.buyer === "object" &&
    typeof s.seller === "object" &&
    typeof s.price_zone === "object"
  );
}

/** Extract the metrics blob from a `session_end` event, if present. */
export function summaryFromEvent(event: StreamEvent): SessionSummary | null {
  return isSummary(event.payload?.summary) ? (event.payload.summary as SessionSummary) : null;
}

/** REST helpers for creating and starting a session. */
export async function createSession(
  kind: string,
  untilAgreement?: boolean,
): Promise<{ session_id: string }> {
  const qs = new URLSearchParams({ kind });
  if (untilAgreement) qs.set("until_agreement", "true");
  const resp = await fetch(`/api/sessions?${qs.toString()}`, { method: "POST" });
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
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
 *
 * The connection survives transient drops: if the socket closes while the feed
 * is still active (i.e. not deliberately stopped), it reconnects with
 * exponential backoff so a flaky network never silently kills a live session.
 * The app's seq-based dedup (see `App`'s `seenSeq`) makes replay + live frames
 * safe across rebuilds, so a reconnect can never double-render an event.
 */
export class LiveFeed {
  private ws: WebSocket | null = null;
  private stopped = true;
  private retries = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  /** Cap reconnect delay so a dead session doesn't hammer the server forever. */
  private static readonly MAX_RETRY_MS = 8000;

  constructor(
    private readonly sessionId: string,
    private readonly onEvent: EventHandler,
    private readonly onConnection: ConnectionHandler,
  ) {}

  start(): void {
    this.stopped = false;
    this.retries = 0;
    this.connect();
  }

  private connect(): void {
    if (this.stopped) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/api/ws/${this.sessionId}`;
    this.onConnection("connecting");
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      this.retries = 0;
      this.onConnection("open");
    };
    ws.onmessage = (msg) => {
      try {
        this.onEvent(JSON.parse(msg.data) as StreamEvent);
      } catch {
        // ignore non-JSON frames
      }
    };
    ws.onclose = () => {
      this.ws = null;
      if (this.stopped) {
        this.onConnection("closed");
        return;
      }
      this.scheduleReconnect();
    };
    ws.onerror = () => {
      // `onclose` fires right after `onerror`; let it own the reconnect logic.
      this.onConnection("error");
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    // Exponential backoff with a little jitter so parallel clients don't sync up.
    const base = Math.min(1000 * 2 ** this.retries, LiveFeed.MAX_RETRY_MS);
    const jitter = Math.round(base * (0.5 + Math.random() * 0.5));
    this.retries += 1;
    this.onConnection("connecting");
    this.timer = setTimeout(() => this.connect(), jitter);
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.onConnection("closed");
  }
}
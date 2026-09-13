import { useCallback, useEffect, useRef, useState } from "react";
import EventFeed from "./components/EventFeed";
import Transcript from "./components/Transcript";
import {
  LiveFeed,
  createSession,
  startNegotiation,
  type ConnectionState,
  type EventHandler,
  type StreamEvent,
} from "./feed";

const KINDS = ["wide", "narrow", "asymmetric", "no_zopa"] as const;
type View = "transcript" | "log";

export default function App() {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("wide");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [conn, setConn] = useState<ConnectionState>("closed");
  const [view, setView] = useState<View>("transcript");
  const feedRef = useRef<LiveFeed | null>(null);
  const seenSeq = useRef<Set<number>>(new Set());

  const onEvent: EventHandler = useCallback((event) => {
    // Dedup replay + live frames by the backend's monotonic per-session seq so a
    // reconnect (or a buffered replay racing a live publish) can never render a
    // duplicate event or double-count the feed.
    if (seenSeq.current.has(event.seq)) return;
    seenSeq.current.add(event.seq);
    setEvents((prev) => [...prev, event]);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setEvents([]);
    seenSeq.current = new Set();
    feedRef.current?.stop();
    try {
      const { session_id } = await createSession(kind);
      setSessionId(session_id);
      await startNegotiation(session_id);
      const feed = new LiveFeed(session_id, onEvent, setConn);
      feedRef.current = feed;
      feed.start();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [kind, onEvent]);

  // Keep the active pane pinned to the newest event as it streams in.
  useEffect(() => {
    const el = document.querySelector<HTMLElement>(
      view === "transcript" ? ".transcript" : ".feed",
    );
    if (el) el.scrollTop = el.scrollHeight;
  }, [events, view]);

  const startEvent = events.find((e) => e.type === "session_start");
  const mode = (startEvent?.payload?.run_mode as string) || null;
  const model = (startEvent?.payload?.run_model as string) || null;
  const offers = events.filter((e) => e.type === "offer").length;
  const toolCalls = events.filter((e) => e.type === "tool_call_start").length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          BATNA <span className="brand-ph">· live negotiation</span>
        </div>
        <div className="controls">
          <label>
            Scenario
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}
              disabled={conn === "open"}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <button onClick={start} disabled={conn === "open"}>
            Start negotiation
          </button>
        </div>
      </header>

      <div className="statusbar">
        <span className={`pill pill-${conn}`}>ws: {conn}</span>
        {sessionId && <span className="pill">session: {sessionId.slice(0, 8)}</span>}
        {mode && (
          <span className={`pill ${mode === "live" ? "pill-open" : "pill-muted"}`}>
            mode: {mode}
          </span>
        )}
        {model && <span className="pill">model: {model}</span>}
        {events.length > 0 && <span className="pill">events: {events.length}</span>}
        {offers > 0 && <span className="pill">offers: {offers}</span>}
        {toolCalls > 0 && <span className="pill">tool calls: {toolCalls}</span>}
        {error && <span className="pill pill-error">error: {error}</span>}
      </div>

      <nav className="view-toggle" aria-label="Dashboard view">
        <button
          className={view === "transcript" ? "active" : ""}
          onClick={() => setView("transcript")}
        >
          Negotiation
        </button>
        <button
          className={view === "log" ? "active" : ""}
          onClick={() => setView("log")}
        >
          Raw event log
        </button>
      </nav>

      <div className="view-body">
        {view === "transcript" ? (
          <Transcript events={events} mode={mode} model={model} />
        ) : (
          <EventFeed events={events} />
        )}
      </div>
    </div>
  );
}
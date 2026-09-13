import { useCallback, useRef, useState } from "react";
import EventFeed from "./components/EventFeed";
import {
  LiveFeed,
  createSession,
  startNegotiation,
  type ConnectionState,
  type EventHandler,
  type StreamEvent,
} from "./feed";

const KINDS = ["wide", "narrow", "asymmetric", "no_zopa"] as const;

export default function App() {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("wide");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [conn, setConn] = useState<ConnectionState>("closed");
  const feedRef = useRef<LiveFeed | null>(null);

  const onEvent: EventHandler = useCallback((event) => {
    setEvents((prev) => [...prev, event]);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setEvents([]);
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

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          BATNA <span className="brand-ph">· Live negotiation</span>
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
        {events.length > 0 && <span className="pill">events: {events.length}</span>}
        {error && <span className="pill pill-error">error: {error}</span>}
      </div>

      <EventFeed events={events} />
    </div>
  );
}